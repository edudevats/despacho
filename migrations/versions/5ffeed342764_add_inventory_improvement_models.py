"""Add inventory improvement models

Revision ID: 5ffeed342764
Revises: 120904668044
Create Date: 2026-02-05 01:18:09.726516

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '5ffeed342764'
down_revision = '120904668044'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if not table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Create tables if they don't exist

    if not table_exists('invoice_template'):
        op.create_table('invoice_template',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    if not table_exists('laboratory'):
        op.create_table('laboratory',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('sanitary_registration', sa.String(length=100), nullable=True),
            sa.Column('active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('company_id', 'name', name='unique_laboratory_per_company')
        )

    if not table_exists('service'):
        op.create_table('service',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('price', sa.Float(), nullable=True),
            sa.Column('sat_key', sa.String(length=10), nullable=True),
            sa.Column('sat_unit_key', sa.String(length=10), nullable=True),
            sa.Column('active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    if not table_exists('purchase_order'):
        op.create_table('purchase_order',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('supplier_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('estimated_total', sa.Float(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.Column('received_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
            sa.ForeignKeyConstraint(['supplier_id'], ['supplier.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    if not table_exists('invoice_template_item'):
        op.create_table('invoice_template_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('item_type', sa.String(length=20), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=True),
            sa.Column('service_id', sa.Integer(), nullable=True),
            sa.Column('quantity', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
            sa.ForeignKeyConstraint(['service_id'], ['service.id'], ),
            sa.ForeignKeyConstraint(['template_id'], ['invoice_template.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    if not table_exists('purchase_order_detail'):
        op.create_table('purchase_order_detail',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('quantity_requested', sa.Integer(), nullable=True),
            sa.Column('quantity_received', sa.Integer(), nullable=True),
            sa.Column('unit_cost', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['purchase_order.id'], ),
            sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # Add columns to product table if they don't exist
    if not column_exists('product', 'profit_margin'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.add_column(sa.Column('profit_margin', sa.Float(), nullable=True))

    if not column_exists('product', 'laboratory_id'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.add_column(sa.Column('laboratory_id', sa.Integer(), nullable=True))

    if not column_exists('product', 'preferred_supplier_id'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.add_column(sa.Column('preferred_supplier_id', sa.Integer(), nullable=True))

    # Add columns to supplier table if they don't exist
    if not column_exists('supplier', 'contact_name'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.add_column(sa.Column('contact_name', sa.String(length=150), nullable=True))

    if not column_exists('supplier', 'payment_terms'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.add_column(sa.Column('payment_terms', sa.String(length=200), nullable=True))

    if not column_exists('supplier', 'is_medication_supplier'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_medication_supplier', sa.Boolean(), nullable=True))


def downgrade():
    # Drop columns from supplier
    if column_exists('supplier', 'is_medication_supplier'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.drop_column('is_medication_supplier')

    if column_exists('supplier', 'payment_terms'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.drop_column('payment_terms')

    if column_exists('supplier', 'contact_name'):
        with op.batch_alter_table('supplier', schema=None) as batch_op:
            batch_op.drop_column('contact_name')

    # Drop columns from product
    if column_exists('product', 'preferred_supplier_id'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.drop_column('preferred_supplier_id')

    if column_exists('product', 'laboratory_id'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.drop_column('laboratory_id')

    if column_exists('product', 'profit_margin'):
        with op.batch_alter_table('product', schema=None) as batch_op:
            batch_op.drop_column('profit_margin')

    # Drop tables
    if table_exists('purchase_order_detail'):
        op.drop_table('purchase_order_detail')

    if table_exists('invoice_template_item'):
        op.drop_table('invoice_template_item')

    if table_exists('purchase_order'):
        op.drop_table('purchase_order')

    if table_exists('service'):
        op.drop_table('service')

    if table_exists('laboratory'):
        op.drop_table('laboratory')

    if table_exists('invoice_template'):
        op.drop_table('invoice_template')
