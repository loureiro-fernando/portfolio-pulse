"""Unit tests for app.api.scim auth + filter parsing.

Full CRUD tests would need a real DB; here we cover the parts that don't:
- bearer auth gating (missing / wrong token / no token configured)
- filter parser (valid eq, unsupported syntax)
- SCIM payload extractor (defaults, missing userName)
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


def test_scim_rejects_missing_bearer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "scim_bearer_token", "expected-token")
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.get("/scim/v2/Users")
    assert res.status_code == 401


def test_scim_rejects_wrong_bearer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "scim_bearer_token", "expected-token")
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.get("/scim/v2/Users", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


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
