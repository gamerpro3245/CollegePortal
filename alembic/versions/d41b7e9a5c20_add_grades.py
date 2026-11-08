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

_INDEXES = (
    ("ix_grades_student_id", ["student_id"]),
    ("ix_grades_teacher_id", ["teacher_id"]),
    ("ix_grades_subject_id", ["subject_id"]),
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The app also calls Base.metadata.create_all() at startup. If that
    # already created grades, don't try to create the same table again.
    if not inspector.has_table("grades"):
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

    existing_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("grades")
    }
    for index_name, columns in _INDEXES:
        if index_name not in existing_indexes:
            op.create_index(index_name, "grades", columns)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("grades"):
        return

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("grades")
    }
    for index_name, _columns in reversed(_INDEXES):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="grades")
    op.drop_table("grades")
