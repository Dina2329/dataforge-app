import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import DataForgeError
from app.modules.attachments.api import router as attachments_router
from app.modules.audit.api import router as audit_router
from app.modules.auth.api import router as auth_router
from app.modules.automations.api import router as automations_router
from app.modules.backup.api import router as backup_router
from app.modules.bases.api import router as bases_router
from app.modules.batch_submit.api import router as batch_submit_router
from app.modules.bulk_ops.api import router as bulk_ops_router
from app.modules.connectors.api import router as connectors_router
from app.modules.dashboards.api import router as dashboards_router
from app.modules.dashboards.public_api import router as public_dashboards_router
from app.modules.missing_terms.api import router as missing_terms_router
from app.modules.notifications.api import router as notifications_router
from app.modules.record_submit.api import router as record_submit_router
from app.modules.records.api import router as records_router
from app.modules.records.public_api import router as public_forms_router
from app.modules.records.ws_api import router as records_ws_router
from app.modules.row_policies.api import router as row_policies_router
from app.modules.snapshots.api import router as snapshots_router
from app.modules.workspaces.api import router as workspaces_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DataForge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # VS Code Remote-SSH port forwarding can present the dev frontend on a
    # different local port than 5173 if that port is already taken on the
    # user's machine (e.g. http://localhost:15173) -- the exact-match
    # allow_origins list above would then reject every write request's CORS
    # preflight (reads still "work" since a simple GET's preflight is more
    # lenient), which looks exactly like "nothing happens on Create" with no
    # visible error. This regex accepts any localhost/127.0.0.1 port in
    # addition to the explicit list, which only matters for local dev anyway.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DataForgeError)
async def dataforge_error_handler(request: Request, exc: DataForgeError) -> JSONResponse:
    # CircuitOpenError/RateLimitedError both carry retry_after_seconds -- set
    # the standard header for well-behaved clients, not just embed it in the message.
    retry_after = getattr(exc, "retry_after_seconds", None)
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(bases_router)
app.include_router(records_router)
app.include_router(records_ws_router)
app.include_router(attachments_router)
app.include_router(connectors_router)
app.include_router(bulk_ops_router)
app.include_router(dashboards_router)
app.include_router(public_dashboards_router)
app.include_router(automations_router)
app.include_router(audit_router)
app.include_router(row_policies_router)
app.include_router(notifications_router)
app.include_router(public_forms_router)
app.include_router(backup_router)
app.include_router(snapshots_router)
app.include_router(record_submit_router)
app.include_router(missing_terms_router)
app.include_router(batch_submit_router)
