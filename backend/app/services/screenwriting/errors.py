"""剧本创作服务层共享异常。

被 chat 与会话状态等子模块共同依赖，避免互相导入产生循环。
"""

from __future__ import annotations


class ScreenwritingServiceError(Exception):
    """剧本创作服务层基础异常。"""


class ScreenwritingValidationError(ScreenwritingServiceError):
    """剧本创作请求不合法。"""