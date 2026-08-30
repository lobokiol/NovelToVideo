from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """获取当前 UTC 时间。

    Returns:
        datetime: 带时区信息的 UTC 当前时间。
    """
    return datetime.now(UTC)