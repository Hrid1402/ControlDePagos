"""normaliza empresa y código de servicio

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# uq_servicio_codigo (H10 CA03) comparaba el código exacto y lower(empresa_nombre), así que solo
# detectaba duplicados si ambos se guardaban normalizados, como hace la API (TASK-33). Esta
# migración lo asegura en la base: el índice compara el código sin distinguir mayúsculas, el
# código no admite espacios, el nombre manual no admite espacios sobrantes y la empresa tiene una
# sola representación (empresa_id para una del catálogo o empresa_nombre para una manual), para
# que alternar entre ambas no esquive el índice.
#
# Antes de exigirlo normaliza los servicios existentes. Si dos quedan iguales, se detiene con un
# mensaje claro y no toca nada: elegir cuál conservar es una decisión del gerente, no de la
# migración.
UPGRADE = r"""
DO $$
DECLARE
  repetidos integer;
  vacios integer;
BEGIN
  SELECT count(*) INTO vacios FROM servicio
  WHERE regexp_replace(codigo_suministro, '\s', '', 'g') = ''
    OR (empresa_id IS NULL AND regexp_replace(coalesce(empresa_nombre, ''), '\s', '', 'g') = '');
  IF vacios > 0 THEN
    RAISE EXCEPTION 'No se puede aplicar la migración 0006: %% servicios tienen el código o el '
      'nombre de la empresa en blanco. Complétalos antes de migrar.', vacios;
  END IF;

  SELECT count(*) INTO repetidos FROM (
    SELECT 1 FROM servicio
    WHERE eliminado_en IS NULL
    GROUP BY
      gerente_id,
      coalesce(
        empresa_id::text,
        lower(btrim(regexp_replace(empresa_nombre, '\s+', ' ', 'g')))
      ),
      upper(regexp_replace(codigo_suministro, '\s', '', 'g'))
    HAVING count(*) > 1
  ) AS grupos;
  IF repetidos > 0 THEN
    RAISE EXCEPTION 'No se puede aplicar la migración 0006: %% grupos de servicios quedan con la '
      'misma empresa y el mismo código al normalizarlos. Elimina o corrige los repetidos antes '
      'de migrar.', repetidos;
  END IF;
END
$$;

UPDATE servicio SET
  empresa_nombre = CASE
    WHEN empresa_id IS NOT NULL THEN NULL
    ELSE btrim(regexp_replace(empresa_nombre, '\s+', ' ', 'g'))
  END,
  codigo_suministro = upper(regexp_replace(codigo_suministro, '\s', '', 'g'))
WHERE empresa_nombre IS DISTINCT FROM CASE
    WHEN empresa_id IS NOT NULL THEN NULL
    ELSE btrim(regexp_replace(empresa_nombre, '\s+', ' ', 'g'))
  END
  OR codigo_suministro <> upper(regexp_replace(codigo_suministro, '\s', '', 'g'));

ALTER TABLE servicio DROP CONSTRAINT ck_servicio_empresa;
ALTER TABLE servicio ADD CONSTRAINT ck_servicio_empresa
  CHECK ((empresa_id IS NULL) <> (empresa_nombre IS NULL));
ALTER TABLE servicio ADD CONSTRAINT ck_servicio_empresa_nombre
  CHECK (empresa_nombre ~ '^\S+( \S+)*$');
ALTER TABLE servicio ADD CONSTRAINT ck_servicio_codigo CHECK (codigo_suministro ~ '^\S+$');

DROP INDEX uq_servicio_codigo;
CREATE UNIQUE INDEX uq_servicio_codigo ON servicio (
  gerente_id, coalesce(empresa_id::text, lower(empresa_nombre)), upper(codigo_suministro)
) WHERE eliminado_en IS NULL;
"""

# Los datos ya normalizados siguen siendo válidos con las reglas anteriores: solo se quitan.
DOWNGRADE = """
DROP INDEX uq_servicio_codigo;
CREATE UNIQUE INDEX uq_servicio_codigo ON servicio (
  gerente_id, coalesce(empresa_id::text, lower(empresa_nombre)), codigo_suministro
) WHERE eliminado_en IS NULL;
ALTER TABLE servicio DROP CONSTRAINT ck_servicio_codigo;
ALTER TABLE servicio DROP CONSTRAINT ck_servicio_empresa_nombre;
ALTER TABLE servicio DROP CONSTRAINT ck_servicio_empresa;
ALTER TABLE servicio ADD CONSTRAINT ck_servicio_empresa
  CHECK (empresa_id IS NOT NULL OR empresa_nombre IS NOT NULL);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
