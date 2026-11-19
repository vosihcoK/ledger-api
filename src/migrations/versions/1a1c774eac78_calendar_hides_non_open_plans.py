"""calendar hides non-open plans

Revision ID: 1a1c774eac78
Revises: 7f908f09e9d4
Create Date: 2026-10-05 12:43:13.745506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a1c774eac78'
down_revision: Union[str, Sequence[str], None] = '7f908f09e9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE OR REPLACE VIEW calendar_items AS
        SELECT 'plan' AS item_type, id, owner_id, title, due_date
        FROM plans WHERE due_date IS NOT NULL AND status = 'open'
        UNION ALL
        SELECT 'task' AS item_type, id, owner_id, title, due_date
        FROM tasks WHERE due_date IS NOT NULL
        UNION ALL
        SELECT 'project' AS item_type, id, owner_id, name AS title, due_date
        FROM projects WHERE due_date IS NOT NULL
    """)

def downgrade():
    op.execute("""
        CREATE OR REPLACE VIEW calendar_items AS
        SELECT 'plan' AS item_type, id, owner_id, title, due_date
        FROM plans WHERE due_date IS NOT NULL
        UNION ALL
        SELECT 'task' AS item_type, id, owner_id, title, due_date
        FROM tasks WHERE due_date IS NOT NULL
        UNION ALL
        SELECT 'project' AS item_type, id, owner_id, name AS title, due_date
        FROM projects WHERE due_date IS NOT NULL
    """)