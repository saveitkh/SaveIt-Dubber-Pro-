from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.tokens import decode_token
from app.db import get_db
from app.models import User


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    header_token = request.headers.get("x-auth-token")
    if header_token:
        return header_token
    query_token = request.query_params.get("access_token")
    if query_token:
        return query_token
    return request.cookies.get("auth_token")


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    return db.get(User, user_id)


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
