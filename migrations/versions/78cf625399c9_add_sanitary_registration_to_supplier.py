"""Add sanitary_registration to Supplier

Revision ID: 78cf625399c9
Revises: 5ffeed342764
Create Date: 2026-02-05 06:45:44.069865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '78cf625399c9'
down_revision = '5ffeed342764'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('supplier', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sanitary_registration', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('supplier', schema=None) as batch_op:
        batch_op.drop_column('sanitary_registration')
