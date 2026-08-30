from __future__ import annotations

"""Video generation specifications shared by storyboard and provider services."""

from typing import Final


class VideoGenerationSpecError(ValueError):
    """The selected model, resolution, or ratio combination is unsupported."""


SEEDANCE_2_DIMENSIONS: Final[dict[str, dict[str, tuple[int, int]]]] = {
    "480p": {
        "16:9": (864, 496),
        "4:3": (752, 560),
        "1:1": (640, 640),
        "3:4": (560, 752),
        "9:16": (496, 864),
        "21:9": (992, 432),
    },
    "720p": {
        "16:9": (1280, 720),
        "4:3": (1112, 834),
        "1:1": (960, 960),
        "3:4": (834, 1112),
        "9:16": (720, 1280),
        "21:9": (1470, 630),
    },
    "1080p": {
        "16:9": (1920, 1080),
        "4:3": (1664, 1248),
        "1:1": (1440, 1440),
        "3:4": (1248, 1664),
        "9:16": (1080, 1920),
        "21:9": (2206, 946),
    },
    "4k": {
        "16:9": (3840, 2160),
        "4:3": (3326, 2494),
        "1:1": (2880, 2880),
        "3:4": (2494, 3326),
        "9:16": (2160, 3840),
        "21:9": (4398, 1886),
    },
}

_STANDARD_RESOLUTIONS: Final[tuple[str, ...]] = ("480p", "720p", "1080p", "4k")
_FAST_MINI_RESOLUTIONS: Final[tuple[str, ...]] = ("480p", "720p")
_IMAGE_SIZE_RESOLUTION: Final[dict[str, str]] = {
    "1K": "720p",
    "2K": "1080p",
    "4K": "4k",
}


def is_seedance_2_model(model_id: str) -> bool:
    normalized = (model_id or "").strip().lower()
    return normalized.startswith("doubao-seedance-2-0-")


def supported_seedance_resolutions(model_id: str) -> tuple[str, ...]:
    normalized = (model_id or "").strip().lower()
    if not is_seedance_2_model(normalized):
        return ()
    if "-fast-" in normalized or "-mini-" in normalized:
        return _FAST_MINI_RESOLUTIONS
    return _STANDARD_RESOLUTIONS


def seedance_dimensions(resolution: str, ratio: str) -> tuple[int, int]:
    resolved_resolution = (resolution or "").strip().lower()
    resolved_ratio = (ratio or "").strip()
    dimensions = SEEDANCE_2_DIMENSIONS.get(resolved_resolution, {}).get(resolved_ratio)
    if dimensions is None:
        raise VideoGenerationSpecError(
            f"Seedance 2.0 不支持分辨率 {resolution or '空'} 与比例 {ratio or '空'} 的组合"
        )
    return dimensions


def find_seedance_spec_by_dimensions(width: int, height: int) -> tuple[str, str] | None:
    expected = (int(width or 0), int(height or 0))
    for resolution, ratios in SEEDANCE_2_DIMENSIONS.items():
        for ratio, dimensions in ratios.items():
            if dimensions == expected:
                return resolution, ratio
    return None


def storyboard_image_size_to_resolution(model_id: str, image_size: str) -> str | None:
    if not is_seedance_2_model(model_id):
        return None
    normalized_size = (image_size or "").strip().upper()
    resolution = _IMAGE_SIZE_RESOLUTION.get(normalized_size)
    if resolution is None:
        raise VideoGenerationSpecError("分镜图分辨率仅支持 1K/2K/4K")
    supported = supported_seedance_resolutions(model_id)
    if resolution not in supported:
        raise VideoGenerationSpecError("当前 Seedance Fast/Mini 视频模型仅支持 1K 分镜图")
    return resolution


def clamp_seedance_duration(duration_seconds: int | None) -> int:
    value = int(duration_seconds or 0)
    if value <= 0:
        return 5
    return max(4, min(15, value))
