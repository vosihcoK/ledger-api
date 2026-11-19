"""make users email unique

Revision ID: db682aa2f14a
Revises: 2bc261f792b3
Create Date: 2026-11-20 00:46:50.206944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db682aa2f14a'
down_revision: Union[str, Sequence[str], None] = '2bc261f792b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
