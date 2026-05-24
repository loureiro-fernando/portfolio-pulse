"""Seed dev data: 1 tenant, 3 portcos, 12 months of KPIs per portco/metric.

Idempotent: deletes existing rows before inserting.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete

from app.db import SessionLocal
from app.models.entities import KpiSnapshot, Portco, Tenant

TENANTS: list[dict[str, Any]] = [
    {"id": "tenant-acme", "slug": "acme", "name": "Acme Capital Partners"},
]

PORTCOS: list[dict[str, Any]] = [
    {"id": "portco-1", "tenant_id": "tenant-acme", "name": "AcmeCo", "sector": "SaaS"},
    {"id": "portco-2", "tenant_id": "tenant-acme", "name": "BetaHealth", "sector": "Healthtech"},
    {"id": "portco-3", "tenant_id": "tenant-acme", "name": "GammaFin", "sector": "Fintech"},
]

PERIODS: list[str] = [
    "2026-04",
    "2026-03",
    "2026-02",
    "2026-01",
    "2025-12",
    "2025-11",
    "2025-10",
    "2025-09",
    "2025-08",
    "2025-07",
    "2025-06",
    "2025-05",
]

TRAJECTORIES: dict[str, dict[str, list[float]]] = {
    "portco-1": {
        "revenue": [3.2, 3.4, 3.6, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 3.1],
        "burn": [1.8, 1.8, 1.9, 1.9, 2.0, 2.0, 2.0, 2.1, 2.1, 2.1, 2.2, 2.4],
        "churn_pct": [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.4, 2.5, 2.6, 2.7, 2.8, 4.5],
    },
    "portco-2": {
        "revenue": [1.5, 1.6, 1.7, 1.9, 2.1, 2.3, 2.5, 2.7, 2.9, 3.1, 3.3, 3.5],
        "burn": [0.9, 0.95, 1.0, 1.0, 1.0, 1.0, 1.05, 1.1, 1.1, 1.1, 1.15, 1.2],
        "churn_pct": [3.0, 2.9, 2.8, 2.7, 2.6, 2.5, 2.5, 2.4, 2.3, 2.2, 2.1, 2.0],
    },
    "portco-3": {
        "revenue": [5.0, 5.4, 5.8, 6.2, 6.7, 7.2, 7.8, 8.4, 9.0, 9.7, 10.5, 11.4],
        "burn": [3.5, 3.6, 3.8, 4.0, 4.2, 4.5, 4.7, 5.0, 5.3, 5.6, 6.0, 6.4],
        "churn_pct": [1.5, 1.4, 1.4, 1.3, 1.3, 1.2, 1.2, 1.1, 1.1, 1.0, 1.0, 0.9],
    },
}


async def main() -> None:
    async with SessionLocal() as session:
        await session.execute(delete(KpiSnapshot))
        await session.execute(delete(Portco))
        await session.execute(delete(Tenant))
        await session.flush()

        session.add_all([Tenant(**t) for t in TENANTS])
        session.add_all([Portco(**p) for p in PORTCOS])
        await session.flush()

        for portco_id, metrics in TRAJECTORIES.items():
            tenant_id = next(p["tenant_id"] for p in PORTCOS if p["id"] == portco_id)
            for metric, values in metrics.items():
                for period, value in zip(reversed(PERIODS), values, strict=True):
                    session.add(
                        KpiSnapshot(
                            tenant_id=tenant_id,
                            portco_id=portco_id,
                            metric=metric,
                            value=value,
                            period=period,
                        )
                    )

        await session.commit()
        total_kpis = sum(len(v) for traj in TRAJECTORIES.values() for v in traj.values())
        print(
            f"Seeded {len(TENANTS)} tenants, {len(PORTCOS)} portcos, "
            f"{total_kpis} KPIs at {datetime.now(UTC).isoformat()}"
        )


if __name__ == "__main__":
    asyncio.run(main())
