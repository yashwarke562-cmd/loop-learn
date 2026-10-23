"""Authentication. Two modes: header-based 'demo' for local use, verified 'firebase' ID tokens for real use."""
from __future__ import annotations

import hmac
import re
from dataclasses import dataclass

from fastapi import HTTPException, Request

USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ROLES = ("student", "teacher")


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


def _firebase_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        claims = fb_auth.verify_id_token(header[7:])
    except Exception:
        raise HTTPException(401, "Invalid token")
    role = claims.get("role", "student")  # teacher role comes only from a server-set custom claim
    if role not in ROLES:
        role = "student"
    return Principal(user_id=claims["uid"], role=role)


def _demo_principal(request: Request) -> Principal:
    settings = request.app.state.settings
    uid = request.headers.get("x-demo-user", "")
    role = request.headers.get("x-demo-role", "student")
    if not USER_RE.fullmatch(uid):
        raise HTTPException(401, "Enter a name using letters, numbers, - or _ (max 32).")
    if role not in ROLES:
        raise HTTPException(401, "Unknown role")
    if role == "teacher":
        pin = request.headers.get("x-demo-pin", "")
        if not hmac.compare_digest(pin.encode(), settings.teacher_pin.encode()):
            raise HTTPException(403, "Wrong teacher PIN")
    return Principal(user_id=uid, role=role)


def get_principal(request: Request) -> Principal:
    if request.app.state.settings.auth_mode == "firebase":
        return _firebase_principal(request)
    return _demo_principal(request)
