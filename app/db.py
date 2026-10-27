"""PostgreSQL connection and repository.

All SQL in the application lives in this module. Every query is parameterised
(no string formatting of user input), and every query that touches an order
also filters by the logged-in customer's ID (business rule R2).

The only function that changes an order is ``apply_change_request``. It runs in
one transaction: lock the rows, re-check, update, write the audit log, commit.
If anything fails, the transaction rolls back and nothing is written (R10).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.config import get_settings

# Columns the agent is allowed to change, per intent. Nothing else can be updated.
ALLOWED_CHANGES: dict[str, str] = {
    "change_address": "shipping_address",
    "cancel_order": "status",
    "postpone_delivery": "delivery_date",
}

# A rule check is called inside the transaction with the locked order and the
# change request. It returns a list of {"rule", "passed", "reason"} dicts.
RuleCheck = Callable[[dict, dict], list[dict]]


class DatabaseError(Exception):
    """Base class for repository errors that the API should show clearly."""


class PendingChangeExists(DatabaseError):
    """R9: this order already has a change waiting for confirmation."""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def normalize_database_url(url: str) -> str:
    """Make any Postgres URL use the psycopg 3 driver.

    Neon and most providers return ``postgresql://`` or ``postgres://`` URLs;
    SQLAlchemy needs ``postgresql+psycopg://`` to use psycopg 3.
    """
    url = url.strip()
    if url.startswith("sqlite"):
        raise DatabaseError("DATABASE_URL points to SQLite; this project uses PostgreSQL.")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_engine(url: Optional[str] = None) -> Engine:
    """Create (once) the connection pool for the given URL, or DATABASE_URL."""
    settings = get_settings()
    return create_engine(
        normalize_database_url(url or settings.database_url),
        pool_pre_ping=True,  # survive dropped connections (serverless Postgres)
        echo=settings.db_echo,
    )


def check_connection(engine: Optional[Engine] = None) -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _row(result) -> Optional[dict]:
    row = result.mappings().first()
    return dict(row) if row else None


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    """Convert dates and decimals so they can be stored in a JSONB column."""
    return json.loads(json.dumps(value, default=str))


# ---------------------------------------------------------------------------
# Customers and orders (read-only)
# ---------------------------------------------------------------------------

def get_customer_by_email(email: str, engine: Optional[Engine] = None) -> Optional[dict]:
    """Look up a customer for login. Includes pin_hash; never return it to the UI."""
    with (engine or get_engine()).connect() as conn:
        return _row(conn.execute(
            text("SELECT * FROM app.customers WHERE lower(email) = lower(:email)"),
            {"email": email.strip()},
        ))


def get_customer(customer_id: int, engine: Optional[Engine] = None) -> Optional[dict]:
    """Return a customer's public profile (no pin_hash)."""
    with (engine or get_engine()).connect() as conn:
        return _row(conn.execute(
            text("""SELECT customer_id, first_name, last_name, email, home_location,
                           home_country, joined_at
                    FROM app.customers WHERE customer_id = :cid"""),
            {"cid": customer_id},
        ))


def list_orders(customer_id: int, engine: Optional[Engine] = None) -> list[dict]:
    """All orders of one customer, newest first."""
    with (engine or get_engine()).connect() as conn:
        return _rows(conn.execute(
            text("SELECT * FROM app.orders WHERE customer_id = :cid ORDER BY created_at DESC"),
            {"cid": customer_id},
        ))


def get_order(order_id: int, customer_id: int, engine: Optional[Engine] = None) -> Optional[dict]:
    """One order, only if it belongs to this customer (R2). Otherwise None."""
    with (engine or get_engine()).connect() as conn:
        return _row(conn.execute(
            text("SELECT * FROM app.orders WHERE order_id = :oid AND customer_id = :cid"),
            {"oid": order_id, "cid": customer_id},
        ))


