"""add group relation

Revision ID: ed05e7359ebd
Revises: 58e2aad25f30
Create Date: 2026-09-21 08:05:09.705749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed05e7359ebd'
down_revision: Union[str, Sequence[str], None] = '58e2aad25f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table(
        "users",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        },
    ) as batch_op:
        batch_op.add_column(
            sa.Column("group_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_users_group_id_groups",
            "groups",
            ["group_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        "users",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        },
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_users_group_id_groups",
            type_="foreignkey",
        )
        batch_op.drop_column("group_id")