"""Add batch info to purchase order detail

Revision ID: 5949f11c8f3d
Revises: 2a415e5f8bec
Create Date: 2026-02-05 17:37:57.095663

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5949f11c8f3d'
down_revision = '2a415e5f8bec'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('purchase_order_detail', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batch_number', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('expiration_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('purchase_order_detail', schema=None) as batch_op:
        batch_op.drop_column('expiration_date')
        batch_op.drop_column('batch_number')