def get_order_items(order_id: int, customer_id: int, engine: Optional[Engine] = None) -> list[dict]:
    """Products in an order, with names, for the preview screen."""
    with (engine or get_engine()).connect() as conn:
        return _rows(conn.execute(
            text("""SELECT i.product_id, p.name, i.quantity, i.item_price
                    FROM app.order_items i
                    JOIN app.orders o ON o.order_id = i.order_id
                    JOIN app.products p ON p.product_id = i.product_id
                    WHERE i.order_id = :oid AND o.customer_id = :cid
                    ORDER BY p.name"""),
            {"oid": order_id, "cid": customer_id},
        ))


def list_customer_order_items(customer_id: int, engine: Optional[Engine] = None) -> list[dict]:
    """Products of all of one customer's orders, in one query (for the orders page)."""
    with (engine or get_engine()).connect() as conn:
        return _rows(conn.execute(
            text("""SELECT i.order_id, i.product_id, p.name, p.category, p.base_colour,
                           p.article_type, i.quantity, i.item_price
                    FROM app.order_items i
                    JOIN app.orders o ON o.order_id = i.order_id
                    JOIN app.products p ON p.product_id = i.product_id
                    WHERE o.customer_id = :cid
                    ORDER BY i.order_id, p.name"""),
            {"cid": customer_id},
        ))


def list_products(limit: int = 12, engine: Optional[Engine] = None) -> list[dict]:
    """Catalog for the store page: most-ordered products first, with a reference price."""
    with (engine or get_engine()).connect() as conn:
        return _rows(conn.execute(
            text("""SELECT p.product_id, p.name, p.category, p.sub_category, p.article_type,
                           p.base_colour, COALESCE(MAX(i.item_price), 999.00) AS price,
                           COUNT(i.order_id) AS times_ordered
                    FROM app.products p
                    LEFT JOIN app.order_items i ON i.product_id = p.product_id
                    GROUP BY p.product_id
                    ORDER BY times_ordered DESC, p.product_id
                    LIMIT :lim"""),
            {"lim": max(1, min(limit, 100))},
        ))


def create_order(customer_id: int, product_id: int, quantity: int = 1,
                 engine: Optional[Engine] = None) -> dict:
    """Place a new order (status placed, paid) shipped to the customer's latest address."""
    if quantity < 1 or quantity > 10:
        raise DatabaseError("Quantity must be between 1 and 10.")
    with (engine or get_engine()).begin() as conn:
        product = _row(conn.execute(
            text("""SELECT p.product_id, COALESCE(MAX(i.item_price), 999.00) AS price
                    FROM app.products p LEFT JOIN app.order_items i ON i.product_id = p.product_id
                    WHERE p.product_id = :pid GROUP BY p.product_id"""),
            {"pid": product_id},
        ))
        if product is None:
            raise DatabaseError("Product not found.")
        customer = _row(conn.execute(
            text("""SELECT c.home_location, c.home_country,
                           (SELECT o.shipping_address FROM app.orders o WHERE o.customer_id = c.customer_id
                            ORDER BY o.created_at DESC LIMIT 1) AS last_address
                    FROM app.customers c WHERE c.customer_id = :cid"""),
            {"cid": customer_id},
        ))
        if customer is None:
            raise DatabaseError("Customer not found.")
        address = customer["last_address"] or customer["home_location"] or "Address on file"
        if len(address.strip()) < 5:
            address = f"{address}, {customer['home_country'] or ''}".strip(", ")
        delivery = date.today() + timedelta(days=5)
        total = product["price"] * quantity
        order = _row(conn.execute(
            text("""INSERT INTO app.orders
                        (booking_id, customer_id, created_at, payment_method, payment_status, status,
                         shipping_address, shipping_country, delivery_date, original_delivery_date,
                         promo_amount, shipment_fee, total_amount)
                    VALUES (:bid, :cid, now(), 'UPI', 'Success', 'placed', :addr, :country,
                            :dd, :dd, 0, 0, :total)
                    RETURNING *"""),
            {"bid": f"WEB-{uuid.uuid4().hex[:12]}", "cid": customer_id, "addr": address,
             "country": customer["home_country"] or "India", "dd": delivery, "total": total},
        ))
        conn.execute(
            text("""INSERT INTO app.order_items (order_id, product_id, quantity, item_price)
                    VALUES (:oid, :pid, :qty, :price)"""),
            {"oid": order["order_id"], "pid": product_id, "qty": quantity, "price": product["price"]},
        )
        _insert_audit(conn, customer_id=customer_id, order_id=order["order_id"], action="order_placed",
                      decision="approved", after_state={"status": "placed", "product_id": product_id,
                                                        "quantity": quantity})
        return order


