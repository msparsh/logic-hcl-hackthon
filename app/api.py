"""FastAPI backend on PostgreSQL. Run from the repository root:

    uvicorn app.api:app --reload --port 8000

Same endpoints and response shapes that streamlit_app.py expects, but every
read and write goes to PostgreSQL through app/db.py. Login and tokens come
from auth.py.

Flow of POST /chat:
    token -> customer_id (R1) -> parse message (LLM, regex fallback) ->
    order must be the customer's (R2) -> business rules (R3-R8) ->
    save a preview (R9) -> the customer confirms -> POST /confirm re-checks
    every rule on the locked row and applies it in one transaction (R10).
"""
from __future__ import annotations

import time
import uuid
from functools import lru_cache
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from app import db
from app.config import Settings, get_settings
from app.rules import check_change, first_failure, rule_check_for_confirm
from app.intent import Intent, compose_reply, parse_message
from auth import (
    check_login,
    clear_failed_logins,
    create_access_token,
    get_token_customer_id,
    is_locked_out,
    record_failed_login,
)

app = FastAPI(title="Team Logic - Autonomous Customer Support", version="1.0.0")

_COLUMN = db.ALLOWED_CHANGES  # intent -> the one column it may change


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(..., max_length=200)
    pin: str = Field(..., min_length=4, max_length=12)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class ConfirmRequest(BaseModel):
    request_id: uuid.UUID
    action: Literal["confirm", "cancel"] = "confirm"
    idempotency_key: Optional[str] = None


