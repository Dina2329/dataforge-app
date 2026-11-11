from typing import Any

from pydantic import BaseModel


class FieldExport(BaseModel):
    name: str
    field_type: str
    options: dict[str, Any] = {}
    required: bool = False
    is_primary: bool = False


class TableExport(BaseModel):
    name: str
    fields: list[FieldExport]
    rows: list[dict[str, Any]]


class BaseExport(BaseModel):
    """The export/import unit for backup/restore. Deliberately scoped to a
    single Base's tables/fields/rows -- NOT automations, dashboards, views
    beyond grid, or workspace membership. Those all reference field/table ids
    that would need remapping on import (a link_to_record's target_table_id,
    a kanban view's group_field_id, ...); tracking that graph is real scope
    this MVP punts on, same as automations punting on a generic DAG engine.
    Virtual fields (link_to_record/lookup/rollup/formula) are excluded for
    the same reason -- their config can't survive a re-import with new ids."""

    name: str
    tables: list[TableExport]
