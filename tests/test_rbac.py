"""Unit tests for app.services.rbac.

Covers: token round-trip, missing/invalid/expired tokens, role gating.
No DB required - User is a plain SQLAlchemy declarative instance built in-memory.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import settings
from app.models.entities import User
from app.services.rbac import JWT_ALG, current_user, decode_token, issue_token, requires_role


def _make_user(role: str = "gp", sector: str | None = None) -> User:
    return User(
        id="user-test",
        tenant_id="tenant-acme",
        email="user@acme.test",
        role=role,
        sector=sector,
    )


def test_issue_and_decode_token_round_trip() -> None:
    user = _make_user(role="gp")
    token = issue_token(user)
    decoded = decode_token(token)
    assert decoded["sub"] == "user-test"
    assert decoded["email"] == "user@acme.test"
    assert decoded["role"] == "gp"
    assert decoded["tenant_id"] == "tenant-acme"


def test_decode_token_rejects_invalid_signature() -> None:
    user = _make_user()
    token = issue_token(user)
    tampered = token[:-4] + "AAAA"
    with pytest.raises(Exception) as exc:
        decode_token(tampered)
    assert "401" in str(exc.value) or "invalid" in str(exc.value).lower()


def test_decode_token_rejects_expired() -> None:
    payload = {
        "sub": "user-test",
        "email": "user@acme.test",
        "role": "gp",
        "tenant_id": "tenant-acme",
        "sector": None,
        "exp": datetime.now(UTC) - timedelta(seconds=10),
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)
    with pytest.raises(Exception) as exc:
        decode_token(expired)
    assert "401" in str(exc.value) or "expired" in str(exc.value).lower()


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    @requires_role("gp")
    async def protected(request: Request, user: dict[str, Any] | None = None) -> dict[str, Any]:
        assert user is not None
        return {"ok": True, "role": user["role"]}

    return app


def _build_cookie_app() -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    async def me(request: Request) -> dict[str, Any]:
        user = await current_user(request)
        return {"email": user["email"]}

    return app


def test_requires_role_allows_matching_role() -> None:
    client = TestClient(_build_app())
    token = issue_token(_make_user(role="gp"))
    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"ok": True, "role": "gp"}


def test_requires_role_rejects_wrong_role() -> None:
    client = TestClient(_build_app())
    token = issue_token(_make_user(role="lp"))
    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_requires_role_rejects_missing_token() -> None:
    client = TestClient(_build_app())
    res = client.get("/protected")
    assert res.status_code == 401


def test_current_user_accepts_jwt_cookie() -> None:
    client = TestClient(_build_cookie_app())
    token = issue_token(_make_user(role="gp"))
    client.cookies.set("portfolio_pulse_token", token)
    res = client.get("/me")
    assert res.status_code == 200
    assert res.json() == {"email": "user@acme.test"}
