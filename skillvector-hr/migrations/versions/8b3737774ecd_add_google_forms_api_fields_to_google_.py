"""add google forms api fields to google_form_connections

Revision ID: 8b3737774ecd
Revises: b2c3d4e5f6a7
Create Date: 2026-06-30 00:04:25.816179

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8b3737774ecd'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('google_form_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('form_id', sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column('field_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column('last_response_id', sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column('sync_status', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('total_synced', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('google_form_connections', schema=None) as batch_op:
        batch_op.drop_column('last_error')
        batch_op.drop_column('total_synced')
        batch_op.drop_column('sync_status')
        batch_op.drop_column('last_response_id')
        batch_op.drop_column('field_mapping')
        batch_op.drop_column('form_id')
