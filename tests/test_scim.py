"""Real SCIM 2.0 endpoint tests against an in-memory SQLite database.

The `scim_client` fixture (see `tests/conftest_scim.py`):
- builds an async SQLite engine and creates all tables,
- monkeypatches `SessionLocal` in `app.db` and `app.api.scim`,
- seeds tenant `tenant-test` (slug `test`),
- yields an `httpx.AsyncClient` over `ASGITransport(app=app)` with the
  expected bearer header.

Plus a handful of pure-function unit tests for the filter parser and
SCIM-payload extractor that don't need the DB.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import scim as scim_module
from app.config import settings


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(scim_module.router)
    return app


# ---------------------------------------------------------------------------
# Pure-function unit tests (no DB)
# ---------------------------------------------------------------------------


def test_scim_returns_503_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "scim_bearer_token", None)
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.get("/scim/v2/Users", headers={"Authorization": "Bearer anything"})
    assert res.status_code == 503


def test_parse_filter_returns_pair_for_eq() -> None:
    assert scim_module._parse_filter('userName eq "alice@acme.test"') == (
        "userName",
        "alice@acme.test",
    )


def test_parse_filter_returns_none_when_empty() -> None:
    assert scim_module._parse_filter(None) is None
    assert scim_module._parse_filter("") is None


def test_parse_filter_rejects_unsupported() -> None:
    with pytest.raises(HTTPException) as exc:
        scim_module._parse_filter('userName sw "foo"')
    assert exc.value.status_code == 400


def test_extract_user_fields_applies_defaults() -> None:
    out = scim_module._extract_user_fields(
        {
            "userName": "new@acme.test",
            "externalId": "okta-123",
        }
    )
    assert out == {
        "email": "new@acme.test",
        "scim_external_id": "okta-123",
        "role": scim_module.DEFAULT_ROLE,
        "sector": None,
        "tenant_id": scim_module.DEFAULT_TENANT_ID,
    }


def test_extract_user_fields_reads_extension() -> None:
    out = scim_module._extract_user_fields(
        {
            "userName": "ana@acme.test",
            scim_module.PORTFOLIO_USER_EXT: {
                "role": "analyst",
                "sector": "SaaS",
                "tenantId": "tenant-acme",
            },
        }
    )
    assert out["role"] == "analyst"
    assert out["sector"] == "SaaS"


def test_extract_user_fields_requires_username() -> None:
    with pytest.raises(HTTPException) as exc:
        scim_module._extract_user_fields({})
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Real-DB integration tests via httpx.AsyncClient + ASGITransport
# ---------------------------------------------------------------------------

SCIM_TENANT_ID = "tenant-test"
AUTH_HEADER = {"Authorization": "Bearer scim-dev-bearer-please-rotate-in-prod"}


@pytest.mark.asyncio
async def test_list_users_empty_returns_zero_resources(scim_client) -> None:
    res = await scim_client.get("/scim/v2/Users", headers=AUTH_HEADER)
    assert res.status_code == 200
    body = res.json()
    assert body["totalResults"] == 0
    assert body["Resources"] == []
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]


@pytest.mark.asyncio
async def test_create_user_returns_201_with_meta(scim_client) -> None:
    res = await scim_client.post(
        "/scim/v2/Users",
        headers=AUTH_HEADER,
        json={
            "userName": "alice@acme.test",
            "externalId": "okta-alice",
            scim_module.PORTFOLIO_USER_EXT: {
                "role": "analyst",
                "sector": "Fintech",
                "tenantId": SCIM_TENANT_ID,
            },
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["userName"] == "alice@acme.test"
    assert body["externalId"] == "okta-alice"
    assert body["id"].startswith("usr_")
    assert body["meta"]["resourceType"] == "User"
    assert body["meta"]["location"].endswith(f"/scim/v2/Users/{body['id']}")
    assert body[scim_module.PORTFOLIO_USER_EXT]["role"] == "analyst"


@pytest.mark.asyncio
async def test_get_user_by_id_returns_full_record(scim_client) -> None:
    created = (
        await scim_client.post(
            "/scim/v2/Users",
            headers=AUTH_HEADER,
            json={
                "userName": "bob@acme.test",
                scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
            },
        )
    ).json()
    res = await scim_client.get(f"/scim/v2/Users/{created['id']}", headers=AUTH_HEADER)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == created["id"]
    assert body["userName"] == "bob@acme.test"
    assert body["active"] is True


@pytest.mark.asyncio
async def test_get_user_unknown_returns_404(scim_client) -> None:
    res = await scim_client.get("/scim/v2/Users/usr_doesnotexist", headers=AUTH_HEADER)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_filter_userName_eq(scim_client) -> None:  # noqa: N802
    await scim_client.post(
        "/scim/v2/Users",
        headers=AUTH_HEADER,
        json={
            "userName": "carol@acme.test",
            scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
        },
    )
    await scim_client.post(
        "/scim/v2/Users",
        headers=AUTH_HEADER,
        json={
            "userName": "dave@acme.test",
            scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
        },
    )
    res = await scim_client.get(
        '/scim/v2/Users?filter=userName eq "carol@acme.test"',
        headers=AUTH_HEADER,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "carol@acme.test"


@pytest.mark.asyncio
async def test_put_user_replaces_fields(scim_client) -> None:
    created = (
        await scim_client.post(
            "/scim/v2/Users",
            headers=AUTH_HEADER,
            json={
                "userName": "erin@acme.test",
                scim_module.PORTFOLIO_USER_EXT: {
                    "role": "lp",
                    "sector": None,
                    "tenantId": SCIM_TENANT_ID,
                },
            },
        )
    ).json()
    res = await scim_client.put(
        f"/scim/v2/Users/{created['id']}",
        headers=AUTH_HEADER,
        json={
            "userName": "erin@acme.test",
            scim_module.PORTFOLIO_USER_EXT: {
                "role": "analyst",
                "sector": "Healthtech",
                "tenantId": SCIM_TENANT_ID,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body[scim_module.PORTFOLIO_USER_EXT]["role"] == "analyst"
    assert body[scim_module.PORTFOLIO_USER_EXT]["sector"] == "Healthtech"


@pytest.mark.asyncio
async def test_delete_user_returns_204_then_404_on_get(scim_client) -> None:
    created = (
        await scim_client.post(
            "/scim/v2/Users",
            headers=AUTH_HEADER,
            json={
                "userName": "frank@acme.test",
                scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
            },
        )
    ).json()
    res = await scim_client.delete(f"/scim/v2/Users/{created['id']}", headers=AUTH_HEADER)
    assert res.status_code == 204
    follow = await scim_client.get(f"/scim/v2/Users/{created['id']}", headers=AUTH_HEADER)
    assert follow.status_code == 404


@pytest.mark.asyncio
async def test_list_groups_returns_scim_listresponse(scim_client) -> None:
    res = await scim_client.get("/scim/v2/Groups", headers=AUTH_HEADER)
    assert res.status_code == 200
    body = res.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    assert body["totalResults"] == 0
    assert body["Resources"] == []


@pytest.mark.asyncio
async def test_create_group_with_members(scim_client) -> None:
    u1 = (
        await scim_client.post(
            "/scim/v2/Users",
            headers=AUTH_HEADER,
            json={
                "userName": "gina@acme.test",
                scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
            },
        )
    ).json()
    u2 = (
        await scim_client.post(
            "/scim/v2/Users",
            headers=AUTH_HEADER,
            json={
                "userName": "harry@acme.test",
                scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
            },
        )
    ).json()
    res = await scim_client.post(
        "/scim/v2/Groups",
        headers=AUTH_HEADER,
        json={
            "displayName": "Analysts",
            scim_module.PORTFOLIO_USER_EXT: {"tenantId": SCIM_TENANT_ID},
            "members": [{"value": u1["id"]}, {"value": u2["id"]}],
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["displayName"] == "Analysts"
    assert body["id"].startswith("grp_")
    member_ids = sorted(m["value"] for m in body["members"])
    assert member_ids == sorted([u1["id"], u2["id"]])


@pytest.mark.asyncio
async def test_missing_bearer_returns_401(scim_client) -> None:
    res = await scim_client.get("/scim/v2/Users")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_wrong_bearer_returns_401(scim_client) -> None:
    res = await scim_client.get(
        "/scim/v2/Users", headers={"Authorization": "Bearer not-the-real-token"}
    )
    assert res.status_code == 401
