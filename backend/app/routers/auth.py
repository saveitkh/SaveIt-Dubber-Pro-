from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.telegram import verify_telegram_init_data
from app.auth.tokens import create_token, hash_password, verify_password
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, get_optional_user
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_MAX_AGE = 30 * 24 * 3600


def _set_auth_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="none",
        secure=True,
    )


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "displayName": user.display_name,
        "telegramId": user.telegram_id,
        "isAdmin": user.is_admin,
        "isLicensed": user.is_licensed,
    }


class TelegramAuthRequest(BaseModel):
    initData: str
    deviceId: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/telegram/enabled")
def telegram_login_enabled() -> dict:
    return {"enabled": bool(settings.studio_telegram_bot_token)}


@router.post("/telegram")
def auth_telegram(body: TelegramAuthRequest, db: Session = Depends(get_db)) -> JSONResponse:
    if not settings.studio_telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram login មិនទាន់កំណត់ (STUDIO_TELEGRAM_BOT_TOKEN)")
    tg_user = verify_telegram_init_data(body.initData, settings.studio_telegram_bot_token)
    if not tg_user:
        raise HTTPException(
            status_code=401,
            detail="ទិន្នន័យ Telegram មិនត្រឹមត្រូវ ឬផុតកំណត់ — សូមបើកពី Bot ម្តងទៀត",
        )
    telegram_id = str(tg_user["id"])
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        if not settings.studio_telegram_signup:
            raise HTTPException(status_code=403, detail="គណនីនេះមិនត្រូវបានអនុញ្ញាតទេ")
        user = User(
            telegram_id=telegram_id,
            display_name=" ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or None,
            username=tg_user.get("username"),
            is_admin=telegram_id in settings.telegram_admin_ids,
        )
        db.add(user)
        db.commit()
    elif telegram_id in settings.telegram_admin_ids and not user.is_admin:
        user.is_admin = True
        db.commit()

    token = create_token(user.id)
    response = JSONResponse(content={"token": token, "user": _user_public(user)})
    _set_auth_cookie(response, token)
    return response


@router.post("/register")
def register(body: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="ឈ្មោះអ្នកប្រើប្រាស់នេះមានរួចហើយ")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    token = create_token(user.id)
    response = JSONResponse(content={"token": token, "user": _user_public(user)})
    _set_auth_cookie(response, token)
    return response


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    user = db.query(User).filter(User.username == body.username).first()

    # Admin password fallback: first login with the configured admin password
    # creates (or promotes) the account, matching spec §7's browser-side fallback.
    if settings.studio_admin_password and body.password == settings.studio_admin_password:
        if not user:
            user = User(username=body.username, is_admin=True, password_hash=hash_password(body.password))
            db.add(user)
            db.commit()
        elif not user.is_admin:
            user.is_admin = True
            db.commit()
    elif not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ឈ្មោះអ្នកប្រើប្រាស់ ឬពាសសម្ងាត់មិនត្រឹមត្រូវ")
    token = create_token(user.id)
    response = JSONResponse(content={"token": token, "user": _user_public(user)})
    _set_auth_cookie(response, token)
    return response


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse(content={"success": True})
    response.delete_cookie(key="auth_token")
    return response


@router.get("/check-session")
def check_session(user: User | None = Depends(get_optional_user)) -> dict:
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": _user_public(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_public(user)
