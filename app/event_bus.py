"""In-memory SSE event bus, keyed by tenant_slug.

Session 2 will replace this with Postgres LISTEN/NOTIFY for multi-worker fan-out.
For now: one Queue per tenant; producers (webhook, orchestrator) put events,
the SSE stream endpoint consumes.
"""

import asyncio
from typing import Any

_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def get_queue(tenant_slug: str) -> asyncio.Queue[dict[str, Any]]:
    if tenant_slug not in _streams:
        _streams[tenant_slug] = asyncio.Queue()
    return _streams[tenant_slug]


async def emit(tenant_slug: str, event: dict[str, Any]) -> None:
    await get_queue(tenant_slug).put(event)
