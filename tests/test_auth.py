"""
Tests for authentication (rule R1: identity comes only from a verified token).
Run with: .venv/bin/python -m pytest tests/test_auth.py
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

import auth
from main import app

client = TestClient(app)
GOOD = {"email": "alice@example.com", "pin": "1234"}


@pytest.fixture(autouse=True)
def reset_lockout():
    """Failed-login counters are global; clear them so tests do not affect each other."""
    auth._failed_logins.clear()


def login_token() -> str:
    return client.post("/login", json=GOOD).json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- PIN hashing -----------------------------------------------------------

def test_hash_is_not_plain_and_verifies():
    h = auth.hash_pin("1234")
    assert h != "1234"
    assert auth.verify_pin("1234", h)


def test_wrong_pin_fails_and_bad_hash_is_no_match():
    assert not auth.verify_pin("9999", auth.hash_pin("1234"))
    assert not auth.verify_pin("1234", "not-a-bcrypt-hash")


# --- /login ----------------------------------------------------------------

def test_login_success_returns_token():
    r = client.post("/login", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["customer_id"] == 1
    assert body["expires_in"] == auth.settings.access_token_expire_minutes * 60


def test_login_wrong_pin_is_401():
    r = client.post("/login", json={**GOOD, "pin": "9999"})
    assert r.status_code == 401


def test_login_unknown_email_gives_same_message_as_wrong_pin():
    wrong_pin = client.post("/login", json={**GOOD, "pin": "9999"}).json()
    unknown = client.post("/login", json={"email": "nobody@example.com", "pin": "1234"}).json()
    assert wrong_pin == unknown


@pytest.mark.parametrize("bad", [
    {},                                           # empty body
    {"email": "alice@example.com"},               # missing pin
    {"email": "not-an-email", "pin": "1234"},     # bad email
    {"email": "alice@example.com", "pin": "abcd"},  # non-numeric pin
    {"email": "alice@example.com", "pin": "12"},    # too short
])
def test_login_bad_input_is_422(bad):
    assert client.post("/login", json=bad).status_code == 422


def test_login_locks_out_after_repeated_failures():
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert client.post("/login", json={**GOOD, "pin": "9999"}).status_code == 401
    # Even the correct PIN is refused while locked
    assert client.post("/login", json=GOOD).status_code == 429


# --- Protected endpoints (R1) ----------------------------------------------

@pytest.mark.parametrize("path", ["/orders", "/audit", "/me"])
def test_r1_no_token_is_401(path):
    assert client.get(path).status_code == 401


def test_r1_valid_token_is_accepted():
    r = client.get("/me", headers=bearer(login_token()))
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"


def test_r1_old_guessable_token_is_rejected():
    assert client.get("/orders", headers=bearer("cust_1")).status_code == 401


def test_r1_customer_id_header_cannot_override_identity():
    # The old X-Customer-ID header must be ignored; without a token it is still 401
    assert client.get("/orders", headers={"X-Customer-ID": "1"}).status_code == 401


def test_r1_tampered_token_is_rejected():
    forged = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "wrong-secret-wrong-secret-wrong-secret", algorithm="HS256")
    assert client.get("/me", headers=bearer(forged)).status_code == 401


def test_r1_expired_token_is_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"sub": "1", "exp": past}, auth.settings.secret_key, algorithm="HS256")
    r = client.get("/me", headers=bearer(expired))
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_r1_alg_none_token_is_rejected():
    unsigned = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                          None, algorithm="none")
    assert client.get("/me", headers=bearer(unsigned)).status_code == 401


def test_r1_token_for_deleted_customer_is_rejected():
    token = auth.create_access_token(999)  # signed correctly, but no such customer
    assert client.get("/me", headers=bearer(token)).status_code == 401


# --- OAuth2 password flow (Authorize button in /docs) -----------------------

def test_token_endpoint_accepts_form_login():
    r = client.post("/token", data={"username": "alice@example.com", "password": "1234"})
    assert r.status_code == 200
    assert client.get("/me", headers=bearer(r.json()["access_token"])).status_code == 200


def test_token_endpoint_wrong_password_is_401():
    r = client.post("/token", data={"username": "alice@example.com", "password": "9999"})
    assert r.status_code == 401
