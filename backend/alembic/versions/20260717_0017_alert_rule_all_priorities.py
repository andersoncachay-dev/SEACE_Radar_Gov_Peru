from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0017"
down_revision = "20260717_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The rule form no longer exposes a minimum-priority selector - rules are
    # scoped only by business keywords now, so no existing rule should keep
    # silently restricting itself to a priority tier the user can no longer
    # see or change from the UI.
    op.execute(sa.text("UPDATE alert_rules SET min_priority = 'C'"))


def downgrade() -> None:
    pass