# ---------------------------------------------------------------------------
# Audit log (append-only)
# ---------------------------------------------------------------------------

def _insert_audit(conn: Connection, **fields: Any) -> int:
    """Insert one audit row on an open connection and return its ID."""
    row = conn.execute(
        text("""INSERT INTO app.audit_log
                    (request_id, customer_id, order_id, action, decision, rule_results,
                     before_state, after_state, fallback_used, latency_ms)
                VALUES (:request_id, :customer_id, :order_id, :action, :decision,
                        CAST(:rule_results AS jsonb), CAST(:before_state AS jsonb),
                        CAST(:after_state AS jsonb), :fallback_used, :latency_ms)
                RETURNING audit_id"""),
        {
            "request_id": fields.get("request_id"),
            "customer_id": fields.get("customer_id"),
            "order_id": fields.get("order_id"),
            "action": fields["action"],
            "decision": fields["decision"],
            "rule_results": json.dumps(_jsonable(fields.get("rule_results") or {})),
            "before_state": json.dumps(_jsonable(fields.get("before_state"))),
            "after_state": json.dumps(_jsonable(fields.get("after_state"))),
            "fallback_used": bool(fields.get("fallback_used", False)),
            "latency_ms": fields.get("latency_ms"),
        },
    ).first()
    return int(row[0])


def write_audit(
    *,
    action: str,
    decision: str,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    request_id: Optional[str] = None,
    rule_results: Optional[dict | list] = None,
    before_state: Optional[dict] = None,
    after_state: Optional[dict] = None,
    fallback_used: bool = False,
    latency_ms: Optional[int] = None,
    engine: Optional[Engine] = None,
) -> int:
    """Record one decision (for example a blocked request) in its own transaction."""
    with (engine or get_engine()).begin() as conn:
        return _insert_audit(
            conn, action=action, decision=decision, customer_id=customer_id,
            order_id=order_id, request_id=request_id, rule_results=rule_results,
            before_state=before_state, after_state=after_state,
            fallback_used=fallback_used, latency_ms=latency_ms,
        )


def list_audit(customer_id: int, limit: int = 50, engine: Optional[Engine] = None) -> list[dict]:
    """Latest audit rows for one customer, newest first."""
    with (engine or get_engine()).connect() as conn:
        return _rows(conn.execute(
            text("""SELECT * FROM app.audit_log WHERE customer_id = :cid
                    ORDER BY created_at DESC, audit_id DESC LIMIT :lim"""),
            {"cid": customer_id, "lim": max(1, min(limit, 200))},
        ))


# ---------------------------------------------------------------------------
# Change requests: preview -> confirm -> apply
# ---------------------------------------------------------------------------

