"""Repository tests against a real PostgreSQL database.

Set TEST_DATABASE_URL to an EMPTY test database (never the shared one): the
tests drop and recreate the schemas and load db/seed.sql before each test.
Run from the repository root:  python -m pytest tests/test_db.py -v
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app import db
from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
TEST_URL = os.getenv("TEST_DATABASE_URL") or get_settings().test_database_url

pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not set")

ALICE, BOB = 1, 2
PLACED, SHIPPED, BOBS_ORDER = 10001, 10002, 10006


@pytest.fixture()
def engine():
    """Fresh schema + seed for every test."""
    plain = TEST_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS app CASCADE; DROP SCHEMA IF EXISTS raw CASCADE;")
        conn.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        conn.execute((ROOT / "db" / "seed.sql").read_text(encoding="utf-8"))
    eng = create_engine(db.normalize_database_url(TEST_URL))
    yield eng
    eng.dispose()


def test_normalize_database_url_adds_psycopg_driver():
    assert db.normalize_database_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert db.normalize_database_url("postgresql://u:p@h/d?sslmode=require") == \
        "postgresql+psycopg://u:p@h/d?sslmode=require"


def test_sqlite_url_is_rejected():
    with pytest.raises(db.DatabaseError):
        db.normalize_database_url("sqlite:///./logic.db")


def test_check_connection(engine):
    assert db.check_connection(engine)


def test_customer_lookup_by_email_is_case_insensitive(engine):
    customer = db.get_customer_by_email("  ALICE@example.com ", engine=engine)
    assert customer["customer_id"] == ALICE
    assert customer["pin_hash"].startswith("$2b$")


def test_public_profile_has_no_pin_hash(engine):
    assert "pin_hash" not in db.get_customer(ALICE, engine=engine)


def test_r2_order_of_another_customer_is_not_visible(engine):
    assert db.get_order(BOBS_ORDER, ALICE, engine=engine) is None
    assert db.get_order(BOBS_ORDER, BOB, engine=engine)["order_ref"] == "ORD-10006"
    assert all(o["customer_id"] == ALICE for o in db.list_orders(ALICE, engine=engine))


def test_order_items_include_product_names(engine):
    items = db.get_order_items(PLACED, ALICE, engine=engine)
    assert items and items[0]["name"]
    assert db.get_order_items(BOBS_ORDER, ALICE, engine=engine) == []


def test_preview_is_built_from_database_values(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="change_address",
                                   proposed_change={"shipping_address": "12 MG Road, Pune"},
                                   session_id="s1", confidence=0.9, engine=engine)
    assert req["status"] == "pending"
    assert req["preview"]["old"] == "4 Park Street, Pune"
    assert req["preview"]["new"] == "12 MG Road, Pune"
    assert req["order_version"] == 1


def test_r9_second_pending_change_on_same_order_is_rejected(engine):
    db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                             proposed_change={}, session_id="s1", engine=engine)
    with pytest.raises(db.PendingChangeExists):
        db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="change_address",
                                 proposed_change={"shipping_address": "12 MG Road, Pune"},
                                 session_id="s1", engine=engine)


def test_change_request_for_another_customers_order_is_rejected(engine):
    with pytest.raises(db.DatabaseError):
        db.create_change_request(customer_id=ALICE, order_id=BOBS_ORDER, intent="cancel_order",
                                 proposed_change={}, session_id="s1", engine=engine)


def test_apply_change_updates_order_and_writes_audit(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="change_address",
                                   proposed_change={"shipping_address": "12 MG Road, Pune"},
                                   session_id="s1", engine=engine)
    result = db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)
    assert result["decision"] == "approved"
    order = db.get_order(PLACED, ALICE, engine=engine)
    assert order["shipping_address"] == "12 MG Road, Pune"
    assert order["version"] == 2
    decisions = [a["decision"] for a in db.list_audit(ALICE, engine=engine)]
    assert decisions[:2] == ["approved", "needs_confirmation"]


def test_cancel_sets_status_cancelled(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    assert db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)["decision"] == "approved"
    assert db.get_order(PLACED, ALICE, engine=engine)["status"] == "cancelled"


def test_double_confirm_applies_only_once(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    first = db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)
    second = db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)
    assert first["decision"] == "approved"
    assert second["decision"] == "blocked"
    assert db.get_order(PLACED, ALICE, engine=engine)["version"] == 2


def test_r10_failed_rule_at_confirm_changes_nothing(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)

    def order_has_shipped(order, change_request):
        return [{"rule": "R3_cancel_only_when_placed", "passed": False, "reason": "Order has shipped."}]

    result = db.apply_change_request(str(req["request_id"]), ALICE,
                                     rule_check=order_has_shipped, engine=engine)
    assert result["decision"] == "blocked"
    assert result["reason"] == "Order has shipped."
    order = db.get_order(PLACED, ALICE, engine=engine)
    assert order["status"] == "placed" and order["version"] == 1
    assert db.get_change_request(str(req["request_id"]), ALICE, engine=engine)["status"] == "blocked"


def test_r10_order_changed_after_preview_is_blocked(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    with engine.begin() as conn:  # simulate another session changing the order
        conn.execute(text("UPDATE app.orders SET version = version + 1 WHERE order_id = :o"),
                     {"o": PLACED})
    result = db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)
    assert result["decision"] == "blocked"
    assert db.get_order(PLACED, ALICE, engine=engine)["status"] == "placed"


def test_r9_expired_preview_is_not_applied(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.change_requests SET expires_at = now() - :d WHERE request_id = :r"),
                     {"d": timedelta(minutes=1), "r": req["request_id"]})
    result = db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)
    assert result["decision"] == "expired"
    assert db.get_order(PLACED, ALICE, engine=engine)["status"] == "placed"


def test_another_customer_cannot_confirm(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    assert db.apply_change_request(str(req["request_id"]), BOB, engine=engine)["decision"] == "blocked"
    assert db.get_order(PLACED, ALICE, engine=engine)["status"] == "placed"


def test_decline_changes_nothing(engine):
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="cancel_order",
                                   proposed_change={}, session_id="s1", engine=engine)
    assert db.decline_change_request(str(req["request_id"]), ALICE, engine=engine)["decision"] == "declined"
    assert db.get_order(PLACED, ALICE, engine=engine)["status"] == "placed"


def test_postpone_updates_delivery_date(engine):
    order = db.get_order(PLACED, ALICE, engine=engine)
    new_date = order["delivery_date"] + timedelta(days=2)
    req = db.create_change_request(customer_id=ALICE, order_id=PLACED, intent="postpone_delivery",
                                   proposed_change={"delivery_date": new_date.isoformat()},
                                   session_id="s1", engine=engine)
    assert db.apply_change_request(str(req["request_id"]), ALICE, engine=engine)["decision"] == "approved"
    assert db.get_order(PLACED, ALICE, engine=engine)["delivery_date"] == new_date


def test_audit_log_cannot_be_edited(engine):
    db.write_audit(action="test", decision="blocked", customer_id=ALICE, engine=engine)
    with pytest.raises(DBAPIError, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.audit_log SET action = 'tampered'"))
