from __future__ import annotations


# 业务模块内声明异步任务列表时使用的属性名。
ASYNC_TASKS_ATTRIBUTE: str = "ASYNC_TASKS"

# 默认不加载任何业务异步任务模块，具体项目通过配置显式声明。
DEFAULT_ASYNC_TASK_MODULES: tuple[str, ...] = ()
# Redis Stream 默认名称。
DEFAULT_TASK_STREAM_NAME: str = "task:stream"
# Redis Stream 默认消费组名称。
DEFAULT_TASK_CONSUMER_GROUP: str = "task-workers"
# Redis Stream 默认最大保留消息数量。
DEFAULT_TASK_STREAM_MAX_LEN: int = 10000

# Worker 默认消费者名称，空值表示启动时自动生成。
DEFAULT_TASK_WORKER_CONSUMER_NAME: str = ""
# Worker 默认单批读取消息数量。根据服务器实际配置而定
DEFAULT_TASK_WORKER_BATCH_SIZE: int = 4
# Worker 默认阻塞读取毫秒数。
DEFAULT_TASK_WORKER_BLOCK_MS: int = 2000
# Worker 默认空闲休眠秒数。
DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS: float = 0.5
# Worker 默认最大并发处理数量。根据服务器实际配置而定。
DEFAULT_TASK_WORKER_MAX_CONCURRENCY: int = 4
# 单个异步任务子项默认执行超时秒数。
DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS: float = 3600.0
# Worker 默认开启任务执行日志。
DEFAULT_TASK_WORKER_LOG_ENABLED: bool = True
# Worker 默认心跳刷新间隔秒数。
DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS: float = 30.0
# 异步任务默认最大重试次数。
DEFAULT_TASK_WORKER_MAX_RETRIES: int = 3
# 异步任务默认重试基础退避秒数。
DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS: float = 30.0
# Worker 默认优雅退出等待秒数。
DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS: float = 30.0
# 运行中任务默认失联判定秒数。
DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS: float = 600.0
# OrphanScavenger 默认扫描间隔秒数。
DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS: float = 30.0

# 媒体生成任务默认通用超时秒数。
DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS: float = 1800.0
# 图片生成任务默认超时秒数。
DEFAULT_IMAGE_GENERATION_TIMEOUT_SECONDS: float = 600.0
# 视频生成任务默认超时秒数。
DEFAULT_VIDEO_GENERATION_TIMEOUT_SECONDS: float = 3600.0
# 媒体生成任务默认异步轮询间隔秒数。
DEFAULT_MEDIA_GENERATION_POLL_INTERVAL_SECONDS: float = 5.0
# 媒体生成任务默认最大并发数量。
DEFAULT_MEDIA_GENERATION_MAX_CONCURRENCY: int = 2

# 任务子项入队时写入 Redis Stream 的事件名。
TASK_STREAM_EVENT_ITEM_QUEUED: str = "task.item.queued"
# Redis Stream 任务消息结构版本号。
TASK_STREAM_MESSAGE_VERSION: str = "1"
