import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.query.filter_dsl import compile_filter, parse_filter_expr
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.field_types.types_relational import ROLLUP_AGGREGATES
from app.modules.bases.formula_engine import referenced_field_names
from app.modules.bases.models import Base, Field, Table, View
from app.modules.bases.repository import BaseRepository, FieldRepository, TableRepository, ViewRepository
from app.modules.workspaces.models import WorkspaceMembership, WorkspaceRole
from app.modules.workspaces.permissions import Permission
from app.modules.workspaces.service import WorkspaceService


class BasesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BaseRepository(db)
        self.tables = TableRepository(db)
        self.fields = FieldRepository(db)
        self.views = ViewRepository(db)
        self.workspaces = WorkspaceService(db)
        self.audit = AuditService(db)

    # -- Bases ---------------------------------------------------------

    async def create_base(self, *, workspace_id: uuid.UUID, name: str, user_id: uuid.UUID) -> Base:
        # Reserved for owner/admin specifically, by role literal rather than
        # the generic schema.write permission editors also hold -- see
        # require_owner_or_admin's docstring; mirrors delete_base below so
        # creating and destroying a base's container are gated the same way.
        await self.workspaces.require_owner_or_admin(workspace_id=workspace_id, user_id=user_id)
        base = await self.bases.create(workspace_id=workspace_id, name=name, created_by=user_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="base.created", resource_type="base",
            resource_id=str(base.id), resource_label=name,
        )
        await self.db.commit()
        return base

    async def list_bases(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[Base]:
        await self.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        return await self.bases.list_for_workspace(workspace_id)

    async def get_base(self, *, base_id: uuid.UUID, user_id: uuid.UUID) -> Base:
        base = await self._get_base_or_404(base_id)
        await self.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        return base

    async def _get_base_or_404(self, base_id: uuid.UUID) -> Base:
        base = await self.bases.get(base_id)
        if base is None:
            raise NotFoundError("Base not found")
        return base

    async def _drop_table_physical_resources(self, table: Table) -> None:
        """Drops the table's own physical df_data table plus the join table
        backing any link_to_record field on it -- neither lives in the
        df_meta FK graph, so an ORM-level delete of the Table row alone would
        leave both as permanently orphaned disk space with no metadata
        pointing at them."""
        fields = await self.fields.list_for_table(table.id)
        for field in fields:
            if field.field_type == "link_to_record":
                await schema_service.drop_link_table(self.db, field.options["link_table_name"])
        await schema_service.drop_physical_table(self.db, table.physical_table_name)

    async def delete_base(self, *, base_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Irreversible -- takes every table (and its data), view, dashboard
        widget bound to those tables, and automation on those tables down
        with it. Restricted to owner/admin (see
        WorkspaceService.require_owner_or_admin), not the generic
        schema.write permission editors also hold."""
        base = await self._get_base_or_404(base_id)
        await self.workspaces.require_owner_or_admin(workspace_id=base.workspace_id, user_id=user_id)

        for table in await self.tables.list_for_base(base_id):
            await self._drop_table_physical_resources(table)

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="base.deleted", resource_type="base",
            resource_id=str(base.id), resource_label=base.name,
        )
        await self.bases.delete(base)
        await self.db.commit()

    # -- Tables ----------------------------------------------------------

    async def create_table(self, *, base_id: uuid.UUID, name: str, user_id: uuid.UUID) -> Table:
        return await self.create_table_with_fields(
            base_id=base_id,
            name=name,
            user_id=user_id,
            field_defs=[{"name": "Name", "field_type": "text", "options": {}, "required": False}],
        )

    async def create_table_with_fields(
        self, *, base_id: uuid.UUID, name: str, user_id: uuid.UUID, field_defs: list[dict], assign_primary: bool = True
    ) -> Table:
        """Shared by the "new blank table" flow (a single default text field) and
        the CSV/connector import flow (one field per source column) — see
        connectors.import_service. Import passes assign_primary=False: an
        imported column is arbitrary source data, not a deliberately-chosen
        display field, and marking it primary blocks it from ever being a bulk
        update "Set" target (see bulk_ops/service.py's is_primary check) purely
        because it happened to be the first column in the source file. Every
        table still has its physical `_row_id` as the real identifier; is_primary
        is only ever a display-field hint that every consumer already treats as
        optional."""
        if not field_defs:
            raise ValidationError("A table needs at least one field")

        base = await self._get_base_or_404(base_id)
        await self.workspaces.require_permission(workspace_id=base.workspace_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)

        physical_name = schema_service.generate_physical_table_name()
        table = await self.tables.create(base_id=base_id, name=name, physical_table_name=physical_name)
        await schema_service.create_physical_table(self.db, physical_name)

        for position, field_def in enumerate(field_defs):
            field = await self.fields.create(
                table_id=table.id,
                name=field_def["name"],
                db_column_name=schema_service.generate_db_column_name(),
                field_type=field_def["field_type"],
                options=field_def.get("options", {}),
                position=position,
                is_primary=assign_primary and position == 0,
                required=field_def.get("required", False),
            )
            await schema_service.add_field_column(self.db, physical_name, field)
        await self.views.create(table_id=table.id, name="Grid view", view_type="grid")

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="table.created", resource_type="table",
            resource_id=str(table.id), resource_label=name,
        )
        await self.db.commit()
        return table

    async def list_tables(self, *, base_id: uuid.UUID, user_id: uuid.UUID) -> list[Table]:
        base = await self._get_base_or_404(base_id)
        await self.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        return await self.tables.list_for_base(base_id)

    async def delete_table(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Irreversible -- takes every row, field, view, dashboard widget,
        automation, row-level policy, and bulk-op history entry bound to this
        table down with it. Restricted to owner/admin, not the generic
        schema.write permission editors also hold."""
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        await self.workspaces.require_owner_or_admin(workspace_id=base.workspace_id, user_id=user_id)

        await self._drop_table_physical_resources(table)

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="table.deleted", resource_type="table",
            resource_id=str(table.id), resource_label=table.name,
        )
        await self.tables.delete(table)
        await self.db.commit()

    async def _get_table_or_404(self, table_id: uuid.UUID) -> Table:
        table = await self.tables.get(table_id)
        if table is None:
            raise NotFoundError("Table not found")
        return table

    async def check_table_access(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> Table:
        """Read access — any workspace role. Use check_table_permission for mutations."""
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        await self.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        return table

    async def check_table_permission(self, *, table_id: uuid.UUID, user_id: uuid.UUID, permission: Permission) -> Table:
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        await self.workspaces.require_permission(workspace_id=base.workspace_id, user_id=user_id, permission=permission)
        return table

    async def check_table_permission_with_context(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, permission: Permission
    ) -> tuple[Table, uuid.UUID, WorkspaceMembership]:
        """Same check as check_table_permission, but also hands back the
        workspace_id and membership (which carries .role) it already had to
        fetch to do that check -- a hot record-write path (create/update/
        delete) needs both again right after, for the audit log's
        workspace_id and row-level-policy's owner/admin bypass respectively.
        Calling get_workspace_id_for_table / get_role_for_table afterward
        would silently re-run the same table+base+membership queries a
        second and third time (confirmed via load-test profiling: this was
        ~50ms of a single write's ~220ms total under 20-way concurrency)."""
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        membership = await self.workspaces.require_permission(workspace_id=base.workspace_id, user_id=user_id, permission=permission)
        return table, base.workspace_id, membership

    async def get_workspace_id_for_table(self, table_id: uuid.UUID) -> uuid.UUID:
        """For audit logging call sites that already hold a permission-checked
        table_id and just need the workspace_id to attribute the log entry to."""
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        return base.workspace_id

    async def get_role_for_table(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceRole:
        """For row-level policy enforcement: owners/admins always bypass a
        row-level scope, so callers need the role, not just membership."""
        table = await self._get_table_or_404(table_id)
        base = await self._get_base_or_404(table.base_id)
        membership = await self.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        return WorkspaceRole(membership.role)

    async def get_table_detail(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Table, list[Field], list[View]]:
        table = await self.check_table_access(table_id=table_id, user_id=user_id)
        fields = await self.fields.list_for_table(table_id)
        views = await self.views.list_for_table(table_id)
        return table, fields, views

    async def get_table_fields_unchecked(self, *, table_id: uuid.UUID) -> tuple[Table, list[Field]]:
        """Bypasses workspace membership checks. Only call this from a path that
        has already authorized access some other way (e.g. a dashboard's public
        share token) -- never expose it behind an authenticated-but-unscoped route."""
        table = await self._get_table_or_404(table_id)
        fields = await self.fields.list_for_table(table_id)
        return table, fields

    # -- Fields ------------------------------------------------------------

    async def create_field(
        self,
        *,
        table_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        field_type: str,
        options: dict,
        required: bool,
    ) -> Field:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        field_type_obj = get_field_type(field_type)  # raises ValidationError on an unknown type key

        existing = await self.fields.list_for_table(table_id)
        options = await self._prepare_field_options(
            table=table, field_type=field_type, options=options, existing_fields=existing, user_id=user_id
        )

        field = await self.fields.create(
            table_id=table_id,
            name=name,
            db_column_name=schema_service.generate_db_column_name(),
            field_type=field_type,
            options=options,
            position=len(existing),
            is_primary=False,
            required=required,
        )
        if field_type == "link_to_record":
            await schema_service.create_link_table(self.db, options["link_table_name"])
        elif not field_type_obj.is_virtual:
            await schema_service.add_field_column(self.db, table.physical_table_name, field)

        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="field.created", resource_type="field",
            resource_id=str(field.id), resource_label=name, details={"field_type": field_type, "table_id": str(table_id)},
        )
        await self.db.commit()
        return field

    async def _prepare_field_options(
        self, *, table: Table, field_type: str, options: dict, existing_fields: list[Field], user_id: uuid.UUID
    ) -> dict:
        """Validates field_type-specific options and returns an augmented copy
        (link_table_name is generated here, never client-supplied)."""
        if field_type == "link_to_record":
            target_table_id_raw = options.get("target_table_id")
            if not target_table_id_raw:
                raise ValidationError("link_to_record requires target_table_id")
            target_table_id = uuid.UUID(str(target_table_id_raw))
            target_table = await self.check_table_access(table_id=target_table_id, user_id=user_id)
            base = await self.get_base(base_id=table.base_id, user_id=user_id)
            target_base = await self.get_base(base_id=target_table.base_id, user_id=user_id)
            if base.workspace_id != target_base.workspace_id:
                raise ValidationError("The linked table must be in the same workspace")
            return {**options, "target_table_id": str(target_table_id), "link_table_name": schema_service.generate_link_table_name()}

        if field_type in ("lookup", "rollup"):
            link_field_id_raw = options.get("link_field_id")
            target_field_id_raw = options.get("target_field_id")
            if not link_field_id_raw or not target_field_id_raw:
                raise ValidationError(f"{field_type} requires link_field_id and target_field_id")
            link_field = await self.fields.get(uuid.UUID(str(link_field_id_raw)))
            if link_field is None or link_field.table_id != table.id or link_field.field_type != "link_to_record":
                raise ValidationError("link_field_id must reference a link_to_record field on this table")
            target_table_id = uuid.UUID(link_field.options["target_table_id"])
            target_field = await self.fields.get(uuid.UUID(str(target_field_id_raw)))
            if target_field is None or target_field.table_id != target_table_id:
                raise ValidationError("target_field_id must reference a field on the linked table")
            if get_field_type(target_field.field_type).is_virtual:
                raise ValidationError("target_field_id must reference a plain field, not another lookup/rollup/formula")
            if field_type == "rollup":
                aggregate = options.get("aggregate")
                if aggregate not in ROLLUP_AGGREGATES:
                    raise ValidationError(f"aggregate must be one of {', '.join(ROLLUP_AGGREGATES)}")
            return {**options, "link_field_id": str(link_field.id), "target_field_id": str(target_field.id)}

        if field_type == "formula":
            expression = options.get("expression")
            if not expression or not str(expression).strip():
                raise ValidationError("formula requires a non-empty expression")
            fields_by_name = {f.name: f for f in existing_fields}
            unknown = referenced_field_names(expression) - set(fields_by_name)
            if unknown:
                raise ValidationError(f"Formula references unknown field(s): {', '.join(sorted(unknown))}")
            chained = [n for n in referenced_field_names(expression) if fields_by_name[n].field_type == "formula"]
            if chained:
                raise ValidationError(f"Formula cannot reference another formula field: {', '.join(chained)}")
            return {**options, "expression": str(expression)}

        if options.get("exclude_values_from") is not None:
            options = await self._validate_exclude_mapping(table=table, field_type=field_type, options=options, user_id=user_id)

        return options

    async def _validate_exclude_mapping(self, *, table: Table, field_type: str, options: dict, user_id: uuid.UUID) -> dict:
        """exclude_values_from = {"table_id", "field_id"}: a plain field (never
        link_to_record/lookup/rollup/formula -- no real column to compare --
        nor attachment, same ineligible set GridFilterDialog.tsx already
        excludes from filtering) can point at one specific field on one
        specific table, used only to suggest fewer filter values (see
        RecordService.distinct_field_values) -- never to hide rows. The
        target is deliberately NOT required to share this field's name."""
        if get_field_type(field_type).is_virtual or field_type == "attachment":
            raise ValidationError(f"exclude_values_from is not supported for field type '{field_type}'")

        mapping = options["exclude_values_from"]
        target_table_id_raw = mapping.get("table_id")
        target_field_id_raw = mapping.get("field_id")
        if not target_table_id_raw or not target_field_id_raw:
            raise ValidationError("exclude_values_from requires table_id and field_id")

        target_table_id = uuid.UUID(str(target_table_id_raw))
        target_table = await self.check_table_access(table_id=target_table_id, user_id=user_id)
        base = await self.get_base(base_id=table.base_id, user_id=user_id)
        target_base = await self.get_base(base_id=target_table.base_id, user_id=user_id)
        if base.workspace_id != target_base.workspace_id:
            raise ValidationError("The exclusion-mapped table must be in the same workspace")

        target_field = await self.fields.get(uuid.UUID(str(target_field_id_raw)))
        if target_field is None or target_field.table_id != target_table_id:
            raise ValidationError("exclude_values_from.field_id must reference a field on that table")
        if get_field_type(target_field.field_type).is_virtual:
            raise ValidationError("exclude_values_from.field_id must reference a plain field, not a lookup/rollup/formula")

        return {**options, "exclude_values_from": {"table_id": str(target_table_id), "field_id": str(target_field.id)}}

    async def update_field(
        self,
        *,
        table_id: uuid.UUID,
        field_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        required: bool | None,
        options: dict | None,
    ) -> Field:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        field = await self.fields.get(field_id)
        if field is None or field.table_id != table_id:
            raise NotFoundError("Field not found")

        if name is not None:
            if not name.strip():
                raise ValidationError("Field name cannot be empty")
            field.name = name.strip()
        if required is not None:
            field.required = required
        if options is not None:
            # exclude_values_from is handled first and independently of the
            # type-dispatch below -- it's valid on any plain (non-virtual,
            # non-attachment) field type, not just the two structural cases
            # that block handles. `null` clears an existing mapping.
            if "exclude_values_from" in options:
                if options["exclude_values_from"] is None:
                    field.options = {k: v for k, v in field.options.items() if k != "exclude_values_from"}
                else:
                    validated = await self._validate_exclude_mapping(
                        table=table, field_type=field.field_type, options=options, user_id=user_id
                    )
                    field.options = {**field.options, "exclude_values_from": validated["exclude_values_from"]}
                options = {k: v for k, v in options.items() if k != "exclude_values_from"}

            # The structural parts of options (link_table_name, target_table_id,
            # link_field_id, ...) are set once at creation and never editable
            # here -- only the two field types with genuinely user-facing,
            # safely-revisable options are allowed through. (options may now be
            # empty if the only key supplied was exclude_values_from, already
            # handled above -- nothing left to validate against a type.)
            if options:
                if field.field_type == "single_select":
                    field.options = {**field.options, "choices": options.get("choices", field.options.get("choices", []))}
                elif field.field_type == "formula":
                    expression = options.get("expression")
                    if not expression or not str(expression).strip():
                        raise ValidationError("formula requires a non-empty expression")
                    existing_fields = await self.fields.list_for_table(table_id)
                    fields_by_name = {f.name: f for f in existing_fields if f.id != field.id}
                    unknown = referenced_field_names(expression) - set(fields_by_name)
                    if unknown:
                        raise ValidationError(f"Formula references unknown field(s): {', '.join(sorted(unknown))}")
                    chained = [n for n in referenced_field_names(expression) if fields_by_name[n].field_type == "formula"]
                    if chained:
                        raise ValidationError(f"Formula cannot reference another formula field: {', '.join(chained)}")
                    field.options = {**field.options, "expression": str(expression).strip()}
                else:
                    raise ValidationError(f"Options cannot be edited for field type '{field.field_type}'")

        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="field.updated", resource_type="field",
            resource_id=str(field.id), resource_label=field.name, details={"field_type": field.field_type},
        )
        await self.db.commit()
        return field

    async def delete_field(self, *, table_id: uuid.UUID, field_id: uuid.UUID, user_id: uuid.UUID) -> None:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        field = await self.fields.get(field_id)
        if field is None or field.table_id != table_id:
            raise NotFoundError("Field not found")
        if field.is_primary:
            raise ValidationError("The primary field cannot be deleted")

        # Deferred import: app.modules.connectors imports BasesService itself
        # (sync_service.py/import_service.py), so importing it back at module
        # level here would be circular.
        from app.modules.connectors.repository import TableSyncConfigRepository

        sync_config = await TableSyncConfigRepository(self.db).get_for_table(table_id)
        if sync_config is not None and sync_config.external_pk_column == field.name:
            raise ValidationError(
                f"'{field.name}' backs this table's sync primary key (external_pk_column) -- "
                "unlink sync first, or pick a different column to delete"
            )

        field_type_obj = get_field_type(field.field_type)
        if field.field_type == "link_to_record":
            await schema_service.drop_link_table(self.db, field.options["link_table_name"])
        elif not field_type_obj.is_virtual:
            await schema_service.drop_field_column(self.db, table.physical_table_name, field)

        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="field.deleted", resource_type="field",
            resource_id=str(field.id), resource_label=field.name, details={"field_type": field.field_type},
        )
        await self.fields.delete(field)
        await self.db.commit()

    # -- Views ---------------------------------------------------------

    VIEW_TYPES = {"grid", "kanban", "form"}

    async def _validate_view_config(self, *, table_id: uuid.UUID, view_type: str, config: dict) -> dict:
        sort = config.get("sort")
        if sort is not None:
            if not isinstance(sort, list):
                raise ValidationError("sort must be a list of {field, direction}")
            fields = await self.fields.list_for_table(table_id)
            for spec in sort:
                if spec.get("direction") not in ("asc", "desc"):
                    raise ValidationError("sort.direction must be 'asc' or 'desc'")
                field = next((f for f in fields if f.name == spec.get("field")), None)
                if field is None or get_field_type(field.field_type).is_virtual:
                    raise ValidationError(f"Field '{spec.get('field')}' cannot be sorted")

        view_filter = config.get("filter")
        if view_filter is not None:
            filter_expr = parse_filter_expr(view_filter)
            fields = await self.fields.list_for_table(table_id)
            sa_table = schema_service.build_data_table(
                (await self.tables.get(table_id)).physical_table_name, fields
            )
            columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
            compile_filter(filter_expr, columns_map)  # raises ValidationError on an unknown/virtual field

        if view_type == "kanban":
            group_field_id_raw = config.get("group_field_id")
            if not group_field_id_raw:
                raise ValidationError("kanban views require a group_field_id")
            group_field = await self.fields.get(uuid.UUID(str(group_field_id_raw)))
            if group_field is None or group_field.table_id != table_id or group_field.field_type != "single_select":
                raise ValidationError("group_field_id must reference a single_select field on this table")
            return {**config, "group_field_id": str(group_field.id)}

        if view_type == "form":
            fields = await self.fields.list_for_table(table_id)
            writable_ids = {str(f.id) for f in fields if not get_field_type(f.field_type).is_virtual}
            field_ids = config.get("field_ids")
            if field_ids is None:
                # Default to every writable field, in table order -- a form
                # can't collect a computed/linked value, only real columns.
                return {**config, "field_ids": [str(f.id) for f in fields if str(f.id) in writable_ids]}
            unknown = {str(i) for i in field_ids} - writable_ids
            if unknown:
                raise ValidationError(f"Form references unknown or non-writable field(s): {', '.join(sorted(unknown))}")
            return {**config, "field_ids": [str(i) for i in field_ids]}

        return config

    async def create_view(self, *, table_id: uuid.UUID, user_id: uuid.UUID, name: str, view_type: str, config: dict) -> View:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        if view_type not in self.VIEW_TYPES:
            raise ValidationError(f"Unknown view type: {view_type}")
        config = await self._validate_view_config(table_id=table_id, view_type=view_type, config=config)

        view = await self.views.create(table_id=table_id, name=name, view_type=view_type, config=config)
        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="view.created", resource_type="view",
            resource_id=str(view.id), resource_label=name, details={"view_type": view_type, "table_id": str(table_id)},
        )
        await self.db.commit()
        return view

    async def update_view(
        self, *, table_id: uuid.UUID, view_id: uuid.UUID, user_id: uuid.UUID, name: str | None, config: dict | None
    ) -> View:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        view = await self.views.get(view_id)
        if view is None or view.table_id != table_id:
            raise NotFoundError("View not found")

        if name is not None:
            view.name = name
        if config is not None:
            view.config = await self._validate_view_config(table_id=table_id, view_type=view.view_type, config=config)

        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="view.updated", resource_type="view",
            resource_id=str(view.id), resource_label=view.name, details={"table_id": str(table_id)},
        )
        await self.db.commit()
        return view

    async def delete_view(self, *, table_id: uuid.UUID, view_id: uuid.UUID, user_id: uuid.UUID) -> None:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        view = await self.views.get(view_id)
        if view is None or view.table_id != table_id:
            raise NotFoundError("View not found")

        existing_views = await self.views.list_for_table(table_id)
        if len(existing_views) <= 1:
            raise ValidationError("A table must have at least one view")

        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="view.deleted", resource_type="view",
            resource_id=str(view.id), resource_label=view.name, details={"table_id": str(table_id)},
        )
        await self.views.delete(view)
        await self.db.commit()

    # -- Form view sharing -----------------------------------------------
    # Mirrors DashboardService's share-link pattern -- only form views ever
    # populate share_token, since only a form has a "let strangers submit
    # into this table" story; grid/kanban links would just be a read leak.

    async def create_view_share_link(self, *, table_id: uuid.UUID, view_id: uuid.UUID, user_id: uuid.UUID) -> View:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        view = await self.views.get(view_id)
        if view is None or view.table_id != table_id:
            raise NotFoundError("View not found")
        if view.view_type != "form":
            raise ValidationError("Only form views can be shared")

        if not view.share_token:
            view.share_token = secrets.token_urlsafe(24)
            base = await self._get_base_or_404(table.base_id)
            await self.audit.log(
                workspace_id=base.workspace_id, user_id=user_id, action="view.share_link_created", resource_type="view",
                resource_id=str(view.id), resource_label=view.name, details={"table_id": str(table_id)},
            )
            await self.db.commit()
        return view

    async def revoke_view_share_link(self, *, table_id: uuid.UUID, view_id: uuid.UUID, user_id: uuid.UUID) -> View:
        table = await self.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        view = await self.views.get(view_id)
        if view is None or view.table_id != table_id:
            raise NotFoundError("View not found")

        view.share_token = None
        base = await self._get_base_or_404(table.base_id)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="view.share_link_revoked", resource_type="view",
            resource_id=str(view.id), resource_label=view.name, details={"table_id": str(table_id)},
        )
        await self.db.commit()
        return view

    async def get_public_form(self, *, token: str) -> tuple[Table, View, list[Field]]:
        """No auth -- the share token itself is the authorization, same as a
        dashboard share link. Returns only the fields the form was configured
        to collect, in that order."""
        view = await self.views.get_by_share_token(token)
        if view is None or view.view_type != "form":
            raise NotFoundError("Form not found")

        table, fields = await self.get_table_fields_unchecked(table_id=view.table_id)
        # Iterate field_ids directly, NOT a set() of it -- sets don't
        # preserve insertion order, which silently scrambled the form's field
        # order (caught in manual verification, not by any type checker).
        allowed_ids = view.config.get("field_ids") or []
        fields_by_id = {str(f.id): f for f in fields}
        visible_fields = [fields_by_id[fid] for fid in allowed_ids if fid in fields_by_id]
        return table, view, visible_fields
