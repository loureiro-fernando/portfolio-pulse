import asyncio
import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.dashboard_api import router as dashboard_api_router
from app.api.scim import router as scim_router
from app.config import settings  # noqa: F401  (forces .env validation at startup)
from app.db import SessionLocal
from app.event_bus import emit, get_queue
from app.models.entities import KpiSnapshot, Tenant
from app.services.rbac import JWT_COOKIE_NAME, current_user, decode_token
from app.telemetry import init_tracing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_tracing()
    yield


app = FastAPI(title="Portfolio-Pulse", version=settings.app_version, lifespan=lifespan)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(scim_router)
app.include_router(dashboard_api_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_STATIC_DIR), html=True), name="dashboard")


class KpiPayload(BaseModel):
    portco_id: str
    metric: str
    value: float
    period: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


def _auth_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return None


def _has_ingest_token(request: Request) -> bool:
    expected = settings.webhook_bearer_token
    if not expected:
        return False
    presented = request.headers.get("x-webhook-token") or _auth_bearer(request)
    return bool(presented and secrets.compare_digest(presented, expected))


def _authorize_webhook(request: Request, tenant_id: str) -> None:
    if _has_ingest_token(request):
        return
    token = _auth_bearer(request) or request.cookies.get(JWT_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="missing webhook token")
    user = decode_token(token)
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="tenant access denied")
    if user.get("role") not in {"gp", "analyst"}:
        raise HTTPException(status_code=403, detail="role cannot ingest KPI events")


@app.post("/webhook/{tenant_slug}", status_code=202)
async def webhook(
    tenant_slug: str,
    payload: KpiPayload,
    background_tasks: BackgroundTasks,
    response: Response,
    request: Request,
) -> dict[str, object]:
    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"unknown tenant: {tenant_slug}")
        tenant_id = tenant.id
        _authorize_webhook(request, tenant_id)

        db.add(
            KpiSnapshot(
                tenant_id=tenant.id,
                portco_id=payload.portco_id,
                metric=payload.metric,
                value=payload.value,
                period=payload.period,
            )
        )
        await db.commit()

    await emit(tenant_slug, {"type": "kpi_received", "payload": payload.model_dump()})

    # Defer pipeline execution until after the response is sent
    from app.agents.orchestrator import run_pipeline

    background_tasks.add_task(
        run_pipeline,
        tenant_slug,
        tenant_id,
        payload.portco_id,
        payload.metric,
        payload.value,
        payload.period,
    )

    response.status_code = 202
    return {
        "accepted": True,
        "tenant": tenant_slug,
        "portco": payload.portco_id,
        "pipeline": "scheduled",
    }


@app.get("/stream/{tenant_slug}")
async def stream(tenant_slug: str, request: Request) -> StreamingResponse:
    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"unknown tenant: {tenant_slug}")
    user = await current_user(request)
    if user.get("tenant_id") != tenant.id:
        raise HTTPException(status_code=403, detail="tenant access denied")

    queue = get_queue(tenant_slug)

    async def event_generator() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'connected', 'tenant': tenant_slug})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
