"""SCIM 2.0 endpoints (RFC 7644 minimal subset).

Auth: Bearer token from settings.scim_bearer_token. Reject 401 otherwise.
Filter support: only `userName eq "value"` for the MVP.
Identity-provider extensions: role and sector via `urn:portfolio-pulse:User`.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal
from app.models.entities import Group, User, UserGroupMembership
from app.services.scim_schemas import (
    ERROR_SCHEMA,
    GROUP_SCHEMA,
    LIST_SCHEMA,
    PORTFOLIO_USER_EXT,
    USER_SCHEMA,
)

router = APIRouter(prefix="/scim/v2", tags=["scim"])

DEFAULT_TENANT_ID = "tenant-acme"
DEFAULT_ROLE = "lp"


def _check_auth(request: Request) -> None:
    expected = settings.scim_bearer_token
    if not expected:
        raise HTTPException(status_code=503, detail=_err("503", "SCIM not configured"))
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=_err("401", "missing bearer token"))
    if auth.split(" ", 1)[1] != expected:
        raise HTTPException(status_code=401, detail=_err("401", "invalid bearer token"))


def _err(stat: str, detail: str) -> dict[str, Any]:
    return {"schemas": [ERROR_SCHEMA], "status": stat, "detail": detail}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _user_to_scim(user: User, base_url: str) -> dict[str, Any]:
    return {
        "schemas": [USER_SCHEMA, PORTFOLIO_USER_EXT],
        "id": user.id,
        "externalId": user.scim_external_id,
        "userName": user.email,
        "emails": [{"value": user.email, "primary": True}],
        "active": True,
        PORTFOLIO_USER_EXT: {
            "role": user.role,
            "sector": user.sector,
            "tenantId": user.tenant_id,
        },
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
            "lastModified": user.updated_at.isoformat() if user.updated_at else None,
            "location": f"{base_url}/scim/v2/Users/{user.id}",
        },
    }


def _group_to_scim(group: Group, members: list[User], base_url: str) -> dict[str, Any]:
    return {
        "schemas": [GROUP_SCHEMA],
        "id": group.id,
        "externalId": group.scim_external_id,
        "displayName": group.display_name,
        "members": [{"value": m.id, "display": m.email} for m in members],
        "meta": {
            "resourceType": "Group",
            "created": group.created_at.isoformat() if group.created_at else None,
            "lastModified": group.updated_at.isoformat() if group.updated_at else None,
            "location": f"{base_url}/scim/v2/Groups/{group.id}",
        },
    }


def _parse_filter(filter_str: str | None) -> tuple[str, str] | None:
    """Parse `userName eq "value"` style filters. Returns (attr, value) or None."""
    if not filter_str:
        return None
    match = re.match(r'^\s*(\w+)\s+eq\s+"([^"]+)"\s*$', filter_str)
    if not match:
        raise HTTPException(
            status_code=400, detail=_err("400", f"unsupported filter: {filter_str}")
        )
    return match.group(1), match.group(2)


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _extract_user_fields(body: dict[str, Any]) -> dict[str, Any]:
    ext = body.get(PORTFOLIO_USER_EXT) or {}
    user_name = body.get("userName")
    if not user_name:
        raise HTTPException(status_code=400, detail=_err("400", "userName is required"))
    return {
        "email": user_name,
        "scim_external_id": body.get("externalId"),
        "role": ext.get("role", DEFAULT_ROLE),
        "sector": ext.get("sector"),
        "tenant_id": ext.get("tenantId", DEFAULT_TENANT_ID),
    }


@router.get("/Users")
async def list_users(
    request: Request,
    filter: str | None = Query(default=None),
    count: int = Query(default=100, ge=0, le=1000),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
) -> dict[str, Any]:
    _check_auth(request)
    parsed = _parse_filter(filter)
    async with SessionLocal() as db:
        stmt = select(User)
        if parsed:
            attr, value = parsed
            if attr == "userName":
                stmt = stmt.where(User.email == value)
            elif attr == "externalId":
                stmt = stmt.where(User.scim_external_id == value)
            else:
                raise HTTPException(
                    status_code=400, detail=_err("400", f"unsupported filter attr: {attr}")
                )
        rows = (await db.execute(stmt)).scalars().all()

    sliced = rows[start_index - 1 : start_index - 1 + count]
    base = _base_url(request)
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": len(rows),
        "startIndex": start_index,
        "itemsPerPage": len(sliced),
        "Resources": [_user_to_scim(u, base) for u in sliced],
    }


@router.get("/Users/{user_id}")
async def get_user(user_id: str, request: Request) -> dict[str, Any]:
    _check_auth(request)
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=_err("404", f"user {user_id} not found"))
    return _user_to_scim(user, _base_url(request))


@router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_user(request: Request) -> dict[str, Any]:
    _check_auth(request)
    body = await request.json()
    fields = _extract_user_fields(body)
    new_id = f"usr_{uuid.uuid4().hex[:12]}"
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == fields["email"]))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=_err("409", f"userName already exists: {fields['email']}")
            )
        user = User(id=new_id, **fields)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return _user_to_scim(user, _base_url(request))


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request) -> dict[str, Any]:
    _check_auth(request)
    body = await request.json()
    fields = _extract_user_fields(body)
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail=_err("404", f"user {user_id} not found"))
        for key, value in fields.items():
            setattr(user, key, value)
        await db.commit()
        await db.refresh(user)
    return _user_to_scim(user, _base_url(request))


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, request: Request) -> Response:
    _check_auth(request)
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail=_err("404", f"user {user_id} not found"))
        await db.execute(delete(UserGroupMembership).where(UserGroupMembership.user_id == user_id))
        await db.delete(user)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _load_group_members(db: Any, group_id: str) -> list[User]:
    member_ids = (
        (
            await db.execute(
                select(UserGroupMembership.user_id).where(UserGroupMembership.group_id == group_id)
            )
        )
        .scalars()
        .all()
    )
    if not member_ids:
        return []
    return list((await db.execute(select(User).where(User.id.in_(member_ids)))).scalars().all())


@router.get("/Groups")
async def list_groups(
    request: Request,
    count: int = Query(default=100, ge=0, le=1000),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
) -> dict[str, Any]:
    _check_auth(request)
    async with SessionLocal() as db:
        rows = (await db.execute(select(Group))).scalars().all()
        sliced = rows[start_index - 1 : start_index - 1 + count]
        base = _base_url(request)
        resources = [_group_to_scim(g, await _load_group_members(db, g.id), base) for g in sliced]
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": len(rows),
        "startIndex": start_index,
        "itemsPerPage": len(sliced),
        "Resources": resources,
    }


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
async def create_group(request: Request) -> dict[str, Any]:
    _check_auth(request)
    body = await request.json()
    display_name = body.get("displayName")
    if not display_name:
        raise HTTPException(status_code=400, detail=_err("400", "displayName is required"))
    new_id = f"grp_{uuid.uuid4().hex[:12]}"
    tenant_id = (body.get(PORTFOLIO_USER_EXT) or {}).get("tenantId", DEFAULT_TENANT_ID)
    async with SessionLocal() as db:
        group = Group(
            id=new_id,
            tenant_id=tenant_id,
            display_name=display_name,
            scim_external_id=body.get("externalId"),
        )
        db.add(group)
        for member in body.get("members", []):
            db.add(UserGroupMembership(user_id=member["value"], group_id=new_id))
        await db.commit()
        await db.refresh(group)
        members = await _load_group_members(db, new_id)
    return _group_to_scim(group, members, _base_url(request))
