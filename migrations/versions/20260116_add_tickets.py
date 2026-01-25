from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260116_add_tickets'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'player_stats',
        sa.Column('tickets', sa.Integer(), nullable=True, server_default='0')
    )
    op.alter_column('player_stats', 'tickets', nullable=False, server_default=None)

def downgrade():
    op.drop_column('player_stats', 'tickets')
