from __future__ import annotations

from app.schemas.provider import ProviderConfig
from app.services.provider_runtime import OpenAICompatibleImageProvider, _build_image_edit_files


def _image_provider() -> OpenAICompatibleImageProvider:
    return OpenAICompatibleImageProvider(
        ProviderConfig(
            key="openai_test",
            protocol="openai",
            name="OpenAI Test",
            base_url="https://example.test/v1",
            input_values={"apiKey": "test-key"},
        )
    )


def test_build_image_edit_files_uses_array_field_for_multiple_reference_images() -> None:
    """OpenAI 兼容的多图编辑应使用 image[] 发送参考图。"""

    files = _build_image_edit_files(
        [
            {"filename": "front.png", "mime_type": "image/png", "data": b"front"},
            {"filename": "side.png", "mime_type": "image/png", "data": b"side"},
        ]
    )

    assert [field_name for field_name, _ in files] == ["image[]", "image[]"]
    assert files[0][1] == ("front.png", b"front", "image/png")
    assert files[1][1] == ("side.png", b"side", "image/png")


def test_build_image_edit_files_keeps_plain_image_field_for_single_reference_image() -> None:
    """单图编辑继续使用 Image API 的普通 image 字段。"""

    files = _build_image_edit_files(
        [{"filename": "reference.png", "mime_type": "image/png", "data": b"reference"}]
    )

    assert [field_name for field_name, _ in files] == ["image"]


def test_build_edit_request_passes_input_fidelity_to_image_edits() -> None:
    """图片编辑应把保真度控制参数透传到 provider 请求。"""

    payload, _files, _headers, _url = _image_provider()._build_edit_request(
        model_id="gpt-image-1",
        prompt="keep the same person and update the outfit",
        images=[{"filename": "reference.png", "mime_type": "image/png", "data": b"reference"}],
        input_fidelity="high",
    )

    assert payload["input_fidelity"] == "high"


def test_build_request_omits_response_format_for_gpt_image_models() -> None:
    """GPT Image 系列的 images 接口不接受 response_format，默认值必须省略。"""

    payload, _headers, _url = _image_provider()._build_request(
        model_id="gpt-image-1",
        prompt="a red apple",
    )

    assert "response_format" not in payload


def test_build_edit_request_omits_response_format_for_gpt_image_models() -> None:
    """GPT Image 系列的图片编辑请求同样不携带 response_format。"""

    payload, _files, _headers, _url = _image_provider()._build_edit_request(
        model_id="gpt-image-1-mini",
        prompt="update the outfit",
        images=[{"filename": "reference.png", "mime_type": "image/png", "data": b"reference"}],
    )

    assert "response_format" not in payload


def test_build_request_keeps_b64_json_default_for_other_models() -> None:
    """非 GPT Image 模型继续默认请求 b64_json，保证结果可直接落盘。"""

    payload, _headers, _url = _image_provider()._build_request(
        model_id="doubao-seedream-4-0",
        prompt="a red apple",
    )

    assert payload["response_format"] == "b64_json"

    edit_payload, _files, _headers, _url = _image_provider()._build_edit_request(
        model_id="doubao-seededit-3-0",
        prompt="update the outfit",
        images=[{"filename": "reference.png", "mime_type": "image/png", "data": b"reference"}],
    )

    assert edit_payload["response_format"] == "b64_json"
