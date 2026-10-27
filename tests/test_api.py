"""End-to-end API tests on a real PostgreSQL database (no LLM calls: regex parser).

Uses TEST_DATABASE_URL, like tests/test_db.py. Run:  python -m pytest tests/test_api.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import api, db
from app.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]
TEST_URL = os.getenv("TEST_DATABASE_URL") or get_settings().test_database_url

pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture()
def client(monkeypatch):
    plain = TEST_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS app CASCADE; DROP SCHEMA IF EXISTS raw CASCADE;")
        conn.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        conn.execute((ROOT / "db" / "seed.sql").read_text(encoding="utf-8"))
    engine = create_engine(db.normalize_database_url(TEST_URL))
    monkeypatch.setattr(db, "get_engine", lambda url=None: engine)
    offline = Settings(groq_api_key="", gemini_api_key="", pollinations_enabled=False)
    monkeypatch.setattr(api, "_parser_settings", lambda: offline)
    yield TestClient(api.app)
    engine.dispose()


def login(client, email="alice@example.com", pin="1234"):
    resp = client.post("/login", json={"email": email, "pin": pin})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def say(client, headers, message):
    resp = client.post("/chat", json={"message": message}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "up"}


def test_r1_wrong_pin_and_missing_token_are_rejected(client):
    assert client.post("/login", json={"email": "alice@example.com", "pin": "9999"}).status_code == 401
    assert client.get("/orders").status_code == 401


def test_orders_include_items_and_only_own_orders(client):
    orders = client.get("/orders", headers=login(client)).json()
    assert {o["order_ref"] for o in orders} == {f"ORD-{n}" for n in range(10001, 10006)}
    assert orders[0]["items"][0]["product"]["name"]


def test_change_address_preview_then_confirm(client):
    headers = login(client)
    answer = say(client, headers, "Change the address of ORD-10001 to 12 MG Road, Pune")
    assert answer["needs_confirmation"]
    cr = answer["change_request"]
    assert cr["preview"] == {"current": {"shipping_address": "4 Park Street, Pune"},
                             "new": {"shipping_address": "12 MG Road, Pune"}}
    assert client.get("/orders/10001", headers=headers).json()["shipping_address"] == "4 Park Street, Pune"

    body = {"request_id": cr["request_id"], "action": "confirm", "idempotency_key": cr["idempotency_key"]}
    done = client.post("/confirm", json=body, headers=headers)
    assert done.status_code == 200 and "12 MG Road, Pune" in done.json()["message"]
    assert client.get("/orders/10001", headers=headers).json()["version"] == 2

    again = client.post("/confirm", json=body, headers=headers)  # double click: applied once only
    assert again.status_code == 409
    assert client.get("/orders/10001", headers=headers).json()["version"] == 2


def test_cancel_at_preview_changes_nothing(client):
    headers = login(client)
    cr = say(client, headers, "cancel order 10001")["change_request"]
    resp = client.post("/confirm", json={"request_id": cr["request_id"], "action": "cancel",
                                         "idempotency_key": cr["idempotency_key"]}, headers=headers)
    assert resp.status_code == 200
    assert client.get("/orders/10001", headers=headers).json()["status"] == "placed"


def test_r3_cancel_shipped_order_is_blocked(client):
    answer = say(client, login(client), "cancel order ORD-10002")
    assert not answer["needs_confirmation"]
    assert "shipped" in answer["reply"]


def test_r5_address_change_blocked_when_payment_failed(client):
    answer = say(client, login(client), "change address for ORD-10005 to 12 MG Road, Pune")
    assert not answer["needs_confirmation"] and "payment" in answer["reply"]


def test_r2_other_customers_order_is_not_found(client):
    answer = say(client, login(client), "cancel ORD-10006")
    assert not answer["needs_confirmation"]
    orders = client.get("/orders", headers=login(client, "bob@example.com")).json()
    assert orders[0]["status"] == "placed"


def test_r9_second_preview_on_same_order_is_blocked(client):
    headers = login(client)
    assert say(client, headers, "cancel order 10001")["needs_confirmation"]
    second = say(client, headers, "change address for ORD-10001 to 12 MG Road, Pune")
    assert not second["needs_confirmation"] and "waiting for confirmation" in second["reply"]


def test_r10_confirm_rechecks_rules(client):
    headers = login(client)
    cr = say(client, headers, "cancel order 10001")["change_request"]
    with db.get_engine().begin() as conn:  # the order ships while the preview is open
        conn.exec_driver_sql("UPDATE app.orders SET status = 'shipped' WHERE order_id = 10001")
    resp = client.post("/confirm", json={"request_id": cr["request_id"], "action": "confirm",
                                         "idempotency_key": cr["idempotency_key"]}, headers=headers)
    assert resp.status_code == 409
    assert client.get("/orders/10001", headers=headers).json()["status"] == "shipped"


def test_another_customer_cannot_confirm(client):
    cr = say(client, login(client), "cancel order 10001")["change_request"]
    resp = client.post("/confirm", json={"request_id": cr["request_id"], "action": "confirm"},
                       headers=login(client, "bob@example.com"))
    assert resp.status_code == 404


def test_track_and_escalate(client):
    headers = login(client)
    assert "shipped" in say(client, headers, "where is my order ORD-10002")["reply"]
    assert "human" in say(client, headers, "I want a refund for ORD-10003")["reply"]


def test_place_order_from_catalog_then_cancel_it(client):
    headers = login(client)
    products = client.get("/products").json()
    assert products and products[0]["name"]
    resp = client.post("/orders", json={"product_id": products[0]["product_id"], "quantity": 1},
                       headers=headers)
    assert resp.status_code == 201
    new = resp.json()
    assert new["status"] == "placed" and new["order_ref"].startswith("ORD-")
    answer = say(client, headers, f"cancel order {new['order_ref']}")
    assert answer["needs_confirmation"]


def test_place_order_unknown_product_is_rejected(client):
    resp = client.post("/orders", json={"product_id": 999999, "quantity": 1}, headers=login(client))
    assert resp.status_code == 400


def test_audit_lists_decisions_oldest_first(client):
    headers = login(client)
    say(client, headers, "cancel order ORD-10002")
    say(client, headers, "cancel order 10001")
    decisions = [a["decision"] for a in client.get("/audit", headers=headers).json()]
    assert decisions == ["blocked", "needs_confirmation"]
