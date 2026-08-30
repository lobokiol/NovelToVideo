from __future__ import annotations

import asyncio
import logging
import sys

from app.core.tasks.engine import default_async_task_engine
from app.core.tasks.worker import create_task_worker, print_task_worker_status


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


STATUS_COMMANDS = {"status", "inspect", "stats", "--status"}


async def main() -> None:
    """启动通用异步任务 Worker。"""
    config = default_async_task_engine.config
    _configure_logging(config.worker_log_enabled)
    default_async_task_engine.register_async_tasks()
    worker = create_task_worker(default_async_task_engine)
    await print_task_worker_status(worker)
    if _status_only():
        return
    await worker.run_forever()


def _status_only() -> bool:
    return len(sys.argv) > 1 and sys.argv[1].strip().lower() in STATUS_COMMANDS


def _configure_logging(worker_log_enabled: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if worker_log_enabled else logging.WARNING,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


if __name__ == "__main__":
    asyncio.run(main())
