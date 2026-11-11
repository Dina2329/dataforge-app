"""Computes chart/KPI/table data for a widget, from one of two sources:
 - a real table's dynamic physical table (compute_widget_data) -- the same
   schema_service/FilterExpr building blocks records and bulk_ops already
   use (architecture plan, section 2: one filter language, every call site).
 - the cross-workspace audit log (compute_audit_widget_data) -- a fixed set
   of pseudo-columns (action, resource_type, actor_email, created_at, ...)
   over AuditLogEntry joined to User, scoped to one workspace.

Both funnel into the same _compute_aggregated_widget_data for kpi/pivot/
bar/line/pie, parameterized by a columns_map + which of those columns are
dates (for pivot's day/week/month bucketing) -- only the "table" widget
type (a flat row listing) differs enough per source to stay separate."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.core.query.filter_dsl import compile_filter, parse_filter_expr
from app.modules.auth.models import User
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field, Table
from app.modules.audit.models import AuditLogEntry
from app.modules.dashboards.models import Widget

TABLE_WIDGET_ROW_LIMIT = 100
_DATE_GRANULARITIES = {"day", "week", "month"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _build_aggregate(aggregate: str, y_field_name: str | None, columns_map: dict):
    if aggregate == "count":
        return func.count()
    if not y_field_name or y_field_name not in columns_map:
        raise ValidationError("This aggregate requires a y_field")
    column = columns_map[y_field_name]
    if aggregate == "sum":
        return func.sum(column)
    if aggregate == "avg":
        return func.avg(column)
    if aggregate == "min":
        return func.min(column)
    if aggregate == "max":
        return func.max(column)
    raise ValidationError(f"Unsupported aggregate: {aggregate}")


async def compute_widget_data(db: AsyncSession, table: Table, fields: list[Field], widget: Widget) -> dict[str, Any]:
    sa_table = schema_service.build_data_table(table.physical_table_name, fields)
    # Virtual fields (link/lookup/rollup/formula) have no real column, so
    # widgets can't group/filter/aggregate on them at all in this MVP -- the
    # existing "not in columns_map" checks below already surface that as a
    # clean ValidationError instead of a KeyError.
    columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
    date_field_names = {f.name for f in fields if f.field_type == "date"}

    if widget.widget_type == "table":
        where_clause = None
        if widget.config.get("filter"):
            where_clause = compile_filter(parse_filter_expr(widget.config["filter"]), columns_map)
        stmt = select(sa_table).order_by(sa_table.c._row_id).limit(TABLE_WIDGET_ROW_LIMIT)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        rows = (await db.execute(stmt)).all()
        result_rows = []
        for row in rows:
            mapping = row._mapping
            values = {
                f.name: get_field_type(f.field_type).from_storage(mapping[f.db_column_name], f.options)
                for f in fields
                if not get_field_type(f.field_type).is_virtual
            }
            result_rows.append({"row_id": mapping["_row_id"], "values": values})
        return {"rows": result_rows}

    return await _compute_aggregated_widget_data(
        db, columns_map=columns_map, date_field_names=date_field_names, from_clause=sa_table, widget=widget
    )


async def compute_audit_widget_data(db: AsyncSession, workspace_id: uuid.UUID, widget: Widget) -> dict[str, Any]:
    """Same widget types as a real table, but over a fixed set of
    pseudo-columns describing an audit log entry -- there's no per-workspace
    schema to introspect here, every workspace's audit log has exactly these
    columns. actor_email comes from an outer join (a system action has no
    user_id, and should still show up as a row/group, not get silently
    dropped by an inner join)."""
    columns_map = {
        "action": AuditLogEntry.action,
        "resource_type": AuditLogEntry.resource_type,
        "resource_id": AuditLogEntry.resource_id,
        "resource_label": AuditLogEntry.resource_label,
        "actor_email": User.email,
        "created_at": AuditLogEntry.created_at,
        # Only a subset of actions carry a table (e.g. record.*, field.*) --
        # null for the rest (dashboard.*, base.*, member.*, ...). Filter-only
        # (not offered as a Group by/Rows/Columns field -- a raw table UUID
        # makes a useless axis label); the frontend resolves the table NAME
        # the user picks back into this UUID before sending the filter.
        # .as_string() is required for a plain (non-JSONB) JSON column to
        # get Postgres's "->>" text extraction instead of "->"'s JSON value
        # (which can't be compared against a plain string).
        "table_id": AuditLogEntry.details["table_id"].as_string(),
    }
    date_field_names = {"created_at"}
    from_clause = AuditLogEntry.__table__.outerjoin(User.__table__, AuditLogEntry.user_id == User.id)
    workspace_filter = AuditLogEntry.workspace_id == workspace_id

    if widget.widget_type == "table":
        stmt = (
            select(
                AuditLogEntry.id.label("row_id"),
                AuditLogEntry.action,
                AuditLogEntry.resource_type,
                AuditLogEntry.resource_label,
                AuditLogEntry.resource_id,
                User.email.label("actor_email"),
                AuditLogEntry.created_at,
            )
            .select_from(from_clause)
            .where(workspace_filter)
            .order_by(AuditLogEntry.created_at.desc())
            .limit(TABLE_WIDGET_ROW_LIMIT)
        )
        if widget.config.get("filter"):
            stmt = stmt.where(compile_filter(parse_filter_expr(widget.config["filter"]), columns_map))
        rows = (await db.execute(stmt)).all()
        result_rows = [
            {
                "row_id": str(r.row_id),
                "values": {
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_label": r.resource_label,
                    "resource_id": r.resource_id,
                    "actor_email": r.actor_email or "System",
                    "created_at": _json_safe(r.created_at),
                },
            }
            for r in rows
        ]
        return {"rows": result_rows}

    return await _compute_aggregated_widget_data(
        db, columns_map=columns_map, date_field_names=date_field_names, from_clause=from_clause, widget=widget,
        extra_where=workspace_filter,
    )


async def _compute_aggregated_widget_data(
    db: AsyncSession, *, columns_map: dict, date_field_names: set[str], from_clause, widget: Widget, extra_where=None
) -> dict[str, Any]:
    where_clauses = [] if extra_where is None else [extra_where]
    if widget.config.get("filter"):
        where_clauses.append(compile_filter(parse_filter_expr(widget.config["filter"]), columns_map))

    aggregate = widget.config.get("aggregate", "count")
    y_field_name = widget.config.get("y_field")
    agg_col = _build_aggregate(aggregate, y_field_name, columns_map)

    if widget.widget_type == "kpi":
        # select_from is required here, not optional -- a bare func.count()
        # (the plain "count everything" case, no y_field) has no column
        # reference of its own for SQLAlchemy to infer a FROM clause from,
        # so without this a KPI with aggregate="count" and no filter would
        # silently compile to "SELECT count(*)" with NO FROM at all (valid
        # SQL, but counts a single dummy row, i.e. always returns 1 -- not
        # the real row count).
        stmt = select(agg_col).select_from(from_clause)
        if where_clauses:
            stmt = stmt.where(*where_clauses)
        value = (await db.execute(stmt)).scalar_one()
        return {"value": _json_safe(value)}

    if widget.widget_type == "pivot":
        return await _compute_pivot(db, columns_map, date_field_names, agg_col, widget, where_clauses, from_clause)

    # bar / line / pie — group by x_field
    x_field_name = widget.config.get("x_field")
    if not x_field_name or x_field_name not in columns_map:
        raise ValidationError(f"Widget type '{widget.widget_type}' requires an x_field")
    x_col = columns_map[x_field_name]

    # select_from matters here for the same reason as the kpi branch above,
    # whenever columns_map spans a join (the audit log's actor_email is a
    # different table than its other columns) -- without it, SQLAlchemy has
    # no way to know the two tables are meant to be joined rather than
    # cross-joined.
    stmt = select(x_col.label("label"), agg_col.label("value")).select_from(from_clause).group_by(x_col).order_by(x_col)
    if where_clauses:
        stmt = stmt.where(*where_clauses)
    rows = (await db.execute(stmt)).all()
    return {"data": [{"label": _json_safe(r.label), "value": _json_safe(r.value)} for r in rows]}


async def _compute_pivot(db, columns_map, date_field_names: set[str], agg_col, widget: Widget, where_clauses: list, from_clause) -> dict[str, Any]:
    """Rows x Columns x aggregate cross-tab, e.g. rows=person, columns=date
    (bucketed to day/week/month when the column field is itself a date --
    otherwise every distinct timestamp would become its own column)."""
    row_field_name = widget.config.get("row_field")
    column_field_name = widget.config.get("column_field")
    if not row_field_name or row_field_name not in columns_map:
        raise ValidationError("Pivot widgets require a row_field")
    if not column_field_name or column_field_name not in columns_map:
        raise ValidationError("Pivot widgets require a column_field")

    row_col = columns_map[row_field_name]
    col_col = columns_map[column_field_name]
    granularity = widget.config.get("date_granularity") or "day"
    date_bucketed = column_field_name in date_field_names and granularity in _DATE_GRANULARITIES
    col_expr = func.date_trunc(granularity, col_col) if date_bucketed else col_col

    stmt = (
        select(row_col.label("row_label"), col_expr.label("col_label"), agg_col.label("value"))
        .select_from(from_clause)
        .group_by(row_col, col_expr)
        .order_by(row_col, col_expr)
    )
    if where_clauses:
        stmt = stmt.where(*where_clauses)
    triples = (await db.execute(stmt)).all()

    row_labels: list[str] = []
    col_labels: list[str] = []
    seen_rows: set[str] = set()
    seen_cols: set[str] = set()
    value_by_pair: dict[tuple[str, str], float | int] = {}
    for r in triples:
        row_label = "—" if r.row_label is None else str(_json_safe(r.row_label))
        if r.col_label is None:
            col_label = "—"
        elif date_bucketed:
            # date_trunc() always returns a full timestamp -- trim back down
            # to just the granularity the user actually asked to see
            # ("2026-11" for month, "2026-11-01" for day/week-start).
            col_label = r.col_label.strftime("%Y-%m") if granularity == "month" else r.col_label.strftime("%Y-%m-%d")
        else:
            col_label = str(_json_safe(r.col_label))
        if row_label not in seen_rows:
            seen_rows.add(row_label)
            row_labels.append(row_label)
        if col_label not in seen_cols:
            seen_cols.add(col_label)
            col_labels.append(col_label)
        value_by_pair[(row_label, col_label)] = 0 if r.value is None else _json_safe(r.value)

    row_labels.sort()
    col_labels.sort()
    cells = [[value_by_pair.get((rl, cl), 0) for cl in col_labels] for rl in row_labels]
    row_totals = [sum(row) for row in cells]
    column_totals = [sum(cells[i][j] for i in range(len(row_labels))) for j in range(len(col_labels))]
    grand_total = sum(row_totals)

    return {
        "pivot": {
            "rows": row_labels,
            "columns": col_labels,
            "cells": cells,
            "row_totals": row_totals,
            "column_totals": column_totals,
            "grand_total": grand_total,
        }
    }
