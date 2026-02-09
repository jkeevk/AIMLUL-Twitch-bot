import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260116_add_tickets"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add tickets column to player_stats table."""
    op.add_column("player_stats", sa.Column("tickets", sa.Integer(), nullable=True, server_default="0"))
    op.alter_column("player_stats", "tickets", nullable=False, server_default=None)


def downgrade():
    """Remove tickets column from player_stats table."""
    op.drop_column("player_stats", "tickets")
