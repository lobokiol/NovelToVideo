"""Harness 模型网关适配器。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.harness.runtime.agent import HarnessAgentError
from app.services.agent_gateway import ProviderModelGateway


class ModelGatewayAdapter:
    """把项目模型网关适配给 Harness 运行时。"""

    def __init__(
        self,
        *,
        gateway: ProviderModelGateway | Any | None = None,
        default_model_id: str | None = None,
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
    ) -> None:
        self.gateway = gateway or ProviderModelGateway(timeout=settings.model_request_timeout_seconds)
        self.default_model_id = (default_model_id or "").strip()
        self.provider_key = provider_key
        self.input_values = input_values

    async def generate_response(
        self,
        *,
        messages: list[dict[str, Any]],
        model_id: str | None = None,
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        resolved_model_id = self._resolve_model_id(model_id)
        return await self.gateway.generate_response(
            model_id=resolved_model_id,
            messages=messages,
            provider_key=self.provider_key if provider_key is None else provider_key,
            input_values=self.input_values if input_values is None else input_values,
            **kwargs,
        )

    async def generate_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        model_id: str | None = None,
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        resolved_model_id = self._resolve_model_id(model_id)
        async for chunk in self.gateway.generate_stream(
            model_id=resolved_model_id,
            messages=messages,
            provider_key=self.provider_key if provider_key is None else provider_key,
            input_values=self.input_values if input_values is None else input_values,
            **kwargs,
        ):
            text = str(chunk or "")
            if text:
                yield text

    def _resolve_model_id(self, model_id: str | None) -> str:
        resolved_model_id = (model_id or self.default_model_id).strip()
        if not resolved_model_id:
            raise HarnessAgentError("model_id 不能为空")
        return resolved_model_id
