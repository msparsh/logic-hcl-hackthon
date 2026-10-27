"""
Authentication helpers for the Autonomous Customer Support API.

Business rule R1 (docs/BUSINESS_RULES.md): the customer must be logged in, and
identity comes ONLY from a verified token, never from the chat text or a header
the client can set freely.

Flow:
1. POST /login with email + PIN.
2. The PIN is checked against a bcrypt hash (plain PINs are never stored).
3. On success we return a signed JWT whose "sub" claim is the customer_id.
4. Every protected endpoint calls `get_token_customer_id`, which rejects
   missing, tampered or expired tokens with HTTP 401.

This module knows nothing about where customers are stored; main.py does the
customer lookup. That keeps auth easy to test and easy to move to PostgreSQL.
"""
from datetime import datetime, timedelta, timezone
import logging
import secrets
import time
from typing import Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Settings (read from .env; see .env.example)
# ============================================================================

class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = AuthSettings()

# If no SECRET_KEY is set we still run, using a random key for this process.
# Tokens then stop working after a restart, which is safe for a demo.
if len(settings.secret_key) < 32:
    logger.warning("SECRET_KEY missing or shorter than 32 chars; using a random key for this run.")
    settings.secret_key = secrets.token_urlsafe(48)


# ============================================================================
# 2. PIN hashing (bcrypt)
# ============================================================================

def hash_pin(pin: str) -> str:
    """Returns a bcrypt hash of the PIN (salt is generated and stored inside the hash)."""
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, pin_hash: str) -> bool:
    """True if the PIN matches the stored bcrypt hash. Bad hashes count as no match."""
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))
    except ValueError:
        return False


# Used when the email does not exist, so a wrong email takes as long as a
# wrong PIN. Otherwise response time would reveal which emails are registered.
_DUMMY_HASH = hash_pin("0000")


def check_login(pin: str, pin_hash: Optional[str]) -> bool:
    """Checks a PIN; pass pin_hash=None when the email was not found."""
    if pin_hash is None:
        verify_pin(pin, _DUMMY_HASH)
        return False
    return verify_pin(pin, pin_hash)


# ============================================================================
# 3. Brute-force protection (a 4-digit PIN has only 10,000 options)
# ============================================================================

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60

# email -> timestamps of recent failed logins (in memory, like the rest of the demo)
_failed_logins: Dict[str, List[float]] = {}


def is_locked_out(email: str) -> bool:
    """True if this email had too many failed logins in the last LOCKOUT_SECONDS."""
    cutoff = time.time() - LOCKOUT_SECONDS
    recent = [t for t in _failed_logins.get(email, []) if t > cutoff]
    _failed_logins[email] = recent
    return len(recent) >= MAX_FAILED_ATTEMPTS


def record_failed_login(email: str) -> None:
    _failed_logins.setdefault(email, []).append(time.time())


def clear_failed_logins(email: str) -> None:
    _failed_logins.pop(email, None)


# ============================================================================
# 4. JWT access tokens
# ============================================================================

def create_access_token(customer_id: int) -> str:
    """Creates a signed token that proves who the customer is until it expires."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(customer_id),  # JWT spec requires "sub" to be a string
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> int:
    """Verifies signature and expiry, then returns the customer_id. Raises 401 on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],  # fixed list: blocks the "alg: none" trick
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired. Please log in again.")
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized("Invalid authentication token.")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# FastAPI's standard OAuth2 "password" flow. tokenUrl makes the Authorize button in
# /docs (Swagger) log in through POST /token. auto_error=False lets us return our
# own clear 401 message instead of FastAPI's default.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_token_customer_id(token: Optional[str] = Depends(oauth2_scheme)) -> int:
    """FastAPI dependency: returns the customer_id from a valid Bearer token, else 401."""
    if not token:
        raise _unauthorized("Not logged in. Send 'Authorization: Bearer <token>' from POST /login.")
    return decode_access_token(token)
