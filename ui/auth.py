"""Basic-auth + bcrypt password hash kept in data/auth.json.

The bootstrap script seeds initial-password.txt and writes the bcrypt hash
into auth.json. The user can change the password from the settings page;
on change initial-password.txt is removed.
"""
from __future__ import annotations

import json
import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.hash import bcrypt

from .paths import AUTH_FILE, INITIAL_PASSWORD_FILE

basic = HTTPBasic(realm="chain-proxy")


def _load() -> dict:
    if not AUTH_FILE.exists():
        return {}
    return json.loads(AUTH_FILE.read_text())


def _save(data: dict) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(AUTH_FILE)
    os.chmod(AUTH_FILE, 0o600)


def ensure_initial(plain_password: Optional[str] = None) -> str:
    """Called on first start. If no auth.json yet, hash the password and store it.

    Returns the plain password (newly generated if not provided).
    """
    data = _load()
    if data.get("hash"):
        return ""
    if plain_password is None:
        plain_password = secrets.token_urlsafe(16)
    data = {"user": "admin", "hash": bcrypt.hash(plain_password)}
    _save(data)
    INITIAL_PASSWORD_FILE.write_text(plain_password + "\n")
    os.chmod(INITIAL_PASSWORD_FILE, 0o600)
    return plain_password


def change_password(new_password: str) -> None:
    data = _load()
    data["user"] = data.get("user", "admin")
    data["hash"] = bcrypt.hash(new_password)
    _save(data)
    if INITIAL_PASSWORD_FILE.exists():
        INITIAL_PASSWORD_FILE.unlink()


def verify(username: str, password: str) -> bool:
    data = _load()
    if not data.get("hash"):
        return False
    if not secrets.compare_digest(username, data.get("user", "admin")):
        return False
    try:
        return bcrypt.verify(password, data["hash"])
    except ValueError:
        return False


def require(request: Request, creds: HTTPBasicCredentials) -> str:
    if not verify(creds.username, creds.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="chain-proxy"'},
        )
    return creds.username
