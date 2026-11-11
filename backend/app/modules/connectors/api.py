import json
import uuid

from fastapi import APIRouter, Form, UploadFile

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.modules.bases.schemas import TableResponse, table_to_response
from app.modules.connectors.base import TableRef
from app.modules.connectors.import_service import ImportService
from app.modules.connectors.registry import get_connector
from app.modules.connectors.pending_sync_service import PendingSyncChangeService
from app.modules.connectors.schemas import (
    ColumnDefResponse,
    ConfigurePullRequest,
    DataSourceResponse,
    ExcelImportResponse,
    ExcelImportResult,
    ExcelInspectResponse,
    ExcelSheetPreview,
    ImportFromSourceRequest,
    PendingSyncChangeResponse,
    RejectSyncChangeRequest,
    SubmitDraftsResponse,
    SyncChangeBatchResponse,
    TableRefResponse,
    TableSyncConfigResponse,
    UpdateTableSyncRequest,
)
from app.modules.connectors.service import DataSourceService
from app.modules.connectors.sync_service import TableSyncService
from app.worker.arq_app import get_arq_pool

router = APIRouter(tags=["connectors"])


@router.post("/api/bases/{base_id}/import-csv", response_model=TableResponse, status_code=201)
async def import_csv(
    base_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile,
    table_name: str = Form(...),
) -> TableResponse:
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV file must be UTF-8 encoded") from exc

    service = ImportService(db)
    table = await service.import_csv(base_id=base_id, table_name=table_name, csv_text=csv_text, user_id=current_user.id)

    fields = await service.bases.fields.list_for_table(table.id)
    views = await service.bases.views.list_for_table(table.id)
    return table_to_response(table, fields, views)


@router.post("/api/bases/{base_id}/import-excel/inspect", response_model=ExcelInspectResponse)
async def inspect_excel(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession, file: UploadFile) -> ExcelInspectResponse:
    raw = await file.read()
    sheets = await ImportService(db).inspect_excel(base_id=base_id, file_bytes=raw, user_id=current_user.id)
    return ExcelInspectResponse(
        sheets=[
            ExcelSheetPreview(
                name=sheet["name"],
                row_count=sheet["row_count"],
                columns=[
                    ColumnDefResponse(
                        name=c.name, native_type=c.native_type, inferred_field_type=c.inferred_field_type, is_primary_key=c.is_primary_key
                    )
                    for c in sheet["columns"]
                ],
            )
            for sheet in sheets
        ]
    )


@router.post("/api/bases/{base_id}/import-excel", response_model=ExcelImportResponse, status_code=201)
async def import_excel(
    base_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile,
    # JSON-encoded list[{"sheet_name": str, "table_name": str}] -- a plain
    # Form field, not a second UploadFile/JSON body, since multipart/
    # form-data can't mix a file with a nested JSON body in one field the way
    # a normal JSON POST could.
    sheets: str = Form(...),
) -> ExcelImportResponse:
    raw = await file.read()
    try:
        sheet_specs = json.loads(sheets)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid sheets payload") from exc
    if not isinstance(sheet_specs, list) or not sheet_specs:
        raise ValidationError("Select at least one sheet to import")

    service = ImportService(db)
    results: list[ExcelImportResult] = []
    for spec in sheet_specs:
        sheet_name = spec["sheet_name"]
        table_name = spec["table_name"]
        try:
            table = await service.import_excel_sheet(
                base_id=base_id, table_name=table_name, file_bytes=raw, sheet_name=sheet_name, user_id=current_user.id
            )
            fields = await service.bases.fields.list_for_table(table.id)
            views = await service.bases.views.list_for_table(table.id)
            results.append(ExcelImportResult(sheet_name=sheet_name, table=table_to_response(table, fields, views)))
        except Exception as exc:
            # Each sheet is an independent unit of work -- one sheet's
            # failure (a stray formatting quirk, an empty sheet, a duplicate
            # name) shouldn't discard tables already created for the others
            # in the same request. Every outcome, success or failure, is
            # reported back per sheet rather than any of them vanishing
            # silently.
            results.append(ExcelImportResult(sheet_name=sheet_name, error=str(exc)))
    return ExcelImportResponse(results=results)


