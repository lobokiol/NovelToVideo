from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.core.rag.constants import (
    DEFAULT_SCREENWRITING_RAG_CHUNK_CHARS,
    DEFAULT_SCREENWRITING_RAG_CHUNK_OVERLAP,
    DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE,
    DEFAULT_SCREENWRITING_RAG_INTENT_ENABLED,
    DEFAULT_SCREENWRITING_RAG_INTENT_TIMEOUT_SECONDS,
    DEFAULT_SCREENWRITING_RAG_MIN_VECTOR_SCORE,
    DEFAULT_SCREENWRITING_RAG_RETRIEVE_LIMIT,
    DEFAULT_SCREENWRITING_RAG_VECTOR_STORE_ROOT,
    DEFAULT_SCREENWRITING_RAG_VISUAL_INTENT_KEYWORDS,
    DEFAULT_SCREENWRITING_RAG_WARMUP_DOCUMENT_BATCH_SIZE,
)
from app.core.tasks.constants import (
    DEFAULT_ASYNC_TASK_MODULES,
    DEFAULT_IMAGE_GENERATION_TIMEOUT_SECONDS,
    DEFAULT_MEDIA_GENERATION_MAX_CONCURRENCY,
    DEFAULT_MEDIA_GENERATION_POLL_INTERVAL_SECONDS,
    DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS,
    DEFAULT_TASK_CONSUMER_GROUP,
    DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS,
    DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS,
    DEFAULT_TASK_STREAM_MAX_LEN,
    DEFAULT_TASK_STREAM_NAME,
    DEFAULT_TASK_WORKER_BATCH_SIZE,
    DEFAULT_TASK_WORKER_BLOCK_MS,
    DEFAULT_TASK_WORKER_CONSUMER_NAME,
    DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS,
    DEFAULT_TASK_WORKER_LOG_ENABLED,
    DEFAULT_TASK_WORKER_MAX_CONCURRENCY,
    DEFAULT_TASK_WORKER_MAX_RETRIES,
    DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS,
    DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
    DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS,
    DEFAULT_VIDEO_GENERATION_TIMEOUT_SECONDS,
)

# 提取项目工程的根目录路径，拼接.env的路径并加载.env中的环境配置
BASE_DIR = Path(__file__).resolve().parents[3]

# 拼接路径
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool) -> bool:
    """从环境变量解析布尔值。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int_tuple(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    """从逗号分隔的环境变量解析整数元组。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    items = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    return items or default


