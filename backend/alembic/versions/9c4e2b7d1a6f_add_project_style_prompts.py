"""add project style prompt columns

Revision ID: 9c4e2b7d1a6f
Revises: e7f2a9c14b3d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c4e2b7d1a6f"
down_revision: Union[str, Sequence[str], None] = "e7f2a9c14b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "af_project",
        sa.Column("art_style_prompt", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "af_project",
        sa.Column("director_style_prompt", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("af_project", "director_style_prompt")
    op.drop_column("af_project", "art_style_prompt")
