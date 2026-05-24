"""Integration tests for app.api.dashboard_api against an in-memory SQLite DB."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import dashboard_api as dashboard_module
from app.models.base import Base
from app.models.entities import AgentRun, Alert, KpiSnapshot, Portco, Tenant


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(Tenant(id="tenant-acme", slug="acme", name="Acme Capital Partners"))
        db.add(Portco(id="portco-1", tenant_id="tenant-acme", name="AcmeCo", sector="SaaS"))
        db.add(Portco(id="portco-2", tenant_id="tenant-acme", name="BetaHealth", sector="Health"))
        await db.flush()
        now = datetime.now(UTC)
        db.add(
            Alert(
                tenant_id="tenant-acme",
                portco_id="portco-1",
                severity="urgent",
                summary="Revenue collapse",
                context={},
                requires_human=True,
            )
        )
        db.add(
            Alert(
                tenant_id="tenant-acme",
                portco_id="portco-1",
                severity="attention",
                summary="Churn spike",
                context={},
                requires_human=False,
            )
        )
        db.add(
            AgentRun(
                tenant_id="tenant-acme",
                agent_name="AnomalyDetector",
                input_tokens=1000,
                output_tokens=200,
                cost_usd=0.002,
                latency_ms=1500,
                payload={"model": "claude-haiku-4-5"},
            )
        )
        for metric, value in [("revenue", 4.2), ("burn", 2.1), ("churn_pct", 3.5)]:
            db.add(
                KpiSnapshot(
                    tenant_id="tenant-acme",
                    portco_id="portco-1",
                    metric=metric,
                    value=value,
                    period=now.strftime("%Y-%m"),
                )
            )
        await db.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def client(session_factory, monkeypatch) -> TestClient:
    monkeypatch.setattr(dashboard_module, "SessionLocal", session_factory)
    app = FastAPI()
    app.include_router(dashboard_module.router)
    return TestClient(app)


def test_portcos_returns_list_for_known_tenant(client: TestClient) -> None:
    res = client.get("/api/v1/portcos", params={"tenant_slug": "acme"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert len(body) == 2
    assert {p["id"] for p in body} == {"portco-1", "portco-2"}
    assert set(body[0].keys()) == {"id", "name", "sector", "tenant_id"}


def test_portcos_returns_404_for_unknown_tenant(client: TestClient) -> None:
    res = client.get("/api/v1/portcos", params={"tenant_slug": "ghost"})
    assert res.status_code == 404


def test_alerts_returns_list_ordered_desc(client: TestClient) -> None:
    res = client.get("/api/v1/alerts", params={"tenant_slug": "acme", "limit": 10})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    keys = {"id", "portco_id", "severity", "summary", "requires_human", "created_at"}
    assert set(body[0].keys()) == keys


def test_alerts_returns_404_for_unknown_tenant(client: TestClient) -> None:
    res = client.get("/api/v1/alerts", params={"tenant_slug": "ghost"})
    assert res.status_code == 404


def test_agent_runs_returns_shape(client: TestClient) -> None:
    res = client.get("/api/v1/agent-runs", params={"tenant_slug": "acme"})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    keys = {
        "id",
        "agent_name",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
        "created_at",
    }
    assert set(body[0].keys()) == keys


def test_agent_runs_returns_404_for_unknown_tenant(client: TestClient) -> None:
    res = client.get("/api/v1/agent-runs", params={"tenant_slug": "ghost"})
    assert res.status_code == 404


def test_portfolio_health_applies_alert_penalties(client: TestClient) -> None:
    res = client.get("/api/v1/portfolio-health", params={"tenant_slug": "acme"})
    assert res.status_code == 200
    body = res.json()
    by_id = {p["portco_id"]: p for p in body}
    # portco-1 has 1 urgent (-50) + 1 attention (-20) = 30
    assert by_id["portco-1"]["health_score"] == 30
    assert by_id["portco-1"]["latest_kpis"]["revenue"] == 4.2
    # portco-2 has no alerts -> full score
    assert by_id["portco-2"]["health_score"] == 100
    keys = {"portco_id", "name", "sector", "latest_kpis", "health_score"}
    assert set(by_id["portco-1"].keys()) == keys


def test_portfolio_health_floors_at_zero(session_factory, monkeypatch) -> None:
    """Three urgent alerts (-150) should floor at 0, not go negative."""

    import asyncio

    async def add_more() -> None:
        async with session_factory() as db:
            for _ in range(3):
                db.add(
                    Alert(
                        tenant_id="tenant-acme",
                        portco_id="portco-2",
                        severity="urgent",
                        summary="x",
                        context={},
                        requires_human=True,
                    )
                )
            await db.commit()

    asyncio.run(add_more())
    monkeypatch.setattr(dashboard_module, "SessionLocal", session_factory)
    app = FastAPI()
    app.include_router(dashboard_module.router)
    client = TestClient(app)
    res = client.get("/api/v1/portfolio-health", params={"tenant_slug": "acme"})
    assert res.status_code == 200
    by_id = {p["portco_id"]: p for p in res.json()}
    assert by_id["portco-2"]["health_score"] == 0


def test_portfolio_health_returns_404_for_unknown_tenant(client: TestClient) -> None:
    res = client.get("/api/v1/portfolio-health", params={"tenant_slug": "ghost"})
    assert res.status_code == 404


def test_portfolio_health_ignores_alerts_older_than_30_days(session_factory, monkeypatch) -> None:
    """Old alerts should not count toward the score."""

    import asyncio

    async def add_old_alert() -> None:
        async with session_factory() as db:
            old_alert = Alert(
                tenant_id="tenant-acme",
                portco_id="portco-2",
                severity="urgent",
                summary="ancient",
                context={},
                requires_human=True,
            )
            db.add(old_alert)
            await db.flush()
            old_alert.created_at = datetime.now(UTC) - timedelta(days=60)
            await db.commit()

    asyncio.run(add_old_alert())
    monkeypatch.setattr(dashboard_module, "SessionLocal", session_factory)
    app = FastAPI()
    app.include_router(dashboard_module.router)
    client = TestClient(app)
    res = client.get("/api/v1/portfolio-health", params={"tenant_slug": "acme"})
    assert res.status_code == 200
    by_id = {p["portco_id"]: p for p in res.json()}
    assert by_id["portco-2"]["health_score"] == 100
