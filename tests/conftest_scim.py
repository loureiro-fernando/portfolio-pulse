"""SCIM-specific fixture: in-memory SQLite engine + ASGI httpx client.

Steps performed per test:
1. Build a fresh `sqlite+aiosqlite:///:memory:` engine (StaticPool keeps the
   single in-memory DB shared across connections within the test).
2. Run `Base.metadata.create_all` on it.
3. Monkeypatch `SessionLocal` in `app.db` *and* `app.api.scim` (the router
   imported the symbol at module load time, so re-binding only `app.db`
   isn't enough).
4. Seed one tenant (`tenant-test`, slug `test`) so user/group rows that
   reference it pass the FK constraint - SQLite has FK enforcement off by
   default for this engine, but the seed keeps the data realistic.
5. Yield an `httpx.AsyncClient` bound to the FastAPI app via `ASGITransport`.
6. Teardown: drop all tables and dispose the engine.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import db as app_db
from app.api import scim as scim_module
from app.main import app
from app.models.base import Base
from app.models.entities import Tenant


@pytest_asyncio.fixture
async def scim_client() -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session() as session:
        session.add(Tenant(id="tenant-test", slug="test", name="Test Tenant"))
        # The DEFAULT_TENANT_ID in scim is "tenant-acme" - seed it too so
        # users created without explicit tenantId don't crash FK in stricter
        # backends.
        session.add(Tenant(id="tenant-acme", slug="acme", name="Acme Tenant"))
        await session.commit()

    original_app_db = app_db.SessionLocal
    original_scim = scim_module.SessionLocal
    app_db.SessionLocal = test_session  # type: ignore[assignment]
    scim_module.SessionLocal = test_session  # type: ignore[assignment]

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app_db.SessionLocal = original_app_db  # type: ignore[assignment]
        scim_module.SessionLocal = original_scim  # type: ignore[assignment]
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
