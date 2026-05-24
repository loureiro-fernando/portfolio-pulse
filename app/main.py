import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings  # noqa: F401  (forces .env validation at startup)

app = FastAPI(title="Portfolio-Pulse", version="0.1.0")

# Session 2 will move this to Postgres LISTEN/NOTIFY for multi-worker fan-out.
_event_streams: dict[str, asyncio.Queue] = {}


class KpiPayload(BaseModel):
    portco_id: str
    metric: str
    value: float
    period: str


def _get_queue(tenant_slug: str) -> asyncio.Queue:
    if tenant_slug not in _event_streams:
        _event_streams[tenant_slug] = asyncio.Queue()
    return _event_streams[tenant_slug]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/webhook/{tenant_slug}")
async def webhook(tenant_slug: str, payload: KpiPayload) -> dict[str, object]:
    if not tenant_slug:
        raise HTTPException(status_code=400, detail="tenant_slug required")
    queue = _get_queue(tenant_slug)
    await queue.put({"type": "kpi_received", "payload": payload.model_dump()})
    return {"accepted": True, "tenant": tenant_slug, "portco": payload.portco_id}


@app.get("/stream/{tenant_slug}")
async def stream(tenant_slug: str) -> StreamingResponse:
    queue = _get_queue(tenant_slug)

    async def event_generator() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'connected', 'tenant': tenant_slug})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
