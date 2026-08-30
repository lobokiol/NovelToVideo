from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition


async def echo_task(context: Any) -> dict[str, Any]:
    """用于验证通用异步任务链路的演示任务处理器。

    Args:
        context: Worker 传入的任务执行上下文，实际类型为 TaskWorkerContext。
            context.session 是当前任务处理过程使用的数据库会话。
            context.record 是从 Redis Stream 读取到的原始任务记录。
            context.message 是 context.record.message 的快捷访问，包含 task_type、item_type、payload 等任务消息字段。
            context.worker_id 是当前执行该任务的 Worker 标识。

    Returns:
        dict[str, Any]: 写回任务子项 result 字段的执行结果。
    """
    return {
        "worker_id": context.worker_id,
        "payload": context.message.payload,
    }


ASYNC_TASKS = (
    AsyncTaskDefinition("demo.echo", echo_task),
)