from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260722_0032"
down_revision = "20260722_0031"
branch_labels = None
depends_on = None

# Las etapas nuevas no deben llegar con las alertas "Atender"/"Urgente" ya activadas
# -el gestor las prende a mano si las quiere para esa etapa puntual-. Esto solo cambia
# el default para etapas que se creen de aqui en adelante; no toca el valor ya elegido
# en etapas existentes (nadie pidio resetear lo que ya esta configurado).


def upgrade() -> None:
    op.alter_column("opportunity_tracking_stages", "alert_atender_enabled", server_default=sa.false())
    op.alter_column("opportunity_tracking_stages", "alert_urgente_enabled", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("opportunity_tracking_stages", "alert_atender_enabled", server_default=sa.true())
    op.alter_column("opportunity_tracking_stages", "alert_urgente_enabled", server_default=sa.true())
