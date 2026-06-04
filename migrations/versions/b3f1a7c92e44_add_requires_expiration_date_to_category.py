"""add requires_expiration_date to product_category and make product_batch.expiration_date nullable

Revision ID: b3f1a7c92e44
Revises: 0547f10f60a1
Create Date: 2026-06-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1a7c92e44'
down_revision = '0547f10f60a1'
branch_labels = None
depends_on = None


def upgrade():
    # Nuevo flag: la categoría exige fecha de caducidad obligatoria al recibir lotes
    with op.batch_alter_table('product_category', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('requires_expiration_date', sa.Boolean(), nullable=True, server_default=sa.false())
        )

    # La caducidad del lote pasa a ser opcional; la obligatoriedad la controla la categoría
    with op.batch_alter_table('product_batch', schema=None) as batch_op:
        batch_op.alter_column(
            'expiration_date',
            existing_type=sa.Date(),
            nullable=True
        )

    # Activar caducidad obligatoria en las categorías Medicamento e Insumo existentes
    op.execute(
        "UPDATE product_category SET requires_expiration_date = 1 "
        "WHERE name IN ('Medicamento', 'Insumo')"
    )


def downgrade():
    with op.batch_alter_table('product_batch', schema=None) as batch_op:
        batch_op.alter_column(
            'expiration_date',
            existing_type=sa.Date(),
            nullable=False
        )

    with op.batch_alter_table('product_category', schema=None) as batch_op:
        batch_op.drop_column('requires_expiration_date')
