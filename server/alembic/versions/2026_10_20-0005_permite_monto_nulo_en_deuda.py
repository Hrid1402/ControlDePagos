"""permite monto nulo en deuda

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Una deuda recurrente variable nace en esperando_recibo sin conocer el importe del mes, y una
# deuda anulada conserva el suyo (o su ausencia). Todo otro estado exige un monto positivo: no se
# usa cero ni un importe ficticio. El CHECK no puede ser solo "monto > 0 OR ...": con monto NULL
# esa expresión da NULL y PostgreSQL lo acepta, así que se pide NOT NULL de forma explícita. Las
# deudas existentes ya tienen monto positivo y no cambian.
UPGRADE = """
ALTER TABLE deuda ALTER COLUMN monto DROP NOT NULL;
ALTER TABLE deuda DROP CONSTRAINT ck_deuda_monto;
ALTER TABLE deuda ADD CONSTRAINT ck_deuda_monto CHECK (
  (monto IS NOT NULL AND monto > 0)
  OR (monto IS NULL AND estado IN ('esperando_recibo', 'anulada'))
);
"""

# Volver a NOT NULL con deudas sin monto obligaría a inventar un importe o a borrar datos: se
# detiene con un mensaje claro y no se toca nada.
DOWNGRADE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM deuda WHERE monto IS NULL) THEN
    RAISE EXCEPTION 'No se puede deshacer la migración 0005: hay deudas sin monto '
      '(esperando recibo o anuladas). Confirma su monto o elimínalas antes de volver atrás.';
  END IF;
END
$$;
ALTER TABLE deuda DROP CONSTRAINT ck_deuda_monto;
ALTER TABLE deuda ADD CONSTRAINT ck_deuda_monto CHECK (monto > 0);
ALTER TABLE deuda ALTER COLUMN monto SET NOT NULL;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
