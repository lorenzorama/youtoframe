"""whisper: transcribing status + transcript_source

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on some
    # Postgres/Alembic configs; run it in an autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'transcribing'")
    op.add_column("job", sa.Column("transcript_source", sa.String(), nullable=True))


def downgrade():
    op.drop_column("job", "transcript_source")
    # NOTE: Postgres cannot easily DROP an enum value, so 'transcribing' is left
    # in the jobstatus type on downgrade (harmless).
