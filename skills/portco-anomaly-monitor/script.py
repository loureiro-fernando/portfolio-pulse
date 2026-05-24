"""Invoke the portco-anomaly-monitor skill programmatically.

Wraps app.agents.orchestrator.run_pipeline with input validation and a
machine-readable return value (alert_id, severity, requires_human, summary).
"""

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import select

from app.agents.orchestrator import run_pipeline
from app.db import SessionLocal
from app.models.entities import Alert, Tenant


async def invoke(
    tenant_slug: str,
    portco_id: str,
    metric: str,
    value: float,
    period: str,
) -> dict[str, Any]:
    if metric not in {"revenue", "burn", "churn_pct"}:
        raise ValueError(f"metric must be revenue|burn|churn_pct, got {metric!r}")

    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"unknown tenant_slug: {tenant_slug}")
        tenant_id = tenant.id

    await run_pipeline(tenant_slug, tenant_id, portco_id, metric, value, period)

    async with SessionLocal() as db:
        latest_alert = (
            await db.execute(
                select(Alert)
                .where(Alert.tenant_id == tenant_id, Alert.portco_id == portco_id)
                .order_by(Alert.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if latest_alert is None:
        return {
            "alert_id": None,
            "severity": "none",
            "requires_human": False,
            "summary": "no anomaly detected",
        }

    return {
        "alert_id": latest_alert.id,
        "severity": latest_alert.severity,
        "requires_human": latest_alert.requires_human,
        "summary": latest_alert.summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke portco-anomaly-monitor skill")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--portco", required=True)
    parser.add_argument("--metric", required=True)
    parser.add_argument("--value", type=float, required=True)
    parser.add_argument("--period", required=True)
    args = parser.parse_args()

    result = asyncio.run(invoke(args.tenant, args.portco, args.metric, args.value, args.period))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
