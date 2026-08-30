from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.services import provider_runtime


class ProviderModelGatewayError(Exception):
    """模型网关调用失败。"""


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    """按候选键读取第一个非空字符串。"""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _to_int(value: Any) -> int:
    """安全转换为非负整数。"""

    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return max(result, 0)


@dataclass
class MediaGenerationOutput:
    """图像/媒体生成结果的统一结构。"""

    data: bytes | None = None
    b64: str = ""
    url: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    duration_ms: int = 0
    seed: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @classmethod
    def from_raw(cls, raw: Any) -> "MediaGenerationOutput":
        """把供应商返回收敛为媒体结果。"""

        if isinstance(raw, MediaGenerationOutput):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            return cls(data=bytes(raw), raw=raw)
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                raise ProviderModelGatewayError("媒体生成响应为空")
            if text.startswith(("http://", "https://")):
                return cls(url=text, raw=raw)
            return cls(b64=text, raw=raw)
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if item is not None:
                    return cls.from_raw(item)
            raise ProviderModelGatewayError("媒体生成响应为空列表")
        if isinstance(raw, dict):
            return cls._from_dict(raw)
        raise ProviderModelGatewayError("无法解析媒体生成响应")

    @classmethod
    def _from_dict(cls, payload: dict[str, Any]) -> "MediaGenerationOutput":
        """解析常见图像模型响应结构。"""

        container: dict[str, Any] = payload
        data_list = payload.get("data")
        if isinstance(data_list, list) and data_list and isinstance(data_list[0], dict):
            container = {**payload, **data_list[0]}
        raw_data = container.get("data")
        raw_bytes = bytes(raw_data) if isinstance(raw_data, (bytes, bytearray)) else None
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
        result = cls(
            data=raw_bytes,
            b64=_first_str(container, ("b64", "b64_json", "image_base64", "base64")),
            url=_first_str(container, ("url", "image_url", "output_url", "file_url")),
            mime_type=_first_str(container, ("mime_type", "content_type", "mimeType")),
            width=_to_int(container.get("width")),
            height=_to_int(container.get("height")),
            duration_ms=_to_int(container.get("duration_ms") or container.get("durationMs")),
            seed=str(container.get("seed") or ""),
            usage=usage,
            cost=cost,
            raw=payload,
        )
        if result.data is None and not result.b64 and not result.url:
            raise ProviderModelGatewayError("媒体生成响应缺少图像数据")
        return result



