"""Security coverage for the public-facing ingest and stream endpoints."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main as main_module
from app.models.base import Base
from app.models.entities import Tenant
from app.services.rbac import issue_token


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(Tenant(id="tenant-acme", slug="acme", name="Acme Capital Partners"))
        await db.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def client(session_factory, monkeypatch) -> TestClient:
    async def fake_run_pipeline(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)
    import app.agents.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "run_pipeline", fake_run_pipeline)
    return TestClient(main_module.app)


def _payload() -> dict[str, object]:
    return {"portco_id": "portco-1", "metric": "revenue", "value": 3.1, "period": "2026-04"}


def test_webhook_requires_auth(client: TestClient) -> None:
    res = client.post("/webhook/acme", json=_payload())
    assert res.status_code == 401


def test_webhook_accepts_ingest_token(client: TestClient) -> None:
    res = client.post(
        "/webhook/acme",
        json=_payload(),
        headers={"X-Webhook-Token": "dummy-webhook-token-for-tests"},
    )
    assert res.status_code == 202


def test_webhook_accepts_gp_jwt(client: TestClient) -> None:
    class UserStub:
        id = "user-gp"
        tenant_id = "tenant-acme"
        email = "gp@acme.test"
        role = "gp"
        sector = None

    res = client.post(
        "/webhook/acme",
        json=_payload(),
        headers={"Authorization": f"Bearer {issue_token(UserStub())}"},
    )
    assert res.status_code == 202


def test_stream_requires_auth(client: TestClient) -> None:
    res = client.get("/stream/acme")
    assert res.status_code == 401
