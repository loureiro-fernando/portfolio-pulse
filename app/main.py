import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
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
from app.telemetry import init_tracing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_tracing()
    yield


app = FastAPI(title="Portfolio-Pulse", version="0.3.0", lifespan=lifespan)

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
    return {"status": "ok", "version": "0.3.0"}


@app.post("/webhook/{tenant_slug}", status_code=202)
async def webhook(
    tenant_slug: str,
    payload: KpiPayload,
    background_tasks: BackgroundTasks,
    response: Response,
) -> dict[str, object]:
    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"unknown tenant: {tenant_slug}")

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
        tenant_id = tenant.id

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
async def stream(tenant_slug: str) -> StreamingResponse:
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
