"""DB queries used by the AnomalyDetector agent tools."""

from typing import Any

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entities import KpiSnapshot, Portco


async def fetch_history(portco_id: str, metric: str, limit: int = 12) -> list[dict[str, Any]]:
    """Most recent N KpiSnapshots for portco/metric, newest first."""
    async with SessionLocal() as session:
        stmt = (
            select(KpiSnapshot)
            .where(KpiSnapshot.portco_id == portco_id, KpiSnapshot.metric == metric)
            .order_by(KpiSnapshot.period.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {"period": r.period, "value": r.value, "created_at": r.created_at.isoformat()}
            for r in rows
        ]


async def compare_peers(portco_id: str, metric: str) -> dict[str, Any]:
    """Compare portco's latest value to sector-peers' average for the same metric+period."""
    async with SessionLocal() as session:
        portco = (
            await session.execute(select(Portco).where(Portco.id == portco_id))
        ).scalar_one_or_none()
        if portco is None:
            return {"error": f"portco {portco_id} not found"}

        latest_stmt = (
            select(KpiSnapshot)
            .where(KpiSnapshot.portco_id == portco_id, KpiSnapshot.metric == metric)
            .order_by(KpiSnapshot.period.desc())
            .limit(1)
        )
        latest = (await session.execute(latest_stmt)).scalar_one_or_none()
        if latest is None:
            return {"error": f"no snapshots for {portco_id}/{metric}"}

        peer_avg_stmt = (
            select(func.avg(KpiSnapshot.value))
            .join(Portco, Portco.id == KpiSnapshot.portco_id)
            .where(
                Portco.sector == portco.sector,
                Portco.id != portco_id,
                KpiSnapshot.metric == metric,
                KpiSnapshot.period == latest.period,
            )
        )
        peer_avg = (await session.execute(peer_avg_stmt)).scalar()

        return {
            "portco_id": portco_id,
            "sector": portco.sector,
            "metric": metric,
            "period": latest.period,
            "portco_value": latest.value,
            "peer_avg": float(peer_avg) if peer_avg is not None else None,
            "delta_pct": (
                round((latest.value - float(peer_avg)) / float(peer_avg) * 100, 2)
                if peer_avg
                else None
            ),
        }
