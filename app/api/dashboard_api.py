"""Read-only REST API consumed by the dashboard for the initial page fetch.

Complements the SSE `/stream/{tenant_slug}` endpoint, which only carries live
updates - on a fresh page load the dashboard needs the prior state (portcos,
recent alerts, agent-runs for the cost burndown, computed portfolio-health
scores). These endpoints fill that gap.

Auth: JWT bearer. Responses are scoped to the tenant carried in the JWT.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.db import SessionLocal
from app.models.entities import AgentRun, Alert, KpiSnapshot, Portco, Tenant
from app.services.rbac import current_user

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


async def _resolve_tenant_id(tenant_slug: str) -> str:
    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"unknown tenant: {tenant_slug}")
    return tenant.id


async def _authorize_tenant(request: Request, tenant_slug: str) -> str:
    tenant_id = await _resolve_tenant_id(tenant_slug)
    user = await current_user(request)
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="tenant access denied")
    return tenant_id


@router.get("/portcos")
async def list_portcos(request: Request, tenant_slug: str = Query(...)) -> list[dict[str, Any]]:
    tenant_id = await _authorize_tenant(request, tenant_slug)
    async with SessionLocal() as db:
        rows = (
            (await db.execute(select(Portco).where(Portco.tenant_id == tenant_id))).scalars().all()
        )
    return [
        {"id": p.id, "name": p.name, "sector": p.sector, "tenant_id": p.tenant_id} for p in rows
    ]


@router.get("/alerts")
async def list_alerts(
    request: Request,
    tenant_slug: str = Query(...),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict[str, Any]]:
    tenant_id = await _authorize_tenant(request, tenant_slug)
    async with SessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(Alert)
                    .where(Alert.tenant_id == tenant_id)
                    .order_by(Alert.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "id": a.id,
            "portco_id": a.portco_id,
            "severity": a.severity,
            "summary": a.summary,
            "requires_human": a.requires_human,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.get("/agent-runs")
async def list_agent_runs(
    request: Request,
    tenant_slug: str = Query(...),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    tenant_id = await _authorize_tenant(request, tenant_slug)
    async with SessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(AgentRun)
                    .where(AgentRun.tenant_id == tenant_id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(limit)
                )
            )
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
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/portfolio-health")
async def portfolio_health(request: Request, tenant_slug: str = Query(...)) -> list[dict[str, Any]]:
    tenant_id = await _authorize_tenant(request, tenant_slug)
    cutoff = datetime.now(UTC) - timedelta(days=30)

    async with SessionLocal() as db:
        portcos = (
            (await db.execute(select(Portco).where(Portco.tenant_id == tenant_id))).scalars().all()
        )

        recent_alerts = (
            (
                await db.execute(
                    select(Alert)
                    .where(Alert.tenant_id == tenant_id)
                    .where(Alert.created_at >= cutoff)
                )
            )
            .scalars()
            .all()
        )

        kpis = (
            (
                await db.execute(
                    select(KpiSnapshot)
                    .where(KpiSnapshot.tenant_id == tenant_id)
                    .order_by(KpiSnapshot.period.desc())
                )
            )
            .scalars()
            .all()
        )

    alerts_by_portco: dict[str, list[Alert]] = {}
    for alert in recent_alerts:
        alerts_by_portco.setdefault(alert.portco_id, []).append(alert)

    latest_kpis: dict[str, dict[str, float]] = {}
    for kpi in kpis:
        portco_kpis = latest_kpis.setdefault(kpi.portco_id, {})
        if kpi.metric not in portco_kpis:
            portco_kpis[kpi.metric] = kpi.value

    result: list[dict[str, Any]] = []
    for portco in portcos:
        portco_alerts = alerts_by_portco.get(portco.id, [])
        attention = sum(1 for a in portco_alerts if a.severity == "attention")
        urgent = sum(1 for a in portco_alerts if a.severity == "urgent")
        score = max(0, 100 - 20 * attention - 50 * urgent)
        portco_kpis = latest_kpis.get(portco.id, {})
        result.append(
            {
                "portco_id": portco.id,
                "name": portco.name,
                "sector": portco.sector,
                "latest_kpis": {
                    "revenue": portco_kpis.get("revenue"),
                    "burn": portco_kpis.get("burn"),
                    "churn_pct": portco_kpis.get("churn_pct"),
                },
                "health_score": score,
            }
        )
    return result
