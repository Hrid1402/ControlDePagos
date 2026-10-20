"""agrega moneda a solicitud_aprobacion

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La aprobación autoriza un importe en una moneda: sin la moneda, una deuda que pasa de PEN a USD
# con el mismo número seguiría aprobada. Las solicitudes anteriores quedan en PEN, la única moneda
# que aprobaban los límites.
UPGRADE = """
ALTER TABLE solicitud_aprobacion ADD COLUMN moneda text NOT NULL DEFAULT 'PEN';
ALTER TABLE solicitud_aprobacion ADD CONSTRAINT ck_solicitud_aprobacion_moneda
  CHECK (moneda IN ('PEN', 'USD'));
"""

DOWNGRADE = """
ALTER TABLE solicitud_aprobacion DROP CONSTRAINT ck_solicitud_aprobacion_moneda;
ALTER TABLE solicitud_aprobacion DROP COLUMN moneda;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
