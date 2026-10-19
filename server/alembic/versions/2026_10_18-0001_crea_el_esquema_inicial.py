"""crea el esquema inicial

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB = Path(__file__).resolve().parents[2] / "db"


def upgrade() -> None:
    op.get_bind().exec_driver_sql((DB / "esquema.sql").read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql((DB / "esquema_down.sql").read_text())