@router.post("/api/workspaces/{workspace_id}/data-sources", response_model=DataSourceResponse, status_code=201)
async def create_data_source(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    name: str = Form(...),
    source_type: str = Form(...),
    config: str = Form("{}"),
    file: UploadFile | None = None,
) -> DataSourceResponse:
    try:
        parsed_config = json.loads(config)
    except json.JSONDecodeError as exc:
        raise ValidationError("config must be valid JSON") from exc

    sqlite_bytes = await file.read() if file is not None else None
    data_source = await DataSourceService(db).create(
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=name,
        source_type=source_type,
        config=parsed_config,
        sqlite_file=sqlite_bytes,
    )
    return DataSourceResponse.model_validate(data_source)


@router.get("/api/workspaces/{workspace_id}/data-sources", response_model=list[DataSourceResponse])
async def list_data_sources(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[DataSourceResponse]:
    data_sources = await DataSourceService(db).list_for_workspace(workspace_id=workspace_id, user_id=current_user.id)
    return [DataSourceResponse.model_validate(d) for d in data_sources]


@router.delete("/api/data-sources/{data_source_id}", status_code=204)
async def delete_data_source(data_source_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await DataSourceService(db).delete(data_source_id=data_source_id, user_id=current_user.id)


@router.post("/api/data-sources/{data_source_id}/test", status_code=204)
async def test_data_source(data_source_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await DataSourceService(db).test_connection(data_source_id=data_source_id, user_id=current_user.id)


@router.get("/api/data-sources/{data_source_id}/tables", response_model=list[TableRefResponse])
async def list_data_source_tables(data_source_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[TableRefResponse]:
    tables = await DataSourceService(db).list_tables(data_source_id=data_source_id, user_id=current_user.id)
    return [TableRefResponse(name=t.name, schema_name=t.schema) for t in tables]


@router.get("/api/data-sources/{data_source_id}/tables/{table_name}/columns", response_model=list[ColumnDefResponse])
async def introspect_data_source_table(
    data_source_id: uuid.UUID,
    table_name: str,
    current_user: CurrentUser,
    db: DbSession,
    table_schema: str | None = None,
) -> list[ColumnDefResponse]:
    columns = await DataSourceService(db).introspect_columns(
        data_source_id=data_source_id, user_id=current_user.id, table_name=table_name, table_schema=table_schema
    )
    return [
        ColumnDefResponse(name=c.name, native_type=c.native_type, inferred_field_type=c.inferred_field_type, is_primary_key=c.is_primary_key)
        for c in columns
    ]


@router.post("/api/bases/{base_id}/import-from-source/{data_source_id}", response_model=TableResponse, status_code=201)
async def import_from_data_source(
    base_id: uuid.UUID,
    data_source_id: uuid.UUID,
    payload: ImportFromSourceRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> TableResponse:
    service = ImportService(db)
    table = await service.import_from_data_source(
        data_source_id=data_source_id,
        base_id=base_id,
        table_name=payload.table_name,
        new_table_name=payload.new_table_name,
        table_schema=payload.table_schema,
        user_id=current_user.id,
        sync_enabled=payload.sync_enabled,
    )
    fields = await service.bases.fields.list_for_table(table.id)
    views = await service.bases.views.list_for_table(table.id)
    return table_to_response(table, fields, views)


@router.get("/api/tables/{table_id}/sync", response_model=TableSyncConfigResponse | None)
async def get_table_sync(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TableSyncConfigResponse | None:
    config = await TableSyncService(db).get_config_for_table_checked(table_id=table_id, user_id=current_user.id)
    return TableSyncConfigResponse.model_validate(config) if config else None


@router.patch("/api/tables/{table_id}/sync", response_model=TableSyncConfigResponse)
async def update_table_sync(
    table_id: uuid.UUID, payload: UpdateTableSyncRequest, current_user: CurrentUser, db: DbSession
) -> TableSyncConfigResponse:
    config = await TableSyncService(db).set_enabled(
        table_id=table_id, user_id=current_user.id, enabled=payload.sync_enabled, requires_approval=payload.push_requires_approval
    )
    return TableSyncConfigResponse.model_validate(config)


@router.delete("/api/tables/{table_id}/sync", status_code=204)
async def unlink_table_sync(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await TableSyncService(db).unlink(table_id=table_id, user_id=current_user.id)


@router.patch("/api/tables/{table_id}/sync/pull", response_model=TableSyncConfigResponse)
async def configure_table_sync_pull(
    table_id: uuid.UUID, payload: ConfigurePullRequest, current_user: CurrentUser, db: DbSession
) -> TableSyncConfigResponse:
    sync_service = TableSyncService(db)
    config = await sync_service.get_config_for_table_checked(table_id=table_id, user_id=current_user.id)
    if config is None:
        raise ValidationError("This table isn't synced with a data source")

    if payload.poll_interval_seconds is not None and payload.poll_interval_seconds < 60:
        raise ValidationError("Poll interval must be at least 60 seconds")
    if payload.deletion_check_interval_seconds is not None and payload.deletion_check_interval_seconds < 300:
        raise ValidationError("Deletion check interval must be at least 300 seconds")

    server_time = None
    column_changing = payload.external_updated_at_column != config.external_updated_at_column
    if payload.external_updated_at_column is not None and column_changing:
        fields = await sync_service.bases.fields.list_for_table(table_id)
        if not any(f.name == payload.external_updated_at_column for f in fields):
            raise ValidationError(f"'{payload.external_updated_at_column}' isn't a field on this table")

        data_source, source_config = await DataSourceService(db).get_decrypted_config(
            data_source_id=config.data_source_id, user_id=current_user.id
        )
        connector = get_connector(data_source.source_type, source_config)
        try:
            columns = await connector.introspect_columns(TableRef(name=config.external_table_name, schema=config.external_schema))
            column = next((c for c in columns if c.name == payload.external_updated_at_column), None)
            if column is None:
                raise ValidationError(f"'{payload.external_updated_at_column}' no longer exists on the source table")
            # A coarse inferred_field_type == "date" also matches a plain
            # DATE column (daily granularity, useless for change detection --
            # see sql_common.py's _map_sa_type_to_field_type collapsing both
            # into one bucket). Reject it explicitly by checking the native
            # type text instead of trusting the coarse category.
            # Elasticsearch is exempt: its own native type string for a
            # "date" mapping is literally "date" (not a SQL dialect name),
            # and unlike a SQL DATE column it always stores full-instant
            # precision internally regardless of display format -- this
            # check would otherwise reject every ES timestamp field, making
            # pull configuration unusable for ES entirely.
            if data_source.source_type != "elasticsearch" and column.native_type.strip().upper() == "DATE":
                raise ValidationError(
                    f"'{payload.external_updated_at_column}' is a plain date column (no time component) -- "
                    "pick a timestamp/datetime column instead"
                )
            if column.inferred_field_type != "date":
                raise ValidationError(f"'{payload.external_updated_at_column}' isn't a date/timestamp column")
            server_time = await connector.get_server_time()
        finally:
            await connector.close()

    config = await sync_service.configure_pull(
        table_id=table_id,
        user_id=current_user.id,
        external_updated_at_column=payload.external_updated_at_column,
        poll_interval_seconds=payload.poll_interval_seconds,
        deletion_check_interval_seconds=payload.deletion_check_interval_seconds,
        server_time=server_time,
    )
    return TableSyncConfigResponse.model_validate(config)


@router.post("/api/tables/{table_id}/sync/pull/run-now", response_model=TableSyncConfigResponse)
async def run_table_sync_pull_now(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TableSyncConfigResponse:
    """"Sync now" -- enqueues a pull immediately instead of waiting for
    poll_interval_seconds. The enqueued jobs still go through the same
    per-table lock as the cron path (try_acquire in sync_tasks.py), so
    clicking this while a poll is already running is a harmless no-op, not a
    duplicate run."""
    config = await TableSyncService(db).prepare_manual_poll(table_id=table_id, user_id=current_user.id)
    pool = await get_arq_pool()
    await pool.enqueue_job("poll_table_sync", str(table_id))
    await pool.enqueue_job("check_table_sync_deletions", str(table_id))
    return TableSyncConfigResponse.model_validate(config)


def _pending_change_response(change, table_name: str, requester_name: str) -> PendingSyncChangeResponse:
    return PendingSyncChangeResponse(
        id=change.id, table_id=change.table_id, table_name=table_name, row_id=change.row_id, operation=change.operation,
        values=change.values, previous_values=change.previous_values, external_pk=change.external_pk, status=change.status,
        requested_by=change.requested_by, requested_by_name=requester_name, requested_at=change.requested_at,
        reviewed_by=change.reviewed_by, reviewed_at=change.reviewed_at, rejection_reason=change.rejection_reason,
    )


def _batch_response(batch, requester_name: str, changes: list[dict]) -> SyncChangeBatchResponse:
    return SyncChangeBatchResponse(
        id=batch.id, workspace_id=batch.workspace_id, status=batch.status, requested_by=batch.requested_by,
        requested_by_name=requester_name, submitted_at=batch.submitted_at, reviewed_by=batch.reviewed_by,
        reviewed_at=batch.reviewed_at, rejection_reason=batch.rejection_reason,
        changes=[_pending_change_response(c["change"], c["table_name"], requester_name) for c in changes],
    )


@router.get("/api/workspaces/{workspace_id}/pending-sync-change-drafts", response_model=list[PendingSyncChangeResponse])
async def list_pending_sync_change_drafts(
    workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> list[PendingSyncChangeResponse]:
    """An editor's own not-yet-submitted edits on gated tables -- what
    submitting would bundle up, before they've bundled it."""
    drafts = await PendingSyncChangeService(db).list_drafts(workspace_id=workspace_id, user_id=current_user.id)
    return [_pending_change_response(change, table_name, current_user.name) for change, table_name in drafts]


@router.post("/api/workspaces/{workspace_id}/pending-sync-changes/submit", response_model=SubmitDraftsResponse)
async def submit_pending_sync_changes(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> SubmitDraftsResponse:
    """Bundles every one of the caller's current drafts in this workspace
    into one new batch for an owner/admin to review in a single action."""
    batch, change_count = await PendingSyncChangeService(db).submit(workspace_id=workspace_id, user_id=current_user.id)
    return SubmitDraftsResponse(batch_id=batch.id, change_count=change_count)


@router.get("/api/workspaces/{workspace_id}/sync-change-batches", response_model=list[SyncChangeBatchResponse])
async def list_sync_change_batches(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[SyncChangeBatchResponse]:
    batches = await PendingSyncChangeService(db).list_batches_for_workspace(workspace_id=workspace_id, user_id=current_user.id)
    return [_batch_response(b["batch"], b["requester_name"], b["changes"]) for b in batches]


@router.post("/api/sync-change-batches/{batch_id}/approve", response_model=SyncChangeBatchResponse)
async def approve_sync_change_batch(batch_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> SyncChangeBatchResponse:
    service = PendingSyncChangeService(db)
    batch, requester_name = await service.approve_batch(batch_id=batch_id, user_id=current_user.id)
    rows = await service.repo.list_for_batch(batch.id)
    return _batch_response(batch, requester_name, [{"change": c, "table_name": t} for c, t in rows])


@router.post("/api/sync-change-batches/{batch_id}/reject", response_model=SyncChangeBatchResponse)
async def reject_sync_change_batch(
    batch_id: uuid.UUID, payload: RejectSyncChangeRequest, current_user: CurrentUser, db: DbSession
) -> SyncChangeBatchResponse:
    service = PendingSyncChangeService(db)
    batch, requester_name = await service.reject_batch(
        batch_id=batch_id, user_id=current_user.id, reason=payload.reason, restore=payload.restore
    )
    rows = await service.repo.list_for_batch(batch.id)
    return _batch_response(batch, requester_name, [{"change": c, "table_name": t} for c, t in rows])
