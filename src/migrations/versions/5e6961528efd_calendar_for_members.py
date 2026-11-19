"""calendar for members

Revision ID: 5e6961528efd
Revises: 1e7650ca70be
Create Date: 2026-10-20 13:11:11.611492

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e6961528efd'
down_revision: Union[str, Sequence[str], None] = '1e7650ca70be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS calendar_items")
    op.execute("""
        CREATE VIEW calendar_items AS
        SELECT 'plan' AS item_type, id, owner_id AS user_id, title, due_date
        FROM plans WHERE due_date IS NOT NULL AND status = 'open'
        UNION ALL
        SELECT 'task', id, owner_id, title, due_date
        FROM tasks WHERE due_date IS NOT NULL AND project_id IS NULL
        UNION ALL
        SELECT 'task', t.id, pm.user_id, t.title, t.due_date
        FROM tasks t JOIN proj_members pm ON pm.project_id = t.project_id
        WHERE t.due_date IS NOT NULL
        UNION ALL
        SELECT 'project', p.id, pm.user_id, p.name, p.due_date
        FROM projects p JOIN proj_members pm ON pm.project_id = p.id
        WHERE p.due_date IS NOT NULL   
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS calendar_items
    """)
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