def _env_str_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """从逗号分隔的环境变量解析字符串元组。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


# frozen=True 冻结属性值，不允许配置类Settings实例化以后，被其他地方的程序修改属性值
@dataclass(frozen=True)
class Settings(object):
    """项目运行时配置对象。"""
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "App"))  # 应用名称
    app_description: str = field(default_factory=lambda: os.getenv("APP_DESCRIPTION", "App description"))  # 应用描述
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))  # 应用运行环境
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))  # 后端监听地址
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))  # 后端监听端口
    reload: bool = field(default_factory=lambda: _env_bool("RELOAD", False))  # 是否开启代码热重载（仅开发用，RELOAD=true 开启）
    api_prefix: str = field(default_factory=lambda: os.getenv("API_PREFIX", "/api"))  # API 路由前缀
    oss_root: str = field(default_factory=lambda: os.getenv("OSS_ROOT", "./data/oss"))  # 本地 OSS 根目录
    db_engine: str = field(default_factory=lambda: os.getenv("DB_ENGINE", "postgres"))  # 数据库类型
    db_driver: str = field(default_factory=lambda: os.getenv("DB_DRIVER", "psycopg"))  # 数据库驱动
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "127.0.0.1"))  # 数据库主机
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))  # 数据库端口
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "anonforge"))  # 数据库名称
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "anonforge"))  # 数据库用户名
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "anonforge"))  # 数据库密码
    db_sqlite_path: str = field(default_factory=lambda: os.getenv("DB_SQLITE_PATH", "./data/app.db"))  # SQLite 数据库文件路径
    tz: str = field(default_factory=lambda: os.getenv("TZ", "Asia/Shanghai"))  # 默认时区
    postgres_image: str = field(default_factory=lambda: os.getenv("POSTGRES_IMAGE", "postgres:18-alpine"))  # PostgreSQL 容器镜像
    postgres_container_name: str = field(default_factory=lambda: os.getenv("POSTGRES_CONTAINER_NAME", "anonforge_dev_postgres"))  # PostgreSQL 容器名称
    postgres_host_port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_HOST_PORT", "5432")))  # PostgreSQL 宿主机端口
    db_data_path: str = field(default_factory=lambda: os.getenv("DB_DATA_PATH", "./postgres/data"))  # 数据库数据目录
    db_healthcheck_interval: str = field(default_factory=lambda: os.getenv("DB_HEALTHCHECK_INTERVAL", "10s"))  # 数据库健康检查间隔
    db_healthcheck_timeout: str = field(default_factory=lambda: os.getenv("DB_HEALTHCHECK_TIMEOUT", "5s"))  # 数据库健康检查超时
    db_healthcheck_retries: int = field(default_factory=lambda: int(os.getenv("DB_HEALTHCHECK_RETRIES", "5")))  # 数据库健康检查重试次数

    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "127.0.0.1"))  # Redis 主机
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))  # Redis 端口
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))  # Redis 数据库编号
    redis_container_name: str = field(default_factory=lambda: os.getenv("REDIS_CONTAINER_NAME", "anonforge_dev_redis"))  # Redis 容器名称
    redis_data_path: str = field(default_factory=lambda: os.getenv("REDIS_DATA_PATH", "./redis/data"))  # Redis 数据目录
    redis_healthcheck_interval: str = field(default_factory=lambda: os.getenv("REDIS_HEALTHCHECK_INTERVAL", "10s"))  # Redis 健康检查间隔
    redis_healthcheck_timeout: str = field(default_factory=lambda: os.getenv("REDIS_HEALTHCHECK_TIMEOUT", "5s"))  # Redis 健康检查超时
    redis_healthcheck_retries: int = field(default_factory=lambda: int(os.getenv("REDIS_HEALTHCHECK_RETRIES", "3")))  # Redis 健康检查重试次数

    redis_token_key_prefix: str = field(default_factory=lambda: os.getenv("REDIS_TOKEN_KEY_PREFIX", "auth:token:"))  # Redis 令牌缓存键前缀
    redis_task_stream_name: str = field(default_factory=lambda: os.getenv("REDIS_TASK_STREAM_NAME", DEFAULT_TASK_STREAM_NAME))  # 异步任务 Redis Stream 名称
    redis_task_consumer_group: str = field(default_factory=lambda: os.getenv("REDIS_TASK_CONSUMER_GROUP", DEFAULT_TASK_CONSUMER_GROUP))  # 异步任务 Redis Stream 消费组
    redis_task_stream_max_len: int = field(default_factory=lambda: int(os.getenv("REDIS_TASK_STREAM_MAX_LEN", DEFAULT_TASK_STREAM_MAX_LEN)))  # 异步任务 Redis Stream 最大保留长度
    async_task_modules: tuple[str, ...] = field( default_factory=lambda: tuple( item.strip() for item in os.getenv("ASYNC_TASK_MODULES", ",".join(DEFAULT_ASYNC_TASK_MODULES)).split(",") if item.strip() ) )  # 异步任务业务模块列表
    async_task_worker_consumer_name: str = field(default_factory=lambda: os.getenv("ASYNC_TASK_WORKER_CONSUMER_NAME", DEFAULT_TASK_WORKER_CONSUMER_NAME))  # 异步任务 Worker 消费者名称
    async_task_worker_batch_size: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_BATCH_SIZE", DEFAULT_TASK_WORKER_BATCH_SIZE)))  # 异步任务 Worker 单批读取数量
    async_task_worker_block_ms: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_BLOCK_MS", DEFAULT_TASK_WORKER_BLOCK_MS)))  # 异步任务 Worker 阻塞读取毫秒数
    async_task_worker_idle_sleep_seconds: float = field( default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_IDLE_SLEEP_SECONDS", DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS)) )  # 异步任务 Worker 空闲休眠秒数
    async_task_worker_max_concurrency: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_MAX_CONCURRENCY", DEFAULT_TASK_WORKER_MAX_CONCURRENCY)))  # 异步任务 Worker 最大并发处理数量
    async_task_worker_task_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_TASK_TIMEOUT_SECONDS", DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS)))  # 异步任务单个子项执行超时秒数
    async_task_worker_log_enabled: bool = field(default_factory=lambda: _env_bool("ASYNC_TASK_WORKER_LOG_ENABLED", DEFAULT_TASK_WORKER_LOG_ENABLED))  # 异步任务 Worker 是否打印任务执行日志
    async_task_worker_heartbeat_interval_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS", DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS)))  # 异步任务 Worker 心跳刷新间隔秒数
    async_task_worker_max_retries: int = field(default_factory=lambda: int(os.getenv("ASYNC_TASK_WORKER_MAX_RETRIES", DEFAULT_TASK_WORKER_MAX_RETRIES)))  # 异步任务默认最大重试次数
    async_task_worker_retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_RETRY_BACKOFF_SECONDS", DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS)))  # 异步任务重试基础退避秒数
    async_task_worker_shutdown_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS", DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS)))  # 异步任务 Worker 优雅退出等待秒数
    async_task_stale_running_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_STALE_RUNNING_TIMEOUT_SECONDS", DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS)))  # 异步任务运行中状态失联判定秒数
    async_task_orphan_scavenger_interval_seconds: float = field(default_factory=lambda: float(os.getenv("ASYNC_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS", DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS)))  # 异步任务孤儿扫描间隔秒数
    algorithm: str = field(default_factory=lambda: os.getenv("ALGORITHM", "HS256"))  # JWT 签名算法
    access_token_expire_seconds: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS", "900")))  # 访问令牌有效秒数
    refresh_token_expire_seconds: int = field(default_factory=lambda: int(os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", "604800")))  # 刷新令牌有效秒数
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-secret-key"))  # 应用密钥

    user_default_admin_name: str = field(default_factory=lambda: os.getenv("USER_DEFAULT_ADMIN_NAME", "admin"))  # 默认管理员用户名
    user_default_admin_password: str = field(default_factory=lambda: os.getenv("USER_DEFAULT_ADMIN_PASSWORD", "admin123"))  # 默认管理员密码

    visual_style_root: str = field(default_factory=lambda: os.getenv("VISUAL_STYLE_ROOT", "./data/skills/art_list"))  # 视觉风格资源根目录
    director_manual_root: str = field(default_factory=lambda: os.getenv("DIRECTOR_MANUAL_ROOT", "./data/skills/director_manual"))  # 导演手册资源根目录
    skills_root: str = field(default_factory=lambda: os.getenv("SKILLS_ROOT", "./data/skills"))  # 技能文档根目录
    script_prompts_root: str = field(default_factory=lambda: os.getenv("SCRIPT_PROMPTS_ROOT", "./data/script"))  # 剧本创作工具提示词根目录（供 web 端可视化编辑）
    chapter_event_extraction_prompt_name: str = field( default_factory=lambda: os.getenv("CHAPTER_EVENT_EXTRACTION_PROMPT_NAME", "chapter_event_extraction") )  # 章节事件提取提示词名称
    asset_extraction_prompt_name: str = field(default_factory=lambda: os.getenv("ASSET_EXTRACTION_PROMPT_NAME", "asset_extraction"))  # 资产抽取提示词名称
    asset_autocomplete_prompt_name: str = field(default_factory=lambda: os.getenv("ASSET_AUTOCOMPLETE_PROMPT_NAME", "asset_autocomplete"))  # 资产描述补全提示词名称
    asset_image_prompt_name: str = field(default_factory=lambda: os.getenv("ASSET_IMAGE_PROMPT_NAME", "asset_image_prompt"))  # 资产生图专业提示词合成提示词名称
    media_root: str = field(default_factory=lambda: os.getenv("MEDIA_ROOT", "./data/media"))  # 统一媒体中枢本地存储根目录
    media_storage_backend: str = field(default_factory=lambda: os.getenv("MEDIA_STORAGE_BACKEND", "local"))  # 媒体存储后端：local/s3/oss
    media_public_base_url: str = field(default_factory=lambda: os.getenv("MEDIA_PUBLIC_BASE_URL", ""))  # 本地媒体公网基地址，留空回退内容接口
    media_s3_bucket: str = field(default_factory=lambda: os.getenv("MEDIA_S3_BUCKET", "nonaforage"))  # S3 媒体存储桶
    media_s3_endpoint_url: str = field(default_factory=lambda: os.getenv("MEDIA_S3_ENDPOINT_URL", "oss-cn-beijing.aliyuncs.com"))  # S3 兼容端点地址
    media_s3_region: str = field(default_factory=lambda: os.getenv("MEDIA_S3_REGION", "cn-beijing"))  # S3 区域
    media_s3_access_key_id: str = field(default_factory=lambda: os.getenv("MEDIA_S3_ACCESS_KEY_ID", "LTAI5t8UdeQmMuLrbjZd5tdP"))  # S3 访问密钥 ID
    media_s3_secret_access_key: str = field(default_factory=lambda: os.getenv("MEDIA_S3_SECRET_ACCESS_KEY", "PQhqD5kBVuQnCp1rewtvi08IDZXiGR"))  # S3 访问密钥
    media_s3_public_base_url: str = field(default_factory=lambda: os.getenv("MEDIA_S3_PUBLIC_BASE_URL", "nonaforage.oss-accelerate.aliyuncs.com"))  # S3 公网基地址（CDN）
    media_s3_addressing_style: str = field(default_factory=lambda: os.getenv("MEDIA_S3_ADDRESSING_STYLE", "virtual"))  # S3 寻址风格：virtual/path
    novel_crawl_http_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("NOVEL_CRAWL_HTTP_TIMEOUT_SECONDS", "20.0")))  # 小说爬虫 HTTP 总超时秒数
    novel_crawl_http_connect_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("NOVEL_CRAWL_HTTP_CONNECT_TIMEOUT_SECONDS", "10.0")))  # 小说爬虫 HTTP 连接超时秒数
    novel_crawl_impersonate: str = field(default_factory=lambda: os.getenv("NOVEL_CRAWL_IMPERSONATE", "chrome110"))  # 小说 rule 来源浏览器 TLS 指纹画像
    novel_crawl_proxy: str = field(default_factory=lambda: os.getenv("NOVEL_CRAWL_PROXY", ""))  # 小说爬虫代理地址，留空则不启用代理
    novel_crawl_chapter_coroutines_per_process: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_CHAPTER_COROUTINES_PER_PROCESS", "8")))  # 小说章节抓取每进程协程数
    novel_crawl_max_processes: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_MAX_PROCESSES", "4")))  # 小说章节抓取最大进程数
    novel_crawl_stream_concurrency: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_STREAM_CONCURRENCY", "8")))  # 小说章节流式抓取默认并发数
    novel_crawl_http_retries: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_HTTP_RETRIES", "2")))  # 小说爬虫 HTTP 请求重试次数
    novel_crawl_http_retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("NOVEL_CRAWL_HTTP_RETRY_BACKOFF_SECONDS", "0.5")))  # 小说爬虫 HTTP 重试基础退避秒数
    novel_crawl_max_search_pages: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_MAX_SEARCH_PAGES", "10")))  # 小说搜索翻页上限
    novel_crawl_max_content_pages: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_MAX_CONTENT_PAGES", "20")))  # 小说单章正文分页拼接上限
    novel_crawl_rule_concurrency: int = field(default_factory=lambda: int(os.getenv("NOVEL_CRAWL_RULE_CONCURRENCY", "3")))  # 小说 rule 来源章节抓取并发数
    novel_crawl_rule_jitter_seconds: float = field(default_factory=lambda: float(os.getenv("NOVEL_CRAWL_RULE_JITTER_SECONDS", "0.4")))  # 小说 rule 来源请求随机抖动秒数
    novel_crawl_throttle_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("NOVEL_CRAWL_THROTTLE_BACKOFF_SECONDS", "3.0")))  # 小说来源命中限流后的退避秒数
    novel_crawl_throttle_status_codes: tuple[int, ...] = field(default_factory=lambda: _env_int_tuple("NOVEL_CRAWL_THROTTLE_STATUS_CODES", (403, 429)))  # 小说来源限流状态码
    novel_crawl_next_page_labels: tuple[str, ...] = field(default_factory=lambda: _env_str_tuple("NOVEL_CRAWL_NEXT_PAGE_LABELS", ("下一页", "下页", "下一頁", "下一张")))  # 小说 rule 正文下一页链接文案

    model_request_timeout_seconds: float = field( default_factory=lambda: float(os.getenv("MODEL_REQUEST_TIMEOUT_SECONDS", "180")) )  # 模型请求超时秒数
    media_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("MEDIA_GENERATION_TIMEOUT_SECONDS", DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS)))  # 媒体生成通用超时秒数
    image_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("IMAGE_GENERATION_TIMEOUT_SECONDS", DEFAULT_IMAGE_GENERATION_TIMEOUT_SECONDS)))  # 图片生成超时秒数
    video_generation_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("VIDEO_GENERATION_TIMEOUT_SECONDS", DEFAULT_VIDEO_GENERATION_TIMEOUT_SECONDS)))  # 视频生成超时秒数
    media_generation_poll_interval_seconds: float = field(default_factory=lambda: float(os.getenv("MEDIA_GENERATION_POLL_INTERVAL_SECONDS", DEFAULT_MEDIA_GENERATION_POLL_INTERVAL_SECONDS)))  # 媒体生成异步轮询间隔秒数
    media_generation_max_concurrency: int = field(default_factory=lambda: int(os.getenv("MEDIA_GENERATION_MAX_CONCURRENCY", DEFAULT_MEDIA_GENERATION_MAX_CONCURRENCY)))  # 媒体生成默认最大并发数量
    provider_template_path: str = field(default_factory=lambda: os.getenv("PROVIDER_TEMPLATE_PATH", "./data/provider_template.py"))  # 服务商模板文件路径

    agent_embedding_model_name: str = field(default_factory=lambda: os.getenv("AGENT_EMBEDDING_MODEL_NAME", "bge-small-zh-v1.5"))  # Agent 本地嵌入模型名称
    agent_embedding_model_dir: str = field(default_factory=lambda: os.getenv("AGENT_EMBEDDING_MODEL_DIR", "./data/models/bge-small-zh-v1.5"))  # Agent 本地嵌入模型目录
    agent_vector_store_dir: str = field(default_factory=lambda: os.getenv("AGENT_VECTOR_STORE_DIR", "./data/chroma/script-agent"))  # Agent ChromaDB 持久化目录
    agent_embedding_dim: int = field(default_factory=lambda: int(os.getenv("AGENT_EMBEDDING_DIM", "512")))  # Agent 嵌入向量维度
    agent_embedding_max_tokens: int = field(default_factory=lambda: int(os.getenv("AGENT_EMBEDDING_MAX_TOKENS", "512")))  # Agent 嵌入最大 token 数
    agent_embedding_batch_size: int = field(default_factory=lambda: int(os.getenv("AGENT_EMBEDDING_BATCH_SIZE", "8")))  # Agent 嵌入单次 ONNX 推理批量上限
    screenwriting_rag_chunk_chars: int = field(default_factory=lambda: int(os.getenv("SCREENWRITING_RAG_CHUNK_CHARS", DEFAULT_SCREENWRITING_RAG_CHUNK_CHARS)))  # 剧本创作 RAG 文档切片字符数
    screenwriting_rag_chunk_overlap: int = field(default_factory=lambda: int(os.getenv("SCREENWRITING_RAG_CHUNK_OVERLAP", DEFAULT_SCREENWRITING_RAG_CHUNK_OVERLAP)))  # 剧本创作 RAG 文档切片重叠字符数
    screenwriting_rag_index_chunk_batch_size: int = field(default_factory=lambda: int(os.getenv("SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE", DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE)))  # 剧本创作 RAG 向量写入 chunk 批量上限
    screenwriting_rag_warmup_document_batch_size: int = field(default_factory=lambda: int(os.getenv("SCREENWRITING_RAG_WARMUP_DOCUMENT_BATCH_SIZE", DEFAULT_SCREENWRITING_RAG_WARMUP_DOCUMENT_BATCH_SIZE)))  # 剧本创作 RAG 预热文档加载批量上限
    screenwriting_rag_min_vector_score: float = field(default_factory=lambda: float(os.getenv("SCREENWRITING_RAG_MIN_VECTOR_SCORE", DEFAULT_SCREENWRITING_RAG_MIN_VECTOR_SCORE)))  # 剧本创作 RAG 向量命中最低分
    screenwriting_rag_retrieve_limit: int = field(default_factory=lambda: int(os.getenv("SCREENWRITING_RAG_RETRIEVE_LIMIT", DEFAULT_SCREENWRITING_RAG_RETRIEVE_LIMIT)))  # 剧本创作 RAG 单轮检索召回条数上限
    screenwriting_rag_intent_enabled: bool = field(default_factory=lambda: _env_bool("SCREENWRITING_RAG_INTENT_ENABLED", DEFAULT_SCREENWRITING_RAG_INTENT_ENABLED))  # 剧本创作 RAG 是否启用大模型查询意图解析
    screenwriting_rag_intent_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("SCREENWRITING_RAG_INTENT_TIMEOUT_SECONDS", DEFAULT_SCREENWRITING_RAG_INTENT_TIMEOUT_SECONDS)))  # 剧本创作 RAG 大模型查询意图解析超时秒数
    screenwriting_rag_vector_store_root: str = field(default_factory=lambda: os.getenv("SCREENWRITING_RAG_VECTOR_STORE_ROOT", DEFAULT_SCREENWRITING_RAG_VECTOR_STORE_ROOT))  # 剧本创作 RAG ChromaDB 项目级持久化根目录
    screenwriting_rag_visual_intent_keywords: tuple[str, ...] = field(default_factory=lambda: _env_str_tuple("SCREENWRITING_RAG_VISUAL_INTENT_KEYWORDS", DEFAULT_SCREENWRITING_RAG_VISUAL_INTENT_KEYWORDS))  # 剧本创作 RAG 技能资料召回意图关键词
    screenwriting_stage_team_enabled: bool = field(default_factory=lambda: _env_bool("SCREENWRITING_STAGE_TEAM_ENABLED", True))  # 剧本创作阶段生成是否启用 CrewAI 多角色团队（关闭则回退单 Agent）
    storyboard_table_prompt_name: str = field(default_factory=lambda: os.getenv("STORYBOARD_TABLE_PROMPT_NAME", "storyboard_table_generation"))  # 分镜表格生成提示词名称
    storyboard_grid_image_prompt_name: str = field(default_factory=lambda: os.getenv("STORYBOARD_GRID_IMAGE_PROMPT_NAME", "storyboard_grid_image_generation"))  # 宫格分镜图生成提示词名称
    storyboard_frame_image_prompt_name: str = field(default_factory=lambda: os.getenv("STORYBOARD_FRAME_IMAGE_PROMPT_NAME", "storyboard_frame_image_generation"))  # 单帧分镜图（1 宫格）生成提示词名称
    art_style_distill_prompt_name: str = field(default_factory=lambda: os.getenv("ART_STYLE_DISTILL_PROMPT_NAME", "art_style_prompt_distill"))  # 艺术风格提示词提炼技能名称
    director_style_distill_prompt_name: str = field(default_factory=lambda: os.getenv("DIRECTOR_STYLE_DISTILL_PROMPT_NAME", "director_style_prompt_distill"))  # 导演叙事提示词提炼技能名称
    shot_video_prompt_name: str = field(default_factory=lambda: os.getenv("SHOT_VIDEO_PROMPT_NAME", "shot_video_generation"))  # 镜头视频生成提示词名称

settings = Settings()

def oss_root_path() -> Path:
    """返回 OSS 本地根目录，配置为相对路径时按工程根目录解析。"""
    configured = Path(settings.oss_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()

def project_path(configured_path: str) -> Path:
    """按项目根目录解析配置路径。"""
    configured = Path(configured_path).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def media_root_path() -> Path:
    """返回统一媒体中枢本地存储根目录。"""
    return project_path(settings.media_root)


def skills_root_path(config: Settings | None = None) -> Path:
    """返回技能文档根目录。"""
    current = config or settings
    return project_path(current.skills_root)


def script_prompts_root_path(config: Settings | None = None) -> Path:
    """返回剧本创作工具提示词根目录。"""
    current = config or settings
    return project_path(current.script_prompts_root)