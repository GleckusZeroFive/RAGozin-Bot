"""Rename tier 'unlimited' to 'admin'

Revision ID: 005
Revises: 004
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET tier = 'admin' WHERE tier = 'unlimited'")
    op.execute("UPDATE invite_keys SET tier = 'admin' WHERE tier = 'unlimited'")


def downgrade() -> None:
    op.execute("UPDATE users SET tier = 'unlimited' WHERE tier = 'admin'")
    op.execute("UPDATE invite_keys SET tier = 'unlimited' WHERE tier = 'admin'")
