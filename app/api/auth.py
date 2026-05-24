"""POST /auth/login - email+password -> JWT. Dev-only, real RBAC uses JWT downstream."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.rbac import get_user_by_email, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str  # In MVP we only check non-empty - real bcrypt verify is roadmap


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    user = await get_user_by_email(req.email)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not req.password:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_token(user)
    return LoginResponse(access_token=token)
