import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class RowLevelPolicy(Model):
    """Scopes one member's visibility on one table to rows matching a stored
    FilterExpr (architecture plan, section 3: "a permission grant can carry a
    FilterExpr as its row-level scope"). One policy per (table, user) pair —
    a member either has an unscoped view of a table or exactly one scope,
    never several ORed/ANDed together; that composition can be added later
    if a real use case needs it.

    Owners/admins always bypass any policy that names them (enforced in
    RowPolicyService.get_effective_filter, not here) -- this table only
    stores the scope, it doesn't know who's exempt."""

    __tablename__ = "row_level_policies"
    __table_args__ = (UniqueConstraint("table_id", "user_id", name="uq_row_level_policy_table_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filter: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