def create_change_request(
    *,
    customer_id: int,
    order_id: int,
    intent: str,
    proposed_change: dict,
    session_id: str,
    confidence: Optional[float] = None,
    ttl_minutes: Optional[int] = None,
    engine: Optional[Engine] = None,
) -> dict:
    """Save a preview that waits for the customer's confirmation.

    The preview (old and new value) is built here from the database row,
    never from LLM text. Raises PendingChangeExists if the order already has a
    pending change (R9), and DatabaseError if the order is not this customer's.
    """
    if intent not in ALLOWED_CHANGES:
        raise DatabaseError(f"Intent '{intent}' does not change data.")
    column = ALLOWED_CHANGES[intent]
    ttl = ttl_minutes or get_settings().preview_ttl_minutes

    with (engine or get_engine()).begin() as conn:
        order = _row(conn.execute(
            text("SELECT * FROM app.orders WHERE order_id = :oid AND customer_id = :cid"),
            {"oid": order_id, "cid": customer_id},
        ))
        if order is None:
            raise DatabaseError("Order not found in this account.")

        # A preview nobody answered must not block this order forever (R9).
        conn.execute(
            text("""UPDATE app.change_requests SET status = 'expired', decided_at = now()
                    WHERE order_id = :oid AND status = 'pending' AND expires_at < now()"""),
            {"oid": order_id},
        )

        new_value = "cancelled" if intent == "cancel_order" else proposed_change.get(column)
        preview = {"field": column, "old": order[column], "new": new_value,
                   "order_ref": order["order_ref"]}
        request_id = str(uuid.uuid4())
        try:
            row = _row(conn.execute(
                text("""INSERT INTO app.change_requests
                            (request_id, session_id, customer_id, order_id, intent, confidence,
                             proposed_change, preview, order_version, status,
                             idempotency_key, expires_at)
                        VALUES (:rid, :sid, :cid, :oid, :intent, :conf,
                                CAST(:proposed AS jsonb), CAST(:preview AS jsonb), :ver,
                                'pending', :idem, :exp)
                        RETURNING *"""),
                {
                    "rid": request_id, "sid": session_id, "cid": customer_id, "oid": order_id,
                    "intent": intent, "conf": confidence,
                    "proposed": json.dumps(_jsonable({column: new_value})),
                    "preview": json.dumps(_jsonable(preview)),
                    "ver": order["version"], "idem": uuid.uuid4().hex,
                    "exp": _utc_now() + timedelta(minutes=ttl),
                },
            ))
        except IntegrityError as exc:
            if "uq_one_pending_change_per_order" in str(exc.orig):
                raise PendingChangeExists(
                    f"Order {order['order_ref']} already has a change waiting for confirmation."
                ) from exc
            raise
        _insert_audit(conn, request_id=request_id, customer_id=customer_id, order_id=order_id,
                      action="preview_shown", decision="needs_confirmation",
                      before_state={column: order[column]}, after_state={column: new_value})
        return row


def get_change_request(request_id: str, customer_id: int, engine: Optional[Engine] = None) -> Optional[dict]:
    """One change request, only if it belongs to this customer."""
    with (engine or get_engine()).connect() as conn:
        return _row(conn.execute(
            text("SELECT * FROM app.change_requests WHERE request_id = :rid AND customer_id = :cid"),
            {"rid": request_id, "cid": customer_id},
        ))


def decline_change_request(request_id: str, customer_id: int, engine: Optional[Engine] = None) -> dict:
    """The customer chose Cancel at the preview: nothing is changed."""
    with (engine or get_engine()).begin() as conn:
        req = _row(conn.execute(
            text("""SELECT * FROM app.change_requests
                    WHERE request_id = :rid AND customer_id = :cid FOR UPDATE"""),
            {"rid": request_id, "cid": customer_id},
        ))
        if req is None:
            return {"decision": "blocked", "reason": "Change request not found."}
        if req["status"] != "pending":
            return {"decision": "blocked", "reason": f"Request is already {req['status']}."}
        conn.execute(
            text("""UPDATE app.change_requests SET status = 'declined', decided_at = now()
                    WHERE request_id = :rid"""),
            {"rid": request_id},
        )
        _insert_audit(conn, request_id=request_id, customer_id=customer_id,
                      order_id=req["order_id"], action=req["intent"], decision="declined")
    return {"decision": "declined", "reason": "No changes were made."}


