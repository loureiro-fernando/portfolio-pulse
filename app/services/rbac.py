"""JWT-based RBAC. issue_token(user) for login; @requires_role(*roles) for endpoints."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.entities import Role, User

JWT_ALG = "HS256"
JWT_TTL_HOURS = 8


def issue_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "sector": user.sector,
        "exp": datetime.now(UTC) + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc


async def current_user(request: Request) -> dict[str, Any]:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return decode_token(auth.split(" ", 1)[1])


def requires_role(*allowed: Role | str) -> Callable:
    allowed_str = {r.value if isinstance(r, Role) else r for r in allowed}

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if request is None:
                raise HTTPException(status_code=500, detail="Request not in handler signature")
            user = await current_user(request)
            if user.get("role") not in allowed_str:
                raise HTTPException(
                    status_code=403,
                    detail=f"role {user.get('role')} not in {sorted(allowed_str)}",
                )
            kwargs["user"] = user
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def get_user_by_email(email: str) -> User | None:
    async with SessionLocal() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
