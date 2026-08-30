from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pprint import pprint
from typing import Any, ClassVar, Mapping


class ProviderError(Exception):
    """Provider 适配器示例的基础异常。"""


class ProviderConfigurationError(ProviderError):
    """Provider 配置或模型配置不合法时抛出。"""


class ProviderCapabilityError(ProviderError):
    """Provider 不支持当前模型能力时抛出。"""


class BaseProvider(ABC):
    """厂商适配器的统一基类。"""

    provider_key: ClassVar[str] = ""
    provider_config: ClassVar[Mapping[str, Any]] = {}
    model_type: ClassVar[str] = ""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        input_values: Mapping[str, str] | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        config_values = dict(self.provider_config.get("input_values") or {})
        if input_values:
            config_values.update(input_values)
        if api_key is not None:
            config_values["apiKey"] = api_key
        if base_url is not None:
            config_values["baseUrl"] = base_url

        self.input_values = config_values
        self.api_key = str(config_values.get("apiKey", ""))
        self.base_url = self._resolve_base_url(config_values)
        self.timeout = timeout
        self._client = client

    @property
    def key(self) -> str:
        return self.provider_key or str(self.provider_config.get("key", ""))

    @property
    def models(self) -> list[dict[str, Any]]:
        return list(self.provider_config.get("models") or [])

    @property
    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderConfigurationError("缺少 API Key")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @abstractmethod
    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        """通过具体能力适配器生成内容。"""

    async def generate_text(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise ProviderCapabilityError(f"{self.key} 不支持文本生成")

    async def generate_image(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise ProviderCapabilityError(f"{self.key} 不支持图像生成")

    async def generate_video(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise ProviderCapabilityError(f"{self.key} 不支持视频生成")

    async def generate_tts(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise ProviderCapabilityError(f"{self.key} 不支持语音生成")

    def select_model_id(self, model_id: str | None = None) -> str:
        if model_id:
            return model_id
        for model in self.models:
            if model.get("model_type") == self.model_type and model.get("model_id"):
                return str(model["model_id"])
        raise ProviderConfigurationError(f"{self.key} 未配置 {self.model_type} 模型")

    def _resolve_base_url(self, input_values: Mapping[str, str]) -> str:
        raw_base_url = (
            input_values.get("baseUrl")
            or input_values.get("base_url")
            or str(self.provider_config.get("base_url", ""))
        )
        return raw_base_url.rstrip("/")

    def result(self, *, model_id: str | None, adapter_step: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "provider_key": self.key,
            "model_type": self.model_type,
            "model_id": self.select_model_id(model_id),
            "base_url": self.base_url,
            "adapter_step": adapter_step,
            "request_kwargs": kwargs,
            "note": "仅用于演示：不会发送真实远程模型请求。",
        }

# 模拟：providers/openai.py的PROVIDER_CONFIG
OPENAI_PROVIDER_CONFIG = {
    "key": "openai",
    "protocol": "openai",
    "version": "1.0",
    "name": "OpenAI",
    "input_values": {"apiKey": "", "baseUrl": "https://api.openai.example/v1"},
    "base_url": "https://api.openai.example/v1",
    "enabled": True,
    "models": [
        {"name": "GPT Demo", "model_id": "gpt-demo", "model_type": "text", "modes": ["text"]},
    ],
}

# 模拟：providers/qwen.py的PROVIDER_CONFIG
QWEN_PROVIDER_CONFIG = {
    "key": "qwen",
    "protocol": "qwen",
    "version": "1.0",
    "name": "Qwen",
    "input_values": {"apiKey": "", "baseUrl": "https://dashscope.example/compatible-mode/v1"},
    "base_url": "https://dashscope.example/compatible-mode/v1",
    "enabled": True,
    "models": [
        {"name": "Qwen Text Demo", "model_id": "qwen-text-demo", "model_type": "text", "modes": ["text"]},
        {"name": "Qwen Image Demo", "model_id": "qwen-image-demo", "model_type": "image", "modes": ["text-to-image"]},
    ],
}

# 模拟：providers/volcengine.py的PROVIDER_CONFIG
VOLCENGINE_PROVIDER_CONFIG = {
    "key": "volcengine",
    "protocol": "volcengine",
    "version": "1.0",
    "name": "Volcengine",
    "input_values": {"apiKey": "", "baseUrl": "https://ark.example/api/v3"},
    "base_url": "https://ark.example/api/v3",
    "enabled": True,
    "models": [
        {"name": "Volcengine Video Demo", "model_id": "volc-video-demo", "model_type": "video", "modes": ["text-to-video"]},
    ],
}


class OpenAIText(BaseProvider):
    """对应 providers/openai.py 中的 Text 适配器。"""

    provider_key = OPENAI_PROVIDER_CONFIG["key"]
    provider_config = OPENAI_PROVIDER_CONFIG
    model_type = "text"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_text(model_id=model_id, **kwargs)

    async def generate_text(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return self.result(model_id=model_id, adapter_step="适配 OpenAI 兼容文本协议", **kwargs)


class QwenText(BaseProvider):
    """对应 providers/qwen.py 中的 Text 适配器。"""

    provider_key = QWEN_PROVIDER_CONFIG["key"]
    provider_config = QWEN_PROVIDER_CONFIG
    model_type = "text"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_text(model_id=model_id, **kwargs)

    async def generate_text(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return self.result(model_id=model_id, adapter_step="适配 Qwen 文本模型协议", **kwargs)


class QwenImage(BaseProvider):
    """对应 providers/qwen.py 中的 Image 适配器。"""

    provider_key = QWEN_PROVIDER_CONFIG["key"]
    provider_config = QWEN_PROVIDER_CONFIG
    model_type = "image"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_image(model_id=model_id, **kwargs)

    async def generate_image(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return self.result(model_id=model_id, adapter_step="适配 Qwen 图像任务协议", **kwargs)


class VolcengineVideo(BaseProvider):
    """对应 volcengine.py 中的 Video 适配器。"""

    provider_key = VOLCENGINE_PROVIDER_CONFIG["key"]
    provider_config = VOLCENGINE_PROVIDER_CONFIG
    model_type = "video"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_video(model_id=model_id, **kwargs)

    async def generate_video(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return self.result(model_id=model_id, adapter_step="适配厂商自定义异步视频任务", **kwargs)


PROVIDER_CONFIGS = {
    OPENAI_PROVIDER_CONFIG["key"]: OPENAI_PROVIDER_CONFIG,
    QWEN_PROVIDER_CONFIG["key"]: QWEN_PROVIDER_CONFIG,
    VOLCENGINE_PROVIDER_CONFIG["key"]: VOLCENGINE_PROVIDER_CONFIG,
}

PROVIDER_CLASSES: dict[tuple[str, str], type[BaseProvider]] = {
    ("openai", "text"): OpenAIText,
    ("qwen", "text"): QwenText,
    ("qwen", "image"): QwenImage,
    ("volcengine", "video"): VolcengineVideo,
}


class ProviderRuntime:
    """Provider Runtime：连接配置、适配器类和上层调用方。"""

    def __init__(
        self,
        provider_configs: Mapping[str, Mapping[str, Any]],
        provider_classes: Mapping[tuple[str, str], type[BaseProvider]],
    ) -> None:
        self.provider_configs = provider_configs
        self.provider_classes = provider_classes

    def list_provider_configs(self) -> list[Mapping[str, Any]]:
        """列出所有 Provider 配置。"""
        return list(self.provider_configs.values())

    def get_provider_config(self, provider_key: str) -> Mapping[str, Any]:
        """按 provider_key 读取单个 Provider 配置。"""
        try:
            return self.provider_configs[provider_key]
        except KeyError as exc:
            raise ProviderConfigurationError(f"未知 Provider：{provider_key}") from exc

    def get_provider_class(self, provider_key: str, model_type: str) -> type[BaseProvider]:
        """根据 provider_key 和 model_type 定位适配器类。"""
        config = self.get_provider_config(provider_key)
        if not config.get("enabled"):
            raise ProviderConfigurationError(f"Provider 未启用：{provider_key}")
        try:
            return self.provider_classes[(provider_key, model_type)]
        except KeyError as exc:
            raise ProviderCapabilityError(f"{provider_key} 不支持 {model_type}") from exc

    def create_provider(
        self,
        provider_key: str,
        model_type: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        input_values: Mapping[str, str] | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> BaseProvider:
        """创建具体厂商和能力类型对应的适配器实例。"""
        provider_class = self.get_provider_class(provider_key, model_type)
        return provider_class(
            api_key=api_key,
            base_url=base_url,
            input_values=input_values,
            timeout=timeout,
            client=client,
        )

    def create_provider_for_model(
        self,
        model_id: str,
        *,
        provider_key: str | None = None,
        input_values: Mapping[str, str] | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> BaseProvider:
        """根据 model_id 查找模型配置，并创建匹配的适配器实例。"""
        configs = [self.get_provider_config(provider_key)] if provider_key else self.list_provider_configs()
        for config in configs:
            if not config.get("enabled"):
                continue
            for model in config.get("models", []):
                if model.get("model_id") == model_id:
                    return self.create_provider(
                        str(config["key"]),
                        str(model["model_type"]),
                        input_values=input_values,
                        timeout=timeout,
                        client=client,
                    )
        raise ProviderConfigurationError(f"未配置模型：{model_id}")

    async def generate(
        self,
        provider_key: str,
        model_type: str,
        *,
        model_id: str | None = None,
        input_values: Mapping[str, str] | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """统一生成入口：先创建适配器，再委托给适配器执行。"""
        provider = self.create_provider(
            provider_key,
            model_type,
            input_values=input_values,
            timeout=timeout,
            client=client,
        )
        return await provider.generate(model_id=model_id, **kwargs)


DEFAULT_RUNTIME = ProviderRuntime(PROVIDER_CONFIGS, PROVIDER_CLASSES)


def list_provider_configs() -> list[Mapping[str, Any]]:
    return DEFAULT_RUNTIME.list_provider_configs()


def get_provider_config(provider_key: str) -> Mapping[str, Any]:
    return DEFAULT_RUNTIME.get_provider_config(provider_key)


def get_provider_class(provider_key: str, model_type: str) -> type[BaseProvider]:
    return DEFAULT_RUNTIME.get_provider_class(provider_key, model_type)


def create_provider(
    provider_key: str,
    model_type: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    input_values: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    client: Any | None = None,
) -> BaseProvider:
    return DEFAULT_RUNTIME.create_provider(
        provider_key,
        model_type,
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
    input_values: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    client: Any | None = None,
) -> BaseProvider:
    return DEFAULT_RUNTIME.create_provider_for_model(
        model_id,
        provider_key=provider_key,
        input_values=input_values,
        timeout=timeout,
        client=client,
    )


async def generate(
    provider_key: str,
    model_type: str,
    *,
    model_id: str | None = None,
    input_values: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    client: Any | None = None,
    **kwargs: Any,
) -> Any:
    return await DEFAULT_RUNTIME.generate(
        provider_key,
        model_type,
        model_id=model_id,
        input_values=input_values,
        timeout=timeout,
        client=client,
        **kwargs,
    )


async def main() -> None:
    runtime = ProviderRuntime(PROVIDER_CONFIGS, PROVIDER_CLASSES)
    text_result = await runtime.generate(
        "openai",
        "text",
        model_id="gpt-demo",
        input_values={"apiKey": "demo-key"},
        prompt="hello",
        messages=[]
    )
    
    video_provider = runtime.create_provider_for_model(
        "volc-video-demo",
        provider_key="volcengine",
        input_values={"apiKey": "api-key"},
    )
    video_result = await video_provider.generate(prompt="make a short video")

    pprint(text_result)
    pprint(video_result)


if __name__ == "__main__":
    asyncio.run(main())
