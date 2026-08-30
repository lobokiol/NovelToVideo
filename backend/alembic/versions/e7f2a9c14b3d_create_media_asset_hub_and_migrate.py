"""统一媒体中枢：新建 af_media_asset 并迁移废除 af_asset_media/af_asset_generation

修订 ID: e7f2a9c14b3d
前置修订: 0bb158dab6af
创建时间: 2026-07-05

升级内容：
1. 新建统一媒体中枢表 af_media_asset；
2. af_asset_media 全量迁入：reference 角色归为 source=upload，其余归为 source=generation，
   状态一律 ready；生成参数、种子、用量自关联 af_asset_generation 的 parameters/output 提取；
   原始回链信息保存在 params JSON 的 _legacy 块中，供回滚逆向还原；
3. 无成品媒体的生成记录（status != succeeded 且 generation_type 属于 image/video/audio）
   迁入为 status=failed 的媒体行（pending/running 归档为迁移中止）；
   generation_type=description 的文本生成历史不属于媒体域，不迁移且回滚不可恢复；
4. 本地媒体文件由旧布局 {project}/{asset}/{media}.{ext}（ASSET_MEDIA_ROOT，默认 ./data/asset_media）
   重排为 {project}/{media_type}/{media}.{ext}（MEDIA_ROOT，默认 ./data/media），
   url 重写为通用媒体分发路由；缺失文件跳过并告警，不中断迁移；
5. 删除 af_asset_media 与 af_asset_generation。
   注：af_project.tts_model 列按用户要求原样保留，后续新功能不消费。

回滚内容：重建两张旧表，按 _legacy 块逆向还原行与文件布局；升级后新产生的
非资产挂靠媒体（scope_type != asset）在旧模型中无宿主，回滚时随中枢表一并丢弃。
"""
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

import sqlmodel

from app.core.config import BASE_DIR

# Alembic 使用的修订标识。
revision: str = 'e7f2a9c14b3d'
down_revision: Union[str, Sequence[str], None] = '0bb158dab6af' # 每一个人的都一样，所以要根据实际情况填写
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_MEDIA_TYPES = ("image", "video", "audio")


def _resolve_root(env_key: str, default: str) -> Path:
    """按运行环境解析媒体存储根目录，相对路径基于项目根目录。"""
    configured = Path(os.getenv(env_key, default)).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def _legacy_media_root() -> Path:
    return _resolve_root("ASSET_MEDIA_ROOT", "./data/asset_media")


def _media_root() -> Path:
    return _resolve_root("MEDIA_ROOT", "./data/media")


def _api_prefix() -> str:
    prefix = os.getenv("API_PREFIX", "/api").strip()
    if prefix and not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return prefix.rstrip("/")


def _content_url(project_public_id: str, media_public_id: str) -> str:
    return f"{_api_prefix()}/projects/{project_public_id}/media/{media_public_id}/content"


def _legacy_content_url(project_public_id: str, media_public_id: str) -> str:
    return f"{_api_prefix()}/projects/{project_public_id}/assets/media/{media_public_id}/content"


