"""add grades

Revision ID: d41b7e9a5c20
Revises: c21a6f4e8b10, c31a9d4e2f10
"""

from alembic import op
import sqlalchemy as sa

revision = "d41b7e9a5c20"
down_revision = ("c21a6f4e8b10", "c31a9d4e2f10")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "grades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id"), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("grade_date", sa.String(length=10), nullable=False),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_grades_student_id", "grades", ["student_id"])
    op.create_index("ix_grades_teacher_id", "grades", ["teacher_id"])
    op.create_index("ix_grades_subject_id", "grades", ["subject_id"])


def downgrade():
    op.drop_index("ix_grades_subject_id", table_name="grades")
    op.drop_index("ix_grades_teacher_id", table_name="grades")
    op.drop_index("ix_grades_student_id", table_name="grades")
    op.drop_table("grades")
