"""Add user permissions and company access

Revision ID: 2a415e5f8bec
Revises: 78cf625399c9
Create Date: 2026-02-05 07:02:14.397996

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a415e5f8bec'
down_revision = '78cf625399c9'
branch_labels = None
depends_on = None


def upgrade():
    # Create user_company_access table
    op.create_table('user_company_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('perm_dashboard', sa.Boolean(), nullable=True),
        sa.Column('perm_sync', sa.Boolean(), nullable=True),
        sa.Column('perm_inventory', sa.Boolean(), nullable=True),
        sa.Column('perm_invoices', sa.Boolean(), nullable=True),
        sa.Column('perm_ppd', sa.Boolean(), nullable=True),
        sa.Column('perm_taxes', sa.Boolean(), nullable=True),
        sa.Column('perm_sales', sa.Boolean(), nullable=True),
        sa.Column('perm_facturacion', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'company_id', name='unique_user_company')
    )

    # Add is_admin column to user table
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_admin')

    op.drop_table('user_company_access')
