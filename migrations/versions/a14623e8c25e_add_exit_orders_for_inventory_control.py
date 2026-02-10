"""Add exit orders for inventory control

Revision ID: a14623e8c25e
Revises: 5949f11c8f3d
Create Date: 2026-02-05 20:35:56.608215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a14623e8c25e'
down_revision = '5949f11c8f3d'
branch_labels = None
depends_on = None


def upgrade():
    # Create exit_order table
    op.create_table('exit_order',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('recipient_name', sa.String(length=200), nullable=False),
        sa.Column('recipient_type', sa.String(length=50), nullable=True),
        sa.Column('recipient_id', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create exit_order_detail table
    op.create_table('exit_order_detail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['product_batch.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['exit_order.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('exit_order_detail')
    op.drop_table('exit_order')