class ProviderModelGateway:
    """按模型 ID 调用文本/图像/语音/视频 生成的 Provider。"""

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.timeout = timeout

    async def generate_text(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> str:
        raw_output = await self.generate_response(
            model_id=model_id,
            messages=messages,
            provider_key=provider_key,
            input_values=input_values,
            **kwargs,
        )
        return self._extract_text(raw_output)

    async def generate_response(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            provider = provider_runtime.create_provider_for_model(
                model_id,
                provider_key=provider_key,
                input_values=input_values,
                timeout=self.timeout,
            )
            request = provider.generate(model_id=model_id, messages=messages, **kwargs)
            return await asyncio.wait_for(request, timeout=self.timeout) if self.timeout > 0 else await request
        except TimeoutError as exc:
            raise ProviderModelGatewayError(f"模型调用超时：{self.timeout}秒") from exc
        except ProviderModelGatewayError:
            raise
        except Exception as exc:
            raise ProviderModelGatewayError(str(exc)) from exc

    async def generate_stream(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        try:
            provider = provider_runtime.create_provider_for_model(
                model_id,
                provider_key=provider_key,
                input_values=input_values,
                timeout=self.timeout,
            )
            stream = getattr(provider, "generate_stream", None)
            if callable(stream):
                if self.timeout > 0:
                    # 流式调用采用"块间空闲超时"：每收到一个增量就重置计时。
                    # 只要模型持续产出就不会被总时长掐断——长剧本单集生成
                    # （上下文随已成集增长）整体耗时可远超单次超时阈值。
                    loop = asyncio.get_running_loop()
                    async with asyncio.timeout(self.timeout) as stream_timeout:
                        async for chunk in stream(model_id=model_id, messages=messages, **kwargs):
                            stream_timeout.reschedule(loop.time() + self.timeout)
                            text = str(chunk or "")
                            if text:
                                yield text
                else:
                    async for chunk in stream(model_id=model_id, messages=messages, **kwargs):
                        text = str(chunk or "")
                        if text:
                            yield text
                return

            raw_output = await self.generate_response(
                model_id=model_id,
                messages=messages,
                provider_key=provider_key,
                input_values=input_values,
                **kwargs,
            )
            yield self._extract_text(raw_output)
        except TimeoutError as exc:
            raise ProviderModelGatewayError(
                f"模型流式响应空闲超时：连续 {self.timeout} 秒未收到增量"
            ) from exc
        except ProviderModelGatewayError:
            raise
        except Exception as exc:
            raise ProviderModelGatewayError(str(exc)) from exc

    async def generate_image(
        self,
        *,
        model_id: str,
        prompt: str = "",
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> MediaGenerationOutput:
        """调用图像模型生成图像，返回归一化媒体结果。"""

        try:
            provider = provider_runtime.create_provider_for_model(
                model_id,
                provider_key=provider_key,
                input_values=input_values,
                timeout=self.timeout,
            )
            method = getattr(provider, "generate_image", None)
            if not callable(method):
                raise ProviderModelGatewayError(f"模型 {model_id} 不支持图像生成")
            request = method(model_id=model_id, prompt=prompt, **kwargs)
            raw = await asyncio.wait_for(request, timeout=self.timeout) if self.timeout > 0 else await request
        except TimeoutError as exc:
            raise ProviderModelGatewayError(f"图像生成超时：{self.timeout}秒") from exc
        except ProviderModelGatewayError:
            raise
        except Exception as exc:
            raise ProviderModelGatewayError(str(exc)) from exc
        return MediaGenerationOutput.from_raw(raw)

    async def edit_image(
        self,
        *,
        model_id: str,
        prompt: str = "",
        images: list[Any] | None = None,
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> MediaGenerationOutput:
        """调用图像模型基于参考图编辑图像，返回归一化媒体结果。"""

        try:
            provider = provider_runtime.create_provider_for_model(
                model_id,
                provider_key=provider_key,
                input_values=input_values,
                timeout=self.timeout,
            )
            method = getattr(provider, "edit_image", None)
            if not callable(method):
                raise ProviderModelGatewayError(f"模型 {model_id} 不支持图像编辑")
            request = method(model_id=model_id, prompt=prompt, images=images, **kwargs)
            raw = await asyncio.wait_for(request, timeout=self.timeout) if self.timeout > 0 else await request
        except TimeoutError as exc:
            raise ProviderModelGatewayError(f"图像编辑超时：{self.timeout}秒") from exc
        except ProviderModelGatewayError:
            raise
        except Exception as exc:
            raise ProviderModelGatewayError(str(exc)) from exc
        return MediaGenerationOutput.from_raw(raw)

    async def generate_video(
        self,
        *,
        model_id: str,
        prompt: str = "",
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> MediaGenerationOutput:
        """调用视频模型生成视频（含首尾帧/参考图输入），返回归一化媒体结果。"""

        try:
            provider = provider_runtime.create_provider_for_model(
                model_id,
                provider_key=provider_key,
                input_values=input_values,
                timeout=self.timeout,
            )
            method = getattr(provider, "generate_video", None)
            if not callable(method):
                raise ProviderModelGatewayError(f"模型 {model_id} 不支持视频生成")
            request = method(model_id=model_id, prompt=prompt, **kwargs)
            raw = await asyncio.wait_for(request, timeout=self.timeout) if self.timeout > 0 else await request
        except TimeoutError as exc:
            raise ProviderModelGatewayError(f"视频生成超时：{self.timeout}秒") from exc
        except ProviderModelGatewayError:
            raise
        except Exception as exc:
            raise ProviderModelGatewayError(str(exc)) from exc
        return MediaGenerationOutput.from_raw(raw)

    def _extract_text(self, raw_output: Any) -> str:
        if isinstance(raw_output, str):
            return self._ensure_text(raw_output)

        if isinstance(raw_output, dict):
            for key in ("output_text", "text"):
                value = raw_output.get(key)
                if isinstance(value, str):
                    return self._ensure_text(value)

            choices = raw_output.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    message = choice.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        return self._ensure_text(message["content"])
                    if isinstance(choice.get("text"), str):
                        return self._ensure_text(choice["text"])

        raise ProviderModelGatewayError("模型响应中没有可用文本")

    @staticmethod
    def _ensure_text(value: str) -> str:
        text = value.strip()
        if not text:
            raise ProviderModelGatewayError("模型响应文本为空")
        return text