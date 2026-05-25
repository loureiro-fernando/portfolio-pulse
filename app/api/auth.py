"""POST /auth/login - email+password -> JWT. Verifies bcrypt-hashed passwords."""

import bcrypt
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.services.rbac import get_user_by_email, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


COOKIE_NAME = "portfolio_pulse_token"


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, response: Response) -> LoginResponse:
    user = await get_user_by_email(req.email)
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not bcrypt.checkpw(req.password.encode("utf-8"), user.password_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_token(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=8 * 60 * 60,
    )
    return LoginResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
