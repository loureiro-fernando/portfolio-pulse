"""Unit tests for app.api.auth - login endpoint with mocked DB lookup."""

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.config import settings
from app.models.entities import User
from app.services.rbac import JWT_ALG


def _make_user() -> User:
    return User(
        id="user-gp",
        tenant_id="tenant-acme",
        email="gp@acme.test",
        role="gp",
        sector=None,
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_module.router)
    return app


def test_login_returns_jwt_on_valid_credentials(monkeypatch) -> None:
    async def fake_get_user(email: str) -> User | None:
        return _make_user() if email == "gp@acme.test" else None

    monkeypatch.setattr(auth_module, "get_user_by_email", fake_get_user)
    client = TestClient(_build_app())
    res = client.post("/auth/login", json={"email": "gp@acme.test", "password": "anything"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    decoded = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=[JWT_ALG])
    assert decoded["email"] == "gp@acme.test"
    assert decoded["role"] == "gp"


def test_login_rejects_unknown_user(monkeypatch) -> None:
    async def fake_get_user(email: str) -> User | None:
        return None

    monkeypatch.setattr(auth_module, "get_user_by_email", fake_get_user)
    client = TestClient(_build_app())
    res = client.post("/auth/login", json={"email": "ghost@acme.test", "password": "x"})
    assert res.status_code == 401


def test_login_rejects_empty_password(monkeypatch) -> None:
    async def fake_get_user(email: str) -> User | None:
        return _make_user()

    monkeypatch.setattr(auth_module, "get_user_by_email", fake_get_user)
    client = TestClient(_build_app())
    res = client.post("/auth/login", json={"email": "gp@acme.test", "password": ""})
    assert res.status_code == 401
