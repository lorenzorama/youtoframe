"""queue: waiting status

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'waiting'")


def downgrade():
    # Postgres cannot easily DROP an enum value; 'waiting' is left in place.
    pass
