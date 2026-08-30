from __future__ import annotations

from typing import Any

from app.core.base_provider import BaseProvider


PROVIDER_CONFIG = {
    "key": "custom",
    "protocol": "custom",
    "version": "1.0",
    "name": "自定义服务",
    "description": "自定义大模型服务配置。",
    "decs_url": "",
    "icon": "",
    "inputs": [
        {
            "key": "apiKey",
            "label": "API Key",
            "type": "password",
            "required": True,
        },
        {
            "key": "baseUrl",
            "label": "请求地址",
            "type": "url",
            "required": True,
        },
    ],
    "input_values": {"apiKey": "", "baseUrl": "https://api.example.com/v1"},
    "base_url": "https://api.example.com/v1",
    "enabled": False,
    "sort_order": 100,
    "models": [],
    "url": "",
}


class Text(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "text"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_text(model_id=model_id, **kwargs)

    async def generate_text(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的文本生成逻辑")


class Image(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "image"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_image(model_id=model_id, **kwargs)

    async def generate_image(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的图像生成逻辑")


class Video(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "video"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_video(model_id=model_id, **kwargs)

    async def generate_video(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的视频生成逻辑")


class TTS(BaseProvider):
    provider_key = PROVIDER_CONFIG["key"]
    provider_config = PROVIDER_CONFIG
    model_type = "tts"

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        return await self.generate_tts(model_id=model_id, **kwargs)

    async def generate_tts(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        raise NotImplementedError("请实现当前服务的语音生成逻辑")
