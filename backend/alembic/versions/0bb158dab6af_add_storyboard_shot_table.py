"""新增分镜镜头表

修订 ID: 0bb158dab6af
前置修订: 55bef61c409c
创建时间: 2026-07-01 14:36:40.200208

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import sqlmodel
# Alembic 使用的修订标识。
revision: str = '0bb158dab6af'
down_revision: Union[str, Sequence[str], None] = '55bef61c409c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构。"""
    # ### Alembic 自动生成的命令，请按需调整。 ###
    op.create_table('af_storyboard_shot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('public_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_public_id', sa.String(length=36), nullable=False),
    sa.Column('episode_public_id', sa.String(length=36), server_default='', nullable=False),
    sa.Column('episode_index', sa.Integer(), server_default='0', nullable=False),
    sa.Column('scene_number', sa.String(length=40), server_default='', nullable=False),
    sa.Column('shot_index', sa.Integer(), server_default='0', nullable=False),
    sa.Column('shot_size', sa.String(length=40), server_default='', nullable=False),
    sa.Column('camera', sa.String(length=120), server_default='', nullable=False),
    sa.Column('action', sa.Text(), server_default='', nullable=False),
    sa.Column('dialogue', sa.Text(), server_default='', nullable=False),
    sa.Column('duration_seconds', sa.Integer(), server_default='0', nullable=False),
    sa.Column('asset_public_ids', sa.String(length=400), server_default='', nullable=False),
    sa.Column('asset_names', sa.String(length=400), server_default='', nullable=False),
    sa.Column('art_style_key', sa.String(length=120), server_default='', nullable=False),
    sa.Column('director_style_key', sa.String(length=120), server_default='', nullable=False),
    sa.Column('model_id', sa.String(length=120), server_default='', nullable=False),
    sa.Column('prompt', sa.Text(), server_default='', nullable=False),
    sa.Column('negative_prompt', sa.Text(), server_default='', nullable=False),
    sa.Column('reference_media_public_id', sa.String(length=36), server_default='', nullable=False),
    sa.Column('seed', sa.String(length=60), server_default='', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['af_project.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_public_id', 'episode_public_id', 'shot_index', name='uq_af_storyboard_shot_episode_index')
    )
    op.create_index(op.f('ix_af_storyboard_shot_disabled_at'), 'af_storyboard_shot', ['disabled_at'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_episode_index'), 'af_storyboard_shot', ['episode_index'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_episode_public_id'), 'af_storyboard_shot', ['episode_public_id'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_project_id'), 'af_storyboard_shot', ['project_id'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_public_id'), 'af_storyboard_shot', ['public_id'], unique=True)
    op.create_index(op.f('ix_af_storyboard_shot_reference_media_public_id'), 'af_storyboard_shot', ['reference_media_public_id'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_shot_index'), 'af_storyboard_shot', ['shot_index'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_sort_order'), 'af_storyboard_shot', ['sort_order'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_status'), 'af_storyboard_shot', ['status'], unique=False)
    op.create_index(op.f('ix_af_storyboard_shot_user_public_id'), 'af_storyboard_shot', ['user_public_id'], unique=False)
    # ### Alembic 命令结束。 ###


def downgrade() -> None:
    """回滚数据库结构。"""
    # ### Alembic 自动生成的命令，请按需调整。 ###
    op.drop_index(op.f('ix_af_storyboard_shot_user_public_id'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_status'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_sort_order'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_shot_index'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_reference_media_public_id'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_public_id'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_project_id'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_episode_public_id'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_episode_index'), table_name='af_storyboard_shot')
    op.drop_index(op.f('ix_af_storyboard_shot_disabled_at'), table_name='af_storyboard_shot')
    op.drop_table('af_storyboard_shot')
    # ### Alembic 命令结束。 ###
