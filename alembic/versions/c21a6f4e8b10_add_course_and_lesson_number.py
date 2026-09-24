"""add course and lesson number

Revision ID: c21a6f4e8b10
Revises: 9b4e7c2a1d11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c21a6f4e8b10"
down_revision: Union[str, Sequence[str], None] = "9b4e7c2a1d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("course", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("schedule_entries", sa.Column("lesson_number", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("schedule_entries", "lesson_number")
    op.drop_column("groups", "course")
