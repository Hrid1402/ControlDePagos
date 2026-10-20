"""agrega clave_evento a notificacion

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# clave_evento identifica evento/destinatario/ciclo: repetir un job no duplica el aviso. Las
# notificaciones anteriores quedan con NULL, que la unicidad no compara.
UPGRADE = """
ALTER TABLE notificacion ADD COLUMN clave_evento text;
ALTER TABLE notificacion ADD CONSTRAINT ck_notificacion_clave_evento
  CHECK (char_length(clave_evento) BETWEEN 1 AND 200);
ALTER TABLE notificacion ADD CONSTRAINT uq_notificacion_usuario_id_clave_evento
  UNIQUE (usuario_id, clave_evento);
"""

DOWNGRADE = """
ALTER TABLE notificacion DROP CONSTRAINT uq_notificacion_usuario_id_clave_evento;
ALTER TABLE notificacion DROP CONSTRAINT ck_notificacion_clave_evento;
ALTER TABLE notificacion DROP COLUMN clave_evento;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
