"""agrega monto y moneda a orden_pago

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La orden urgente autoriza el importe y la moneda exactos que el gerente ordenó. Sin guardarlos,
# un cambio de la deuda después de ordenar pasaría como autorizado. NOT NULL sin valor por
# defecto: ninguna API creaba órdenes antes de esta migración.
UPGRADE = """
ALTER TABLE orden_pago ADD COLUMN monto numeric(12,2) NOT NULL;
ALTER TABLE orden_pago ADD COLUMN moneda text NOT NULL;
ALTER TABLE orden_pago ADD CONSTRAINT ck_orden_pago_monto CHECK (monto > 0);
ALTER TABLE orden_pago ADD CONSTRAINT ck_orden_pago_moneda CHECK (moneda IN ('PEN', 'USD'));
"""

DOWNGRADE = """
ALTER TABLE orden_pago DROP CONSTRAINT ck_orden_pago_moneda;
ALTER TABLE orden_pago DROP CONSTRAINT ck_orden_pago_monto;
ALTER TABLE orden_pago DROP COLUMN moneda;
ALTER TABLE orden_pago DROP COLUMN monto;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
