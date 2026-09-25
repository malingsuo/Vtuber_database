"""inventory movements append-only reversal

流水帳改為只追加：更正以沖銷紀錄表示（reverses_movement_id），
預購記下自己的出貨異動（shipment_movement_id），出貨退回時據此沖銷。

約束一律具名：SQLite 的 batch 模式重建表時需要名字，downgrade 也才刪得掉。

Revision ID: f703cb560377
Revises: 0153d9a7d3b0
Create Date: 2026-09-25 22:32:24.323134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f703cb560377'
down_revision: Union[str, Sequence[str], None] = '0153d9a7d3b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('inventory_movements') as batch_op:
        batch_op.add_column(
            sa.Column('reverses_movement_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_inventory_movements_reverses_movement_id',
            'inventory_movements', ['reverses_movement_id'], ['id'],
        )
        batch_op.create_unique_constraint(
            'uq_inventory_movements_reverses_movement_id', ['reverses_movement_id']
        )

    with op.batch_alter_table('preorders') as batch_op:
        batch_op.add_column(
            sa.Column('shipment_movement_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_preorders_shipment_movement_id',
            'inventory_movements', ['shipment_movement_id'], ['id'],
        )
        batch_op.create_unique_constraint(
            'uq_preorders_shipment_movement_id', ['shipment_movement_id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('preorders') as batch_op:
        batch_op.drop_constraint('uq_preorders_shipment_movement_id', type_='unique')
        batch_op.drop_constraint('fk_preorders_shipment_movement_id', type_='foreignkey')
        batch_op.drop_column('shipment_movement_id')

    with op.batch_alter_table('inventory_movements') as batch_op:
        batch_op.drop_constraint(
            'uq_inventory_movements_reverses_movement_id', type_='unique'
        )
        batch_op.drop_constraint(
            'fk_inventory_movements_reverses_movement_id', type_='foreignkey'
        )
        batch_op.drop_column('reverses_movement_id')