def _load_json(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _move_file(source: Path, target: Path) -> bool:
    """搬迁单个媒体文件；源文件缺失或搬迁失败时告警并返回 False。"""
    if not source.exists():
        logger.warning("媒体文件缺失，跳过搬迁：%s", source)
        return False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except OSError as exc:
        logger.warning("媒体文件搬迁失败（%s → %s）：%s", source, target, exc)
        return False
    return True


def _create_media_asset_table() -> None:
    op.create_table(
        'af_media_asset',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('public_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_public_id', sa.String(length=36), nullable=False),
        sa.Column('media_type', sa.String(length=20), server_default='image', nullable=False),
        sa.Column('source', sa.String(length=20), server_default='generation', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('scope_type', sa.String(length=20), server_default='', nullable=False),
        sa.Column('scope_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('media_role', sa.String(length=40), server_default='generated', nullable=False),
        sa.Column('provider_key', sa.String(length=80), server_default='', nullable=False),
        sa.Column('model_id', sa.String(length=120), server_default='', nullable=False),
        sa.Column('prompt', sa.Text(), server_default='', nullable=False),
        sa.Column('params', sa.Text(), server_default='{}', nullable=False),
        sa.Column('seed', sa.String(length=60), server_default='', nullable=False),
        sa.Column('storage_backend', sa.String(length=20), server_default='', nullable=False),
        sa.Column('storage_key', sa.String(length=1000), server_default='', nullable=False),
        sa.Column('url', sa.String(length=2000), server_default='', nullable=False),
        sa.Column('mime_type', sa.String(length=120), server_default='', nullable=False),
        sa.Column('file_size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('width', sa.Integer(), server_default='0', nullable=False),
        sa.Column('height', sa.Integer(), server_default='0', nullable=False),
        sa.Column('duration_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cost_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('usage', sa.Text(), server_default='{}', nullable=False),
        sa.Column('task_job_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('task_item_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('error_message', sa.Text(), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['af_project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    for column, unique in (
        ('disabled_at', False),
        ('media_role', False),
        ('media_type', False),
        ('model_id', False),
        ('project_id', False),
        ('provider_key', False),
        ('public_id', True),
        ('scope_public_id', False),
        ('scope_type', False),
        ('sort_order', False),
        ('source', False),
        ('status', False),
        ('storage_key', False),
        ('task_item_public_id', False),
        ('task_job_public_id', False),
        ('user_public_id', False),
    ):
        op.create_index(op.f(f'ix_af_media_asset_{column}'), 'af_media_asset', [column], unique=unique)


_INSERT_MEDIA_ASSET = sa.text(
    """
    INSERT INTO af_media_asset (
        public_id, sort_order, created_at, updated_at, disabled_at,
        project_id, user_public_id, media_type, source, status,
        scope_type, scope_public_id, media_role, provider_key, model_id,
        prompt, params, seed, storage_backend, storage_key, url, mime_type,
        file_size, width, height, duration_ms, cost_tokens, usage,
        task_job_public_id, task_item_public_id, error_message
    ) VALUES (
        :public_id, :sort_order, :created_at, :updated_at, :disabled_at,
        :project_id, :user_public_id, :media_type, :source, :status,
        :scope_type, :scope_public_id, :media_role, :provider_key, :model_id,
        :prompt, :params, :seed, :storage_backend, :storage_key, :url, :mime_type,
        :file_size, :width, :height, :duration_ms, :cost_tokens, :usage,
        :task_job_public_id, :task_item_public_id, :error_message
    )
    """
)


def _migrate_media_rows(conn: sa.Connection) -> None:
    """把资产媒体行（联表资产/项目/生成记录）迁入媒体中枢并重排文件。"""
    rows = conn.execute(
        sa.text(
            """
            SELECT m.public_id, m.sort_order, m.created_at, m.updated_at, m.disabled_at,
                   m.project_id, m.user_public_id, m.media_type, m.media_role, m.url,
                   m.storage_key, m.mime_type, m.width, m.height, m.duration_ms,
                   m.prompt, m.generation_public_id, m.extra_data,
                   a.public_id AS asset_public_id, p.public_id AS project_public_id,
                   g.provider AS gen_provider, g.model_id AS gen_model_id,
                   g.parameters AS gen_parameters, g.status AS gen_status,
                   g.task_job_public_id AS gen_task_job_public_id,
                   g.task_item_public_id AS gen_task_item_public_id,
                   g.output AS gen_output,
                   g.started_at AS gen_started_at, g.completed_at AS gen_completed_at
            FROM af_asset_media m
            JOIN af_asset a ON a.id = m.asset_id
            JOIN af_project p ON p.id = m.project_id
            LEFT JOIN af_asset_generation g ON g.public_id = m.generation_public_id
            """
        )
    ).mappings()

    legacy_root = _legacy_media_root()
    media_root = _media_root()
    migrated = 0
    for row in rows:
        media_type = str(row["media_type"] or "image")
        is_upload = str(row["media_role"] or "") == "reference"
        output = _load_json(row["gen_output"])
        usage = output.get("usage") if isinstance(output.get("usage"), dict) else {}
        try:
            cost_tokens = int(usage.get("total_tokens") or 0)
        except (TypeError, ValueError):
            cost_tokens = 0

        params = _load_json(row["gen_parameters"]) if row["gen_provider"] is not None else {}
        if is_upload:
            params = _load_json(row["extra_data"])
        params["_legacy"] = {
            "generation_public_id": str(row["generation_public_id"] or ""),
            "generation_status": str(row["gen_status"] or ""),
            "generation_output": output,
            "media_extra_data": _load_json(row["extra_data"]),
            "storage_key": str(row["storage_key"] or ""),
            "url": str(row["url"] or ""),
        }

        old_key = str(row["storage_key"] or "")
        new_key = old_key
        file_size = 0
        if old_key:
            suffix = Path(old_key).suffix or ".png"
            new_key = f"{row['project_public_id']}/{media_type}/{row['public_id']}{suffix}"
            source_path = legacy_root / old_key
            if source_path.exists():
                file_size = source_path.stat().st_size
            _move_file(source_path, media_root / new_key)

        conn.execute(
            _INSERT_MEDIA_ASSET,
            {
                "public_id": row["public_id"],
                "sort_order": row["sort_order"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "disabled_at": row["disabled_at"],
                "project_id": row["project_id"],
                "user_public_id": row["user_public_id"],
                "media_type": media_type,
                "source": "upload" if is_upload else "generation",
                "status": "ready",
                "scope_type": "asset",
                "scope_public_id": row["asset_public_id"],
                "media_role": row["media_role"],
                "provider_key": str(row["gen_provider"] or ""),
                "model_id": str(row["gen_model_id"] or ""),
                "prompt": str(row["prompt"] or ""),
                "params": json.dumps(params, ensure_ascii=False),
                "seed": str(output.get("seed") or "")[:60],
                "storage_backend": "local" if new_key else "",
                "storage_key": new_key,
                "url": _content_url(str(row["project_public_id"]), str(row["public_id"])),
                "mime_type": str(row["mime_type"] or ""),
                "file_size": file_size,
                "width": row["width"] or 0,
                "height": row["height"] or 0,
                "duration_ms": row["duration_ms"] or 0,
                "cost_tokens": cost_tokens,
                "usage": json.dumps(usage, ensure_ascii=False),
                "task_job_public_id": str(row["gen_task_job_public_id"] or ""),
                "task_item_public_id": str(row["gen_task_item_public_id"] or ""),
                "error_message": "",
            },
        )
        migrated += 1
    logger.info("媒体中枢迁移：已迁入 %s 行资产媒体", migrated)


def _migrate_failed_generation_rows(conn: sa.Connection) -> None:
    """把未产出媒体的生成记录归档为失败媒体行，保留失败历史。"""
    rows = conn.execute(
        sa.text(
            """
            SELECT g.public_id, g.sort_order, g.created_at, g.updated_at, g.disabled_at,
                   g.project_id, g.user_public_id, g.generation_type, g.provider, g.model_id,
                   g.prompt, g.parameters, g.status, g.task_job_public_id, g.task_item_public_id,
                   g.error_message,
                   a.public_id AS asset_public_id, p.public_id AS project_public_id
            FROM af_asset_generation g
            JOIN af_asset a ON a.id = g.asset_id
            JOIN af_project p ON p.id = g.project_id
            WHERE g.status != 'succeeded' AND g.generation_type IN ('image', 'video', 'audio')
            """
        )
    ).mappings()

    archived = 0
    for row in rows:
        status = str(row["status"] or "")
        if status == "cancelled":
            error_message = "已取消"
        elif status in ("pending", "running"):
            error_message = "迁移中止：任务在迁移时未完成"
        else:
            error_message = str(row["error_message"] or "生成失败")

        params = _load_json(row["parameters"])
        params["_legacy"] = {
            "generation_public_id": str(row["public_id"]),
            "generation_status": status,
            "from_generation_only": True,
        }
        conn.execute(
            _INSERT_MEDIA_ASSET,
            {
                "public_id": row["public_id"],
                "sort_order": row["sort_order"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "disabled_at": row["disabled_at"],
                "project_id": row["project_id"],
                "user_public_id": row["user_public_id"],
                "media_type": str(row["generation_type"]),
                "source": "generation",
                "status": "failed",
                "scope_type": "asset",
                "scope_public_id": row["asset_public_id"],
                "media_role": "generated",
                "provider_key": str(row["provider"] or ""),
                "model_id": str(row["model_id"] or ""),
                "prompt": str(row["prompt"] or ""),
                "params": json.dumps(params, ensure_ascii=False),
                "seed": "",
                "storage_backend": "",
                "storage_key": "",
                "url": "",
                "mime_type": "",
                "file_size": 0,
                "width": 0,
                "height": 0,
                "duration_ms": 0,
                "cost_tokens": 0,
                "usage": "{}",
                "task_job_public_id": str(row["task_job_public_id"] or ""),
                "task_item_public_id": str(row["task_item_public_id"] or ""),
                "error_message": error_message,
            },
        )
        archived += 1
    logger.info("媒体中枢迁移：已归档 %s 行失败生成记录", archived)


def upgrade() -> None:
    """升级数据库结构：建中枢表、迁数据与文件、删旧表。"""
    _create_media_asset_table()

    conn = op.get_bind()
    _migrate_media_rows(conn)
    _migrate_failed_generation_rows(conn)

    op.drop_table('af_asset_media')
    op.drop_table('af_asset_generation')


def _recreate_legacy_tables() -> None:
    op.create_table(
        'af_asset_generation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('public_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_public_id', sa.String(length=36), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('generation_type', sa.String(length=40), server_default='image', nullable=False),
        sa.Column('provider', sa.String(length=80), server_default='', nullable=False),
        sa.Column('model_id', sa.String(length=120), server_default='', nullable=False),
        sa.Column('prompt', sa.Text(), server_default='', nullable=False),
        sa.Column('negative_prompt', sa.Text(), server_default='', nullable=False),
        sa.Column('parameters', sa.Text(), server_default='{}', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('task_job_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('task_item_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('output', sa.Text(), server_default='{}', nullable=False),
        sa.Column('error_message', sa.Text(), server_default='', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['af_asset.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['af_project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    for column, unique in (
        ('asset_id', False),
        ('disabled_at', False),
        ('generation_type', False),
        ('model_id', False),
        ('project_id', False),
        ('provider', False),
        ('public_id', True),
        ('sort_order', False),
        ('status', False),
        ('task_item_public_id', False),
        ('task_job_public_id', False),
        ('user_public_id', False),
    ):
        op.create_index(op.f(f'ix_af_asset_generation_{column}'), 'af_asset_generation', [column], unique=unique)

    op.create_table(
        'af_asset_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('public_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_public_id', sa.String(length=36), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(length=20), server_default='image', nullable=False),
        sa.Column('media_role', sa.String(length=40), server_default='reference', nullable=False),
        sa.Column('url', sa.String(length=2000), server_default='', nullable=False),
        sa.Column('storage_key', sa.String(length=1000), server_default='', nullable=False),
        sa.Column('mime_type', sa.String(length=120), server_default='', nullable=False),
        sa.Column('width', sa.Integer(), server_default='0', nullable=False),
        sa.Column('height', sa.Integer(), server_default='0', nullable=False),
        sa.Column('duration_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('prompt', sa.Text(), server_default='', nullable=False),
        sa.Column('generation_public_id', sa.String(length=36), server_default='', nullable=False),
        sa.Column('extra_data', sa.Text(), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['af_asset.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['af_project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    for column, unique in (
        ('asset_id', False),
        ('disabled_at', False),
        ('generation_public_id', False),
        ('media_role', False),
        ('media_type', False),
        ('project_id', False),
        ('public_id', True),
        ('sort_order', False),
        ('storage_key', False),
        ('user_public_id', False),
    ):
        op.create_index(op.f(f'ix_af_asset_media_{column}'), 'af_asset_media', [column], unique=unique)


def downgrade() -> None:
    """回滚数据库结构：重建旧表、按 _legacy 逆向还原数据与文件。"""
    _recreate_legacy_tables()

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT h.*, a.id AS asset_id, p.public_id AS project_public_id
            FROM af_media_asset h
            JOIN af_project p ON p.id = h.project_id
            LEFT JOIN af_asset a ON a.public_id = h.scope_public_id
            WHERE h.scope_type = 'asset'
            """
        )
    ).mappings()

    legacy_root = _legacy_media_root()
    media_root = _media_root()
    seen_generation_ids: set[str] = set()
    restored = 0
    dropped = 0
    for row in rows:
        if row["asset_id"] is None:
            dropped += 1
            continue

        params = _load_json(row["params"])
        legacy = params.pop("_legacy", {}) if isinstance(params.get("_legacy"), dict) else {}
        generation_public_id = str(legacy.get("generation_public_id") or "")
        usage = _load_json(row["usage"])

        if legacy.get("from_generation_only") or str(row["status"]) == "failed":
            # 失败归档行：只还原生成记录，不产生媒体行。
            if row["public_id"] not in seen_generation_ids:
                seen_generation_ids.add(str(row["public_id"]))
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO af_asset_generation (
                            public_id, sort_order, created_at, updated_at, disabled_at,
                            project_id, user_public_id, asset_id, generation_type, provider,
                            model_id, prompt, negative_prompt, parameters, status,
                            task_job_public_id, task_item_public_id, output, error_message
                        ) VALUES (
                            :public_id, :sort_order, :created_at, :updated_at, :disabled_at,
                            :project_id, :user_public_id, :asset_id, :generation_type, :provider,
                            :model_id, :prompt, '', :parameters, :status,
                            :task_job_public_id, :task_item_public_id, '{}', :error_message
                        )
                        """
                    ),
                    {
                        "public_id": row["public_id"],
                        "sort_order": row["sort_order"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "disabled_at": row["disabled_at"],
                        "project_id": row["project_id"],
                        "user_public_id": row["user_public_id"],
                        "asset_id": row["asset_id"],
                        "generation_type": row["media_type"],
                        "provider": row["provider_key"],
                        "model_id": row["model_id"],
                        "prompt": row["prompt"],
                        "parameters": json.dumps(params, ensure_ascii=False),
                        "status": str(legacy.get("generation_status") or "failed"),
                        "task_job_public_id": row["task_job_public_id"],
                        "task_item_public_id": row["task_item_public_id"],
                        "error_message": row["error_message"],
                    },
                )
            restored += 1
            continue

        # 就绪媒体行：还原媒体行与（生成来源时的）生成记录。
        legacy_key = str(legacy.get("storage_key") or "")
        if not legacy_key and row["storage_key"]:
            suffix = Path(str(row["storage_key"])).suffix or ".png"
            legacy_key = f"{row['project_public_id']}/{row['scope_public_id']}/{row['public_id']}{suffix}"
        if row["storage_key"] and legacy_key:
            _move_file(media_root / str(row["storage_key"]), legacy_root / legacy_key)

        if str(row["source"]) == "generation" and generation_public_id and generation_public_id not in seen_generation_ids:
            seen_generation_ids.add(generation_public_id)
            legacy_output = legacy.get("generation_output")
            output = legacy_output if isinstance(legacy_output, dict) else {"usage": usage, "seed": row["seed"]}
            conn.execute(
                sa.text(
                    """
                    INSERT INTO af_asset_generation (
                        public_id, sort_order, created_at, updated_at, disabled_at,
                        project_id, user_public_id, asset_id, generation_type, provider,
                        model_id, prompt, negative_prompt, parameters, status,
                        task_job_public_id, task_item_public_id, output, error_message
                    ) VALUES (
                        :public_id, :sort_order, :created_at, :updated_at, :disabled_at,
                        :project_id, :user_public_id, :asset_id, :generation_type, :provider,
                        :model_id, :prompt, '', :parameters, :status,
                        :task_job_public_id, :task_item_public_id, :output, ''
                    )
                    """
                ),
                {
                    "public_id": generation_public_id,
                    "sort_order": row["sort_order"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "disabled_at": row["disabled_at"],
                    "project_id": row["project_id"],
                    "user_public_id": row["user_public_id"],
                    "asset_id": row["asset_id"],
                    "generation_type": row["media_type"],
                    "provider": row["provider_key"],
                    "model_id": row["model_id"],
                    "prompt": row["prompt"],
                    "parameters": json.dumps(params, ensure_ascii=False),
                    "status": str(legacy.get("generation_status") or "succeeded"),
                    "task_job_public_id": row["task_job_public_id"],
                    "task_item_public_id": row["task_item_public_id"],
                    "output": json.dumps(output, ensure_ascii=False),
                },
            )

        media_extra = legacy.get("media_extra_data")
        extra_data = media_extra if isinstance(media_extra, dict) else ({} if str(row["source"]) == "generation" else params)
        conn.execute(
            sa.text(
                """
                INSERT INTO af_asset_media (
                    public_id, sort_order, created_at, updated_at, disabled_at,
                    project_id, user_public_id, asset_id, media_type, media_role,
                    url, storage_key, mime_type, width, height, duration_ms,
                    prompt, generation_public_id, extra_data
                ) VALUES (
                    :public_id, :sort_order, :created_at, :updated_at, :disabled_at,
                    :project_id, :user_public_id, :asset_id, :media_type, :media_role,
                    :url, :storage_key, :mime_type, :width, :height, :duration_ms,
                    :prompt, :generation_public_id, :extra_data
                )
                """
            ),
            {
                "public_id": row["public_id"],
                "sort_order": row["sort_order"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "disabled_at": row["disabled_at"],
                "project_id": row["project_id"],
                "user_public_id": row["user_public_id"],
                "asset_id": row["asset_id"],
                "media_type": row["media_type"],
                "media_role": row["media_role"],
                "url": str(legacy.get("url") or _legacy_content_url(str(row["project_public_id"]), str(row["public_id"]))),
                "storage_key": legacy_key,
                "mime_type": row["mime_type"],
                "width": row["width"],
                "height": row["height"],
                "duration_ms": row["duration_ms"],
                "prompt": row["prompt"],
                "generation_public_id": generation_public_id,
                "extra_data": json.dumps(extra_data, ensure_ascii=False),
            },
        )
        restored += 1

    logger.info("媒体中枢回滚：还原 %s 行，丢弃无宿主行 %s 行", restored, dropped)
    op.drop_table('af_media_asset')