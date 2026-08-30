from __future__ import annotations

from typing import Any

import pytest

from app.services import agent_gateway


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_provider_model_gateway_edit_image_delegates_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Image edit calls should use the provider edit_image API and normalize output."""

    calls: dict[str, Any] = {}

    class FakeProvider:
        async def edit_image(
            self,
            *,
            model_id: str | None = None,
            prompt: str = "",
            images: list[Any] | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            calls["model_id"] = model_id
            calls["prompt"] = prompt
            calls["images"] = images
            calls["kwargs"] = kwargs
            return {
                "data": [
                    {
                        "b64_json": "ZmFrZS1pbWFnZQ==",
                        "mime_type": "image/png",
                        "width": 16,
                        "height": 9,
                    }
                ]
            }

    def fake_create_provider_for_model(
        model_id: str,
        *,
        provider_key: str | None = None,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> FakeProvider:
        calls["provider_model_id"] = model_id
        calls["provider_key"] = provider_key
        calls["input_values"] = input_values
        calls["timeout"] = timeout
        return FakeProvider()

    monkeypatch.setattr(
        agent_gateway.provider_runtime,
        "create_provider_for_model",
        fake_create_provider_for_model,
    )

    output = await agent_gateway.ProviderModelGateway(timeout=12.5).edit_image(
        model_id="image-model",
        provider_key="custom-provider",
        input_values={"apiKey": "secret"},
        prompt="turn the reference into a variant",
        images=[{"data": b"reference", "mime_type": "image/png"}],
        image_size="1K",
    )

    assert output.b64 == "ZmFrZS1pbWFnZQ=="
    assert output.mime_type == "image/png"
    assert output.width == 16
    assert output.height == 9
    assert calls == {
        "provider_model_id": "image-model",
        "provider_key": "custom-provider",
        "input_values": {"apiKey": "secret"},
        "timeout": 12.5,
        "model_id": "image-model",
        "prompt": "turn the reference into a variant",
        "images": [{"data": b"reference", "mime_type": "image/png"}],
        "kwargs": {"image_size": "1K"},
    }
