"""Admin endpoints protected by JWT + role-based access.

Scoping rules:
- GP: full visibility across tenant
- Analyst: restricted to portcos in their `sector`
- LP: only public-ish portfolio info (name)
"""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.db import SessionLocal
from app.models.entities import AgentRun, Alert, Portco
from app.services.rbac import requires_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/portcos")
@requires_role("gp", "analyst", "lp")
async def list_portcos(
    request: Request, user: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    assert user is not None
    tenant_id: str = user["tenant_id"]
    role: str = user["role"]
    sector: str | None = user.get("sector")

    async with SessionLocal() as db:
        stmt = select(Portco).where(Portco.tenant_id == tenant_id)
        if role == "analyst" and sector:
            stmt = stmt.where(Portco.sector == sector)
        rows = (await db.execute(stmt)).scalars().all()

    if role == "lp":
        return [{"id": p.id, "name": p.name} for p in rows]
    return [
        {"id": p.id, "name": p.name, "sector": p.sector, "tenant_id": p.tenant_id} for p in rows
    ]


@router.get("/agent-runs")
@requires_role("gp", "analyst")
async def list_agent_runs(
    request: Request, user: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    assert user is not None
    tenant_id: str = user["tenant_id"]

    async with SessionLocal() as db:
        rows = (
            (await db.execute(select(AgentRun).where(AgentRun.tenant_id == tenant_id)))
            .scalars()
            .all()
        )

    return [
        {
            "id": r.id,
            "agent_name": r.agent_name,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]


@router.get("/alerts")
@requires_role("gp", "analyst")
async def list_alerts(request: Request, user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    assert user is not None
    tenant_id: str = user["tenant_id"]
    role: str = user["role"]
    sector: str | None = user.get("sector")

    async with SessionLocal() as db:
        stmt = (
            select(Alert, Portco)
            .join(Portco, Alert.portco_id == Portco.id)
            .where(Alert.tenant_id == tenant_id)
        )
        if role == "analyst" and sector:
            stmt = stmt.where(Portco.sector == sector)
        rows = (await db.execute(stmt)).all()

    return [
        {
            "id": alert.id,
            "portco_id": alert.portco_id,
            "severity": alert.severity,
            "summary": alert.summary,
            "requires_human": alert.requires_human,
        }
        for alert, _portco in rows
    ]
