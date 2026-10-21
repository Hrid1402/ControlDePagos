"""agrega pago_realizado_en a deuda

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cuándo se declaró hecho el pago presencial en la ruta (H23 CA03). pago_realizado ya existe; la
# fecha va aparte de pago_iniciado_en, que es cuándo se empezó a pagar. Las dos se limpian juntas:
# una fecha sin declaración, o al revés, sería un dato inconsistente. Una deuda declarada que ya
# tenía la marca toma como fecha el inicio del intento, el dato más cercano que hay.
UPGRADE = """
ALTER TABLE deuda ADD COLUMN pago_realizado_en timestamptz;
UPDATE deuda SET pago_realizado_en = coalesce(pago_iniciado_en, now()) WHERE pago_realizado;
ALTER TABLE deuda ADD CONSTRAINT ck_deuda_pago_realizado
  CHECK (pago_realizado = (pago_realizado_en IS NOT NULL));
"""

DOWNGRADE = """
ALTER TABLE deuda DROP CONSTRAINT ck_deuda_pago_realizado;
ALTER TABLE deuda DROP COLUMN pago_realizado_en;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
