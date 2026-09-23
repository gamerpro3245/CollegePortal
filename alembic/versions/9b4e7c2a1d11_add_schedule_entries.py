"""add schedule entries

Revision ID: 9b4e7c2a1d11
Revises: ee477220eb85
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9b4e7c2a1d11"
down_revision: Union[str, Sequence[str], None] = "ee477220eb85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("teaching_assignment_id", sa.Integer(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("room", sa.String(length=50), nullable=True),
        sa.Column("lesson_type", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["teaching_assignment_id"], ["teaching_assignments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedule_entries_group_id", "schedule_entries", ["group_id"])
    op.create_index("ix_schedule_entries_subject_id", "schedule_entries", ["subject_id"])
    op.create_index("ix_schedule_entries_teacher_id", "schedule_entries", ["teacher_id"])
    op.create_index("ix_schedule_entries_day_of_week", "schedule_entries", ["day_of_week"])


def downgrade() -> None:
    op.drop_index("ix_schedule_entries_day_of_week", table_name="schedule_entries")
    op.drop_index("ix_schedule_entries_teacher_id", table_name="schedule_entries")
    op.drop_index("ix_schedule_entries_subject_id", table_name="schedule_entries")
    op.drop_index("ix_schedule_entries_group_id", table_name="schedule_entries")
    op.drop_table("schedule_entries")