@app.exception_handler(OperationalError)
def database_unavailable(_: Request, __: OperationalError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database is not reachable. Check DATABASE_URL."})


@lru_cache
def _parser_settings() -> Settings:
    """Short LLM timeout so a slow provider falls back to regex quickly."""
    s = get_settings()
    return s.model_copy(update={"llm_timeout_seconds": min(s.llm_timeout_seconds, 2.5)})


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


# ---------------------------------------------------------------------------
# Health and login
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> dict:
    return {"service": "Team Logic customer support API", "docs": "/docs"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": "up" if db.check_connection() else "down"}


def _login(email: str, pin: str) -> dict:
    email = email.strip().lower()
    if is_locked_out(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many failed attempts. Try again in 5 minutes.")
    customer = db.get_customer_by_email(email)
    if not check_login(pin, customer["pin_hash"] if customer else None):
        record_failed_login(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or PIN.")
    clear_failed_logins(email)
    name = f"{customer['first_name']} {customer.get('last_name') or ''}".strip()
    return {"access_token": create_access_token(int(customer["customer_id"])), "token_type": "bearer",
            "customer_id": int(customer["customer_id"]), "customer_email": customer["email"],
            "customer_name": name}


@app.post("/login")
def login(body: LoginRequest) -> dict:
    return _login(body.email, body.pin)


@app.post("/token", include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    """Used by the Authorize button in /docs (username = email, password = PIN)."""
    return _login(form.username, form.password)


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------

@app.get("/orders")
def orders(customer_id: int = Depends(get_token_customer_id)) -> list[dict]:
    items_by_order: dict[int, list[dict]] = {}
    for item in db.list_customer_order_items(customer_id):
        items_by_order.setdefault(item["order_id"], []).append({
            "product_id": item["product_id"], "quantity": item["quantity"],
            "item_price": item["item_price"],
            "product": {"name": item["name"], "category": item["category"],
                        "base_colour": item["base_colour"], "article_type": item["article_type"]},
        })
    return [{**o, "items": items_by_order.get(o["order_id"], [])} for o in db.list_orders(customer_id)]


class NewOrderRequest(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1, le=10)


@app.get("/products")
def products(limit: int = 12) -> list[dict]:
    return db.list_products(limit)


@app.post("/orders", status_code=201)
def place_order(body: NewOrderRequest, customer_id: int = Depends(get_token_customer_id)) -> dict:
    try:
        return db.create_order(customer_id, body.product_id, body.quantity)
    except db.DatabaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@app.get("/me")
def me(customer_id: int = Depends(get_token_customer_id)) -> dict:
    customer = db.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    return customer


@app.get("/orders/{order_id}")
def order_detail(order_id: int, customer_id: int = Depends(get_token_customer_id)) -> dict:
    order = db.get_order(order_id, customer_id)
    if order is None:  # same answer for "not yours" and "does not exist" (R2)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found in your account.")
    return {**order, "items": db.get_order_items(order_id, customer_id)}


@app.get("/audit")
def audit(customer_id: int = Depends(get_token_customer_id)) -> list[dict]:
    return list(reversed(db.list_audit(customer_id, limit=50)))  # oldest first


# ---------------------------------------------------------------------------
# Chat: parse -> rules -> preview
# ---------------------------------------------------------------------------

def _reply(decision: str, facts: dict) -> str:
    return compose_reply(decision, facts, use_llm=False).text


def _answer(reply: str, trace: list[dict], change_request: Optional[dict] = None) -> dict:
    return {"reply": reply, "needs_confirmation": change_request is not None,
            "change_request": change_request, "trace": trace}


@app.post("/chat")
def chat(body: ChatRequest, customer_id: int = Depends(get_token_customer_id)) -> dict:
    start = time.perf_counter()
    trace = [{"node": "R1_verify_token", "status": "passed"}]
    customer_orders = db.list_orders(customer_id)

    result = parse_message(body.message, customer_orders, settings=_parser_settings())
    p = result.parsed
    trace.append({"node": f"parse_intent [{result.source}] -> {p.intent.value} "
                          f"({p.confidence:.2f})", "status": "passed"})

    def audit_decision(decision: str, order_id: Optional[int] = None, **extra) -> None:
        db.write_audit(action=p.intent.value, decision=decision, customer_id=customer_id,
                       order_id=order_id, fallback_used=result.fallback_used,
                       latency_ms=_ms(start), **extra)

    if p.needs_clarification:  # R11
        trace.append({"node": "R11_confidence_and_fields", "status": "needs_info"})
        audit_decision("needs_info")
        return _answer(_reply("needs_info", {"question": p.clarification_question}), trace)

    if p.intent == Intent.GENERAL_INQUIRY or (p.intent == Intent.UNKNOWN and p.confidence < 0.7):
        return _answer(_reply("general", {}), trace)

    if p.intent == Intent.UNKNOWN:  # refunds, returns, complaints (R12)
        trace.append({"node": "R12_escalate_to_human", "status": "escalated"})
        audit_decision("escalated", order_id=p.order_id if p.order_id in
                       {o["order_id"] for o in customer_orders} else None)
        return _answer(_reply("escalated", {}), trace)

    order = db.get_order(p.order_id, customer_id) if p.order_id else None
    if order is None:  # R2
        trace.append({"node": "R2_order_belongs_to_customer", "status": "failed"})
        audit_decision("blocked", rule_results=[{"rule": "R2_ownership", "passed": False}])
        return _answer("I couldn't find that order in your account.", trace)
    trace.append({"node": "R2_order_belongs_to_customer", "status": "passed"})

    if p.intent == Intent.TRACK_ORDER:
        return _answer(_reply("track", {"order_ref": order["order_ref"], "status": order["status"],
                                        "delivery_date": order["delivery_date"]}), trace)

    intent = p.intent.value
    column = _COLUMN[intent]
    proposed = {"cancel_order": {"status": "cancelled"},
                "change_address": {"shipping_address": p.new_address},
                "postpone_delivery": {"delivery_date": p.new_delivery_date.isoformat()
                                      if p.new_delivery_date else None}}[intent]

    rules = check_change(intent, order, proposed)
    trace += [{"node": r["rule"], "status": "passed" if r["passed"] else "failed"} for r in rules]
    failure = first_failure(rules)
    if failure:
        audit_decision("blocked", order_id=order["order_id"], rule_results=rules,
                       before_state={column: order[column]}, after_state=proposed)
        return _answer(_reply("blocked", {"reason": failure["reason"]}), trace)

    try:
        req = db.create_change_request(customer_id=customer_id, order_id=order["order_id"],
                                       intent=intent, proposed_change=proposed,
                                       session_id=f"api-{customer_id}", confidence=p.confidence)
    except db.PendingChangeExists as exc:  # R9: no double booking
        trace.append({"node": "R9_one_pending_change", "status": "failed"})
        audit_decision("blocked", order_id=order["order_id"],
                       rule_results=[{"rule": "R9_one_pending_change", "passed": False}])
        return _answer(_reply("blocked", {"reason": str(exc)}), trace)
    trace.append({"node": "R9_preview_saved (expires in 5 min)", "status": "passed"})

    preview = req["preview"]
    facts = {"order_ref": order["order_ref"], "field": column, "old": preview["old"], "new": preview["new"]}
    change_request = {
        "request_id": str(req["request_id"]), "idempotency_key": req["idempotency_key"],
        "order_id": order["order_ref"], "intent": intent, "expires_at": req["expires_at"],
        "preview": {"current": {column: preview["old"]}, "new": {column: preview["new"]}},
    }
    return _answer(_reply("needs_confirmation", facts), trace, change_request)


# ---------------------------------------------------------------------------
# Confirm or cancel a preview
# ---------------------------------------------------------------------------

@app.post("/confirm")
def confirm(body: ConfirmRequest, customer_id: int = Depends(get_token_customer_id)) -> dict:
    request_id = str(body.request_id)
    req = db.get_change_request(request_id, customer_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found.")
    if body.idempotency_key and body.idempotency_key != req["idempotency_key"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirmation key does not match this request.")

    if body.action == "cancel":
        outcome = db.decline_change_request(request_id, customer_id)
        if outcome["decision"] != "declined":
            raise HTTPException(status.HTTP_409_CONFLICT, outcome["reason"])
        return {"decision": "declined", "message": _reply("declined", {})}

    outcome = db.apply_change_request(request_id, customer_id, rule_check=rule_check_for_confirm)
    if outcome["decision"] != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, _reply(outcome["decision"],
                                                             {"reason": outcome["reason"]}))
    order = outcome["order"]
    column = _COLUMN[req["intent"]]
    message = _reply("approved", {"intent": req["intent"], "order_ref": order["order_ref"],
                                  "new": order[column]})
    return {"decision": "approved", "message": message, "order": order,
            "rule_results": outcome["rule_results"]}