def apply_change_request(
    request_id: str,
    customer_id: int,
    rule_check: Optional[RuleCheck] = None,
    engine: Optional[Engine] = None,
) -> dict:
    """Apply a confirmed change in ONE transaction (R10).

    Steps: lock the request and the order (FOR UPDATE), check the request is
    pending and not expired, check the order version is unchanged since the
    preview, re-run the business rules, update only the allowed column, mark
    the request applied, write the audit row, commit.

    Returns {"decision": approved|blocked|expired|failed, "reason": str,
    "order": dict|None, "rule_results": list}. On anything but approved,
    no order data is changed.
    """
    eng = engine or get_engine()
    outcome: dict[str, Any] = {"decision": "failed", "reason": "", "order": None, "rule_results": []}
    req: Optional[dict] = None
    try:
        with eng.begin() as conn:
            req = _row(conn.execute(
                text("""SELECT * FROM app.change_requests
                        WHERE request_id = :rid AND customer_id = :cid FOR UPDATE"""),
                {"rid": request_id, "cid": customer_id},
            ))
            if req is None:
                return {**outcome, "decision": "blocked", "reason": "Change request not found."}
            if req["status"] != "pending":
                # Second click on Confirm, or replayed request: never applied twice.
                return {**outcome, "decision": "blocked",
                        "reason": f"Request is already {req['status']}."}
            if req["expires_at"] < _utc_now():
                conn.execute(
                    text("""UPDATE app.change_requests SET status = 'expired', decided_at = now()
                            WHERE request_id = :rid"""),
                    {"rid": request_id},
                )
                _insert_audit(conn, request_id=request_id, customer_id=customer_id,
                              order_id=req["order_id"], action=req["intent"], decision="expired")
                return {**outcome, "decision": "expired",
                        "reason": "The preview expired. Please send the request again."}

            order = _row(conn.execute(
                text("""SELECT * FROM app.orders
                        WHERE order_id = :oid AND customer_id = :cid FOR UPDATE"""),
                {"oid": req["order_id"], "cid": customer_id},
            ))
            if order is None:
                raise _Blocked("Order not found in this account.", [])
            if order["version"] != req["order_version"]:
                raise _Blocked("The order changed after the preview. Please review it again.",
                               [{"rule": "R10_version_unchanged", "passed": False,
                                 "reason": "order version changed"}])

            results = rule_check(order, req) if rule_check else []
            failed = [r for r in results if not r.get("passed")]
            if failed:
                raise _Blocked(failed[0].get("reason") or "A business rule failed.", results)

            column = ALLOWED_CHANGES[req["intent"]]
            new_value = req["proposed_change"][column]
            if column == "delivery_date" and isinstance(new_value, str):
                new_value = date.fromisoformat(new_value)
            # The column name comes from the fixed ALLOWED_CHANGES map, never from user input.
            updated = _row(conn.execute(
                text(f"""UPDATE app.orders
                         SET {column} = :val, version = version + 1, updated_at = now()
                         WHERE order_id = :oid AND version = :ver
                         RETURNING *"""),
                {"val": new_value, "oid": order["order_id"], "ver": req["order_version"]},
            ))
            if updated is None:
                raise _Blocked("The order changed after the preview. Please review it again.", results)

            conn.execute(
                text("""UPDATE app.change_requests SET status = 'applied', decided_at = now()
                        WHERE request_id = :rid"""),
                {"rid": request_id},
            )
            _insert_audit(conn, request_id=request_id, customer_id=customer_id,
                          order_id=order["order_id"], action=req["intent"], decision="approved",
                          rule_results=results, before_state={column: order[column],
                                                              "version": order["version"]},
                          after_state={column: updated[column], "version": updated["version"]})
            return {"decision": "approved", "reason": "Change applied.", "order": updated,
                    "rule_results": results}
    except _Blocked as blocked:
        # The transaction above was rolled back; record the block in a new one.
        with eng.begin() as conn:
            conn.execute(
                text("""UPDATE app.change_requests SET status = 'blocked', decided_at = now()
                        WHERE request_id = :rid AND status = 'pending'"""),
                {"rid": request_id},
            )
            _insert_audit(conn, request_id=request_id, customer_id=customer_id,
                          order_id=req["order_id"] if req else None,
                          action=req["intent"] if req else "confirm", decision="blocked",
                          rule_results=blocked.rule_results)
        return {**outcome, "decision": "blocked", "reason": blocked.reason,
                "rule_results": blocked.rule_results}
    except Exception as exc:  # database or unexpected error: rolled back, nothing written
        try:
            write_audit(action=req["intent"] if req else "confirm", decision="failed",
                        customer_id=customer_id, order_id=req["order_id"] if req else None,
                        request_id=request_id if req else None,
                        rule_results={"error": type(exc).__name__}, engine=eng)
        except Exception:
            pass
        return {**outcome, "decision": "failed",
                "reason": "The change could not be saved. Nothing was changed."}


class _Blocked(Exception):
    """Internal: abort the transaction because a check failed."""

    def __init__(self, reason: str, rule_results: list[dict]):
        super().__init__(reason)
        self.reason = reason
        self.rule_results = rule_results
