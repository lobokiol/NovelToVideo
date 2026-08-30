from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import json
import sys
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.base_provider import BaseProvider
from app.core.config import settings
from app.schemas.provider import ProviderConfig
from app.services import provider as provider_service
from app.services.video_generation_spec import (
    VideoGenerationSpecError,
    is_seedance_2_model,
    seedance_dimensions,
)
from app.utils.secret_tools import decrypt_secret


class ProviderRuntimeError(provider_service.ProviderServiceError):
    """运行时加载或调度 provider 失败。"""


class OpenAICompatibleTextProvider(BaseProvider):
    """OpenAI 兼容协议的通用文本生成 Provider。"""

    provider_key = "openai_compatible"
    model_type = "text"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.provider_key = config.key
        self.provider_config = config.model_dump(mode="json")
        self.input_values = {**config.input_values, **(input_values or {})}
        self.base_url = config.base_url
        self.timeout = timeout
        self.client = client

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        """调用 OpenAI 兼容的 chat completions 接口生成文本。"""
        payload, headers, url = self._build_request(model_id=model_id, **kwargs)
        try:
            if self.client is not None:
                response = await self.client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=_build_httpx_timeout(self.timeout)) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"文本生成请求失败: {_format_http_error(exc, url)}") from exc

        if response.status_code >= 400:
            raise ProviderRuntimeError(f"文本生成请求失败，HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderRuntimeError("文本生成响应不是合法 JSON") from exc

    async def generate_stream(self, *, model_id: str | None = None, **kwargs: Any) -> AsyncIterator[str]:
        """调用 OpenAI 兼容的 chat completions 流式接口。"""
        payload, headers, url = self._build_request(model_id=model_id, **kwargs)
        payload["stream"] = True

        try:
            if self.client is not None:
                async with self.client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        error_text = await _read_stream_error_text(response)
                        raise ProviderRuntimeError(
                            f"文本生成流式请求失败，HTTP {response.status_code}: {error_text}"
                        )
                    async for chunk in self._iterate_stream_response(response):
                        yield chunk
            else:
                async with httpx.AsyncClient(timeout=_build_httpx_timeout(self.timeout)) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code >= 400:
                            error_text = await _read_stream_error_text(response)
                            raise ProviderRuntimeError(
                                f"文本生成流式请求失败，HTTP {response.status_code}: {error_text}"
                            )
                        async for chunk in self._iterate_stream_response(response):
                            yield chunk
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"文本生成流式请求失败: {_format_http_error(exc, url)}") from exc

    def _build_request(self, *, model_id: str | None = None, **kwargs: Any) -> tuple[dict[str, Any], dict[str, str], str]:
        resolved_model_id = (model_id or "").strip()
        if not resolved_model_id:
            raise ProviderRuntimeError("model_id 不能为空")
        messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ProviderRuntimeError("messages 不能为空")

        payload: dict[str, Any] = {
            "model": resolved_model_id,
            "messages": messages,
        }
        for key in (
            "temperature",
            "top_p",
            "max_tokens",
            "response_format",
            "stop",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
        ):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        headers = {
            "Authorization": f"Bearer {_resolve_openai_api_key(self.config, self.input_values)}",
            "Content-Type": "application/json",
        }
        return payload, headers, _build_chat_completions_url(self.base_url)

    @staticmethod
    async def _iterate_stream_response(response: Any) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            if not line:
                continue
            data = line.strip()
            if not data:
                continue
            if data.startswith("data:"):
                data = data[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            chunk = OpenAICompatibleTextProvider._extract_stream_text(payload)
            if chunk:
                yield chunk

    @staticmethod
    def _extract_stream_text(payload: Any) -> str:
        if isinstance(payload, dict):
            if isinstance(payload.get("output_text"), str):
                return payload["output_text"].strip()
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    for key in ("delta", "message"):
                        part = choice.get(key)
                        if isinstance(part, dict):
                            content = part.get("content")
                            if isinstance(content, str):
                                return content
                            if isinstance(content, list):
                                return "".join(str(item) for item in content if item is not None)
                    text = choice.get("text")
                    if isinstance(text, str):
                        return text
        if isinstance(payload, str):
            return payload
        return ""


def _image_model_accepts_response_format(model_id: str) -> bool:
    """GPT Image 系列的 images 接口不接受 response_format（恒返 b64_json），传入会被拒绝。"""

    return not (model_id or "").strip().lower().startswith("gpt-image")


class OpenAICompatibleImageProvider(BaseProvider):
    """OpenAI 兼容协议的通用图像 Provider（/images/generations 与 /images/edits）。

    与 OpenAICompatibleTextProvider 同构：所有走 OpenAI 协议的生图服务复用本类，
    各服务文件无需各自实现 generate_image/edit_image。返回供应商原始 JSON，由网关
    MediaGenerationOutput.from_raw 归一为统一媒体结果。
    """

    provider_key = "openai_compatible"
    model_type = "image"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.provider_key = config.key
        self.provider_config = config.model_dump(mode="json")
        self.input_values = {**config.input_values, **(input_values or {})}
        self.base_url = config.base_url
        self.timeout = timeout
        self.client = client

    def _build_request(
        self, *, model_id: str | None = None, prompt: str = "", **kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, str], str]:
        resolved_model_id = (model_id or "").strip()
        if not resolved_model_id:
            raise ProviderRuntimeError("model_id 不能为空")
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            raise ProviderRuntimeError("prompt 不能为空")

        payload: dict[str, Any] = {
            "model": resolved_model_id,
            "prompt": prompt_text,
            "n": 1,
        }
        if _image_model_accepts_response_format(resolved_model_id):
            payload["response_format"] = "b64_json"
        for key in (
            "size",
            "response_format",
            "aspect_ratio",
            "image_size",
            "quality",
            "background",
            "user",
            "n",
        ):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        headers = {
            "Authorization": f"Bearer {_resolve_openai_api_key(self.config, self.input_values)}",
            "Content-Type": "application/json",
        }
        return payload, headers, _build_images_generations_url(self.base_url)

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_image(model_id=model_id, **kwargs)

    async def generate_image(self, *, model_id: str | None = None, prompt: str = "", **kwargs: Any) -> Any:
        """调用 OpenAI 兼容的 images/generations 接口生成图像，返回原始 JSON。"""
        payload, headers, url = self._build_request(model_id=model_id, prompt=prompt, **kwargs)
        try:
            if self.client is not None:
                response = await self.client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=_build_httpx_timeout(self.timeout)) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"图像生成请求失败: {_format_http_error(exc, url)}") from exc

        if response.status_code >= 400:
            raise ProviderRuntimeError(f"图像生成请求失败，HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderRuntimeError("图像生成响应不是合法 JSON") from exc

    def _build_edit_request(
        self, *, model_id: str | None = None, prompt: str = "", images: list[Any] | None = None, **kwargs: Any
    ) -> tuple[dict[str, str], list[tuple[str, tuple[str, bytes, str]]], dict[str, str], str]:
        resolved_model_id = (model_id or "").strip()
        if not resolved_model_id:
            raise ProviderRuntimeError("model_id 不能为空")
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            raise ProviderRuntimeError("prompt 不能为空")

        payload: dict[str, Any] = {
            "model": resolved_model_id,
            "prompt": prompt_text,
            "n": 1,
        }
        if _image_model_accepts_response_format(resolved_model_id):
            payload["response_format"] = "b64_json"
        for key in (
            "size",
            "response_format",
            "aspect_ratio",
            "image_size",
            "quality",
            "background",
            "user",
            "n",
            "input_fidelity",
        ):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        files = _build_image_edit_files(images)
        headers = {
            "Authorization": f"Bearer {_resolve_openai_api_key(self.config, self.input_values)}",
        }
        return {key: str(value) for key, value in payload.items()}, files, headers, _build_images_edits_url(self.base_url)

    async def edit_image(
        self, *, model_id: str | None = None, prompt: str = "", images: list[Any] | None = None, **kwargs: Any
    ) -> Any:
        """调用 OpenAI 兼容的 images/edits 接口基于参考图编辑图像，返回原始 JSON。"""
        payload, files, headers, url = self._build_edit_request(
            model_id=model_id,
            prompt=prompt,
            images=images,
            **kwargs,
        )
        try:
            if self.client is not None:
                response = await self.client.post(url, headers=headers, data=payload, files=files)
            else:
                async with httpx.AsyncClient(timeout=_build_httpx_timeout(self.timeout)) as client:
                    response = await client.post(url, headers=headers, data=payload, files=files)
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"图像编辑请求失败: {_format_http_error(exc, url)}") from exc

        if response.status_code >= 400:
            raise ProviderRuntimeError(f"图像编辑请求失败，HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderRuntimeError("图像编辑响应不是合法 JSON") from exc


class VolcengineArkVideoProvider(BaseProvider):
    """火山方舟"内容生成任务"协议的通用视频 Provider。

    与 OpenAICompatibleImageProvider 同构：所有走方舟协议的视频模型复用本类，
    服务文件无需各自实现 generate_video。流程为提交任务 → 轮询直至终态，
    返回归一化 dict（url/usage/seed/duration_ms），由网关 MediaGenerationOutput
    收敛为统一媒体结果。

    生成参数使用方舟当前推荐的请求体字段传入并接受强校验；调用方可继续使用
    aspect_ratio/duration_seconds 等内部别名，适配器在提交前统一转换。
    """

    provider_key = "volcengine_ark"
    model_type = "video"

    _BODY_PARAM_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("resolution", ("resolution",)),
        ("ratio", ("ratio", "aspect_ratio")),
        ("duration", ("duration", "duration_seconds")),
        ("fps", ("fps", "frames_per_second", "framespersecond")),
        ("seed", ("seed",)),
        ("watermark", ("watermark",)),
        ("camera_fixed", ("camera_fixed", "camerafixed")),
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
        poll_interval: float | None = None,
    ) -> None:
        self.config = config
        self.provider_key = config.key
        self.provider_config = config.model_dump(mode="json")
        self.input_values = {**config.input_values, **(input_values or {})}
        self.base_url = config.base_url
        self.timeout = timeout
        self.client = client
        self.poll_interval = max(
            1.0,
            float(poll_interval if poll_interval is not None else settings.media_generation_poll_interval_seconds),
        )

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_video(model_id=model_id, **kwargs)

    async def generate_video(
        self,
        *,
        model_id: str | None = None,
        prompt: str = "",
        first_frame: Any = None,
        last_frame: Any = None,
        references: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """提交方舟视频生成任务并轮询至终态，返回归一化媒体 dict。"""

        payload = self._build_task_payload(
            model_id=model_id,
            prompt=prompt,
            first_frame=first_frame,
            last_frame=last_frame,
            references=references,
            **kwargs,
        )
        headers = {
            "Authorization": f"Bearer {_resolve_openai_api_key(self.config, self.input_values)}",
            "Content-Type": "application/json",
        }
        tasks_url = _build_content_generation_tasks_url(self.base_url)
        task_id = await self._submit_task(tasks_url, headers, payload)
        task = await self._poll_task(f"{tasks_url}/{task_id}", headers)
        dimension_source = first_frame or next(iter(references or []), None) or last_frame
        fallback_width = 0
        fallback_height = 0
        if isinstance(dimension_source, dict):
            fallback_width = int(dimension_source.get("width") or 0)
            fallback_height = int(dimension_source.get("height") or 0)
        return self._normalize_task_result(
            task,
            fallback_width=fallback_width,
            fallback_height=fallback_height,
        )

    def _build_task_payload(
        self,
        *,
        model_id: str | None = None,
        prompt: str = "",
        first_frame: Any = None,
        last_frame: Any = None,
        references: list[Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        resolved_model_id = (model_id or "").strip()
        if not resolved_model_id:
            raise ProviderRuntimeError("model_id 不能为空")
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            raise ProviderRuntimeError("prompt 不能为空")

        body_extra = self._normalize_generation_params(kwargs)

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        if first_frame is not None:
            content.append(self._image_content_item(first_frame, role="first_frame"))
        for reference in references or []:
            content.append(self._image_content_item(reference, role="reference_image"))
        if last_frame is not None:
            content.append(self._image_content_item(last_frame, role="last_frame"))

        return {"model": resolved_model_id, "content": content, **body_extra}

    def _normalize_generation_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """把内部参数别名收敛为方舟强校验请求体字段。"""

        body_extra: dict[str, Any] = {}
        consumed: set[str] = set()
        for field_name, aliases in self._BODY_PARAM_ALIASES:
            for alias in aliases:
                if alias in params and params[alias] not in (None, ""):
                    body_extra[field_name] = params[alias]
                    consumed.update(aliases)
                    break
        body_extra.update(
            {
                key: value
                for key, value in params.items()
                if key not in consumed and value not in (None, "")
            }
        )
        return body_extra

    @staticmethod
    def _image_content_item(image: Any, *, role: str) -> dict[str, Any]:
        """把帧图/参考图输入归一为方舟 image_url 内容项（data URI 或直链）。"""

        url = ""
        if isinstance(image, str):
            url = image.strip()
        elif isinstance(image, dict):
            raw_url = str(image.get("url") or "").strip()
            if raw_url:
                url = raw_url
            else:
                raw_data = image.get("data") or image.get("bytes")
                if isinstance(raw_data, (bytes, bytearray)) and raw_data:
                    mime_type = str(image.get("mime_type") or image.get("mimeType") or "image/png").strip()
                    encoded = base64.b64encode(bytes(raw_data)).decode("ascii")
                    url = f"data:{mime_type};base64,{encoded}"
        elif isinstance(image, (bytes, bytearray)) and image:
            encoded = base64.b64encode(bytes(image)).decode("ascii")
            url = f"data:image/png;base64,{encoded}"
        if not url:
            raise ProviderRuntimeError("帧图内容为空，无法提交视频生成任务")
        return {"type": "image_url", "image_url": {"url": url}, "role": role}

    async def _submit_task(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> str:
        response = await self._request("POST", url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise ProviderRuntimeError(f"视频生成任务提交失败，HTTP {response.status_code}: {response.text}")
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderRuntimeError("视频生成任务响应不是合法 JSON") from exc
        task_id = str(body.get("id") or "").strip()
        if not task_id:
            raise ProviderRuntimeError(f"视频生成任务响应缺少任务 ID：{body}")
        return task_id

    async def _poll_task(self, task_url: str, headers: dict[str, str]) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout if self.timeout > 0 else None
        consecutive_errors = 0
        while True:
            try:
                response = await self._request("GET", task_url, headers=headers)
                if response.status_code >= 400:
                    raise ProviderRuntimeError(
                        f"视频生成任务查询失败，HTTP {response.status_code}: {response.text}"
                    )
                task = response.json()
                consecutive_errors = 0
            except (ProviderRuntimeError, ValueError) as exc:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    raise ProviderRuntimeError(f"视频生成任务查询连续失败：{exc}") from exc
                task = None

            if isinstance(task, dict):
                status = str(task.get("status") or "").strip().lower()
                if status == "succeeded":
                    return task
                if status in {"failed", "cancelled"}:
                    error = task.get("error") if isinstance(task.get("error"), dict) else {}
                    message = str(error.get("message") or task.get("failure_reason") or status)
                    raise ProviderRuntimeError(f"视频生成任务未成功（{status}）：{message}")

            if deadline is not None and time.monotonic() >= deadline:
                raise ProviderRuntimeError(f"视频生成任务超时：{self.timeout}秒内未完成")
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def _normalize_task_result(
        task: dict[str, Any],
        *,
        fallback_width: int = 0,
        fallback_height: int = 0,
    ) -> dict[str, Any]:
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        video_url = str(content.get("video_url") or content.get("url") or "").strip()
        if not video_url:
            raise ProviderRuntimeError(f"视频生成任务成功但缺少视频地址：{task}")
        usage = task.get("usage") if isinstance(task.get("usage"), dict) else {}
        duration_ms = 0
        raw_duration = task.get("duration")
        if isinstance(raw_duration, (int, float)) and raw_duration > 0:
            duration_ms = int(float(raw_duration) * 1000)
        model_id = str(task.get("model") or "").strip()
        resolution = str(task.get("resolution") or "").strip().lower()
        ratio = str(task.get("ratio") or "").strip()
        width = int(task.get("width") or 0)
        height = int(task.get("height") or 0)
        if is_seedance_2_model(model_id) and resolution and ratio and ratio != "adaptive":
            try:
                width, height = seedance_dimensions(resolution, ratio)
            except VideoGenerationSpecError as exc:
                raise ProviderRuntimeError(f"Seedance 视频结果规格无效：{exc}") from exc
        elif is_seedance_2_model(model_id) and ratio == "adaptive" and (width <= 0 or height <= 0):
            width = int(fallback_width or 0)
            height = int(fallback_height or 0)
            if width <= 0 or height <= 0:
                raise ProviderRuntimeError("Seedance adaptive 视频结果缺少可验证的像素尺寸")
        return {
            "url": video_url,
            "mime_type": "video/mp4",
            "width": width,
            "height": height,
            "usage": usage,
            "seed": str(task.get("seed") or ""),
            "duration_ms": duration_ms,
            "resolution": resolution,
            "ratio": ratio,
            "raw": task,
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self.client is not None:
                return await self.client.request(method, url, **kwargs)
            async with httpx.AsyncClient(timeout=_build_httpx_timeout(min(self.timeout, 60.0) or 60.0)) as client:
                return await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"视频生成请求失败: {_format_http_error(exc, url)}") from exc


def create_provider(
    provider_key: str,
    model_type: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> BaseProvider:
    """按厂商 key 与模型类型创建运行时工具类实例。"""
    provider_class = get_provider_class(provider_key, model_type)
    return provider_class(
        api_key=api_key,
        base_url=base_url,
        input_values=input_values,
        timeout=timeout,
        client=client,
    )


def create_provider_for_model(
    model_id: str,
    *,
    provider_key: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> BaseProvider:
    """根据 model_id 查找配置中的模型能力，并创建对应 provider。"""
    model_id = model_id.strip()
    if not model_id:
        raise ProviderRuntimeError("model_id 不能为空")

    configs = (
        [provider_service.get_provider_config(provider_key)]
        if provider_key
        else provider_service.list_provider_configs()
    )
    for config in configs:
        if not config.enabled:
            continue
        for model in config.models:
            if model.model_id == model_id:
                if _should_use_openai_compatible_text_provider(config, model.model_type):
                    return OpenAICompatibleTextProvider(
                        config,
                        input_values=input_values,
                        timeout=timeout,
                        client=client,
                    )
                if _should_use_openai_compatible_image_provider(config, model.model_type):
                    return OpenAICompatibleImageProvider(
                        config,
                        input_values=input_values,
                        timeout=timeout,
                        client=client,
                    )
                if _should_use_ark_video_provider(config, model.model_type):
                    return VolcengineArkVideoProvider(
                        config,
                        input_values=input_values,
                        timeout=timeout,
                        client=client,
                    )
                return create_provider(
                    config.key,
                    model.model_type,
                    input_values=input_values,
                    timeout=timeout,
                    client=client,
                )
    raise ProviderRuntimeError("未找到可用的模型配置")


def _should_use_openai_compatible_text_provider(config: ProviderConfig, model_type: str) -> bool:
    """判断文本模型是否可使用内置 OpenAI 兼容调用器。"""
    if model_type != "text":
        return False
    protocol = config.protocol.strip().lower()
    if protocol in {"openai", "openai-compatible", "openai_compatible", "qwen", "volcengine"}:
        return True
    return bool(config.base_url.strip().rstrip("/").endswith("/v1"))


def _should_use_openai_compatible_image_provider(config: ProviderConfig, model_type: str) -> bool:
    """判断图像模型是否可使用内置 OpenAI 兼容生图调用器。"""
    if model_type != "image":
        return False
    protocol = config.protocol.strip().lower()
    if protocol in {"openai", "openai-compatible", "openai_compatible", "qwen", "volcengine"}:
        return True
    return bool(config.base_url.strip().rstrip("/").endswith("/v1"))


def _should_use_ark_video_provider(config: ProviderConfig, model_type: str) -> bool:
    """判断视频模型是否可使用内置方舟内容生成任务调用器。"""
    if model_type != "video":
        return False
    protocol = config.protocol.strip().lower()
    return protocol in {"volcengine", "volcengine_ark", "ark"}


def _build_chat_completions_url(base_url: str) -> str:
    """拼接 OpenAI 兼容的 chat completions 地址。"""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProviderRuntimeError("缺少请求地址")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderRuntimeError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _build_images_generations_url(base_url: str) -> str:
    """拼接 OpenAI 兼容的 images/generations 地址。"""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProviderRuntimeError("缺少请求地址")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderRuntimeError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/images/generations"):
        return normalized
    return f"{normalized}/images/generations"


def _build_images_edits_url(base_url: str) -> str:
    """拼接 OpenAI 兼容的 images/edits 地址。"""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProviderRuntimeError("缺少请求地址")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderRuntimeError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/images/edits"):
        return normalized
    if normalized.endswith("/images/generations"):
        return f"{normalized[: -len('/images/generations')]}/images/edits"
    return f"{normalized}/images/edits"


def _build_content_generation_tasks_url(base_url: str) -> str:
    """拼接方舟内容生成任务地址。"""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProviderRuntimeError("缺少请求地址")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderRuntimeError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/contents/generations/tasks"):
        return normalized
    return f"{normalized}/contents/generations/tasks"


def _build_image_edit_files(images: list[Any] | None) -> list[tuple[str, tuple[str, bytes, str]]]:
    """把参考图输入转换为 httpx multipart files 结构。"""

    if not isinstance(images, list) or not images:
        raise ProviderRuntimeError("images 不能为空")

    file_parts: list[tuple[str, bytes, str]] = []
    for index, item in enumerate(images, start=1):
        filename = f"reference-{index}.png"
        mime_type = "image/png"
        data: bytes | None = None

        if isinstance(item, dict):
            raw_data = item.get("data") or item.get("bytes")
            if isinstance(raw_data, (bytes, bytearray)):
                data = bytes(raw_data)
            raw_filename = str(item.get("filename") or "").strip()
            if raw_filename:
                filename = raw_filename
            raw_mime = str(item.get("mime_type") or item.get("mimeType") or "").strip()
            if raw_mime:
                mime_type = raw_mime
        elif isinstance(item, (bytes, bytearray)):
            data = bytes(item)

        if not data:
            raise ProviderRuntimeError("参考图内容不能为空")
        file_parts.append((filename, data, mime_type))

    field_name = "image[]" if len(file_parts) > 1 else "image"
    return [(field_name, part) for part in file_parts]


def _format_http_error(exc: httpx.HTTPError, url: str) -> str:
    """格式化 httpx 异常，避免空字符串错误被直接展示给用户。"""
    message = str(exc).strip()
    error_type = type(exc).__name__
    if message:
        return f"{error_type}: {message}（{url}）"
    return f"{error_type}（{url}）"


async def _read_stream_error_text(response: Any) -> str:
    """读取流式错误响应文本。"""
    aread = getattr(response, "aread", None)
    if callable(aread):
        await aread()
    text = getattr(response, "text", "")
    return str(text or "").strip()


def _build_httpx_timeout(timeout: float) -> httpx.Timeout:
    """构造模型请求超时，连接阶段保持较短，读取阶段按模型生成时间放宽。"""
    return httpx.Timeout(timeout, connect=min(15.0, timeout))


def _resolve_openai_api_key(config: ProviderConfig, values: dict[str, str]) -> str:
    """从服务配置输入值中读取并解密 API Key。"""
    candidates = [
        values.get("apiKey"),
        values.get("api_key"),
        values.get("OPENAI_API_KEY"),
        values.get("API_KEY"),
        values.get("token"),
    ]
    candidates.extend(values.get(item.key) for item in config.inputs if item.type == "password")
    candidates.extend(
        value
        for key, value in values.items()
        if key.lower().endswith(("api_key", "apikey", "token"))
    )

    for value in candidates:
        raw_value = str(value or "").strip()
        if not raw_value:
            continue
        try:
            api_key = decrypt_secret(raw_value).strip()
        except ValueError as exc:
            raise ProviderRuntimeError("API Key 解密失败") from exc
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        if api_key:
            return api_key
    raise ProviderRuntimeError("缺少 API Key")


async def generate(
    provider_key: str,
    model_type: str,
    *,
    model_id: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> Any:
    """统一调度 provider 工具类执行生成任务。"""
    provider = create_provider(
        provider_key,
        model_type,
        input_values=input_values,
        timeout=timeout,
        client=client,
    )
    return await provider.generate(model_id=model_id, **kwargs)


def get_provider_class(provider_key: str, model_type: str) -> type[BaseProvider]:
    config = provider_service.get_provider_config(provider_key)
    if not config.enabled:
        raise ProviderRuntimeError("服务未启用")

    module = load_provider_module(provider_key)
    matches: list[type[BaseProvider]] = []
    for value in vars(module).values():
        if not inspect.isclass(value) or value is BaseProvider:
            continue
        if not issubclass(value, BaseProvider):
            continue
        class_key = getattr(value, "provider_key", "")
        class_model_type = getattr(value, "model_type", "")
        if class_key == provider_key and class_model_type == model_type:
            matches.append(value)

    if not matches:
        raise ProviderRuntimeError("未找到匹配的 provider 工具类")
    if len(matches) > 1:
        raise ProviderRuntimeError("找到多个匹配的 provider 工具类")
    return matches[0]


def load_provider_module(provider_key: str):
    provider_service.get_provider_config(provider_key)
    module_name = f"app.providers.{provider_key}"
    try:
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)
    except Exception as exc:
        raise ProviderRuntimeError(f"加载 provider 模块失败: {exc}") from exc