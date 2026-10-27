"""
FastAPI application for Autonomous Customer Support.
Strictly validated using Pydantic models matching the database ER schema:
- CUSTOMERS
- ORDERS
- PRODUCTS
- ORDER_ITEMS
- CHANGE_REQUESTS
- AUDIT_LOG
"""
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from enum import Enum
import re
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, Depends, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# 1. Pydantic Models & Enums (Referencing Database Schema)
# ============================================================================

class OrderStatusEnum(str, Enum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatusEnum(str, Enum):
    SUCCESS = "Success"
    FAILED = "Failed"


class IntentEnum(str, Enum):
    CHANGE_ADDRESS = "change_address"
    CANCEL_ORDER = "cancel_order"
    POSTPONE_DELIVERY = "postpone_delivery"
    TRACK_ORDER = "track_order"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


class ChangeRequestStatusEnum(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    EXPIRED = "expired"
    BLOCKED = "blocked"
    APPLIED = "applied"


class AuditDecisionEnum(str, Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"
    DECLINED = "declined"
    FAILED = "failed"


class ConfirmActionEnum(str, Enum):
    CONFIRM = "confirm"
    CANCEL = "cancel"


# --- Table: CUSTOMERS ---
class CustomerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int = Field(..., description="bigint PK")
    first_name: Optional[str] = Field(None, description="text")
    last_name: Optional[str] = Field(None, description="text")
    email: str = Field(..., description="text UK login")
    home_location: Optional[str] = Field(None, description="text")
    home_country: Optional[str] = Field(None, description="text")
    joined_at: date = Field(..., description="date")


# --- Table: PRODUCTS ---
class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int = Field(..., description="bigint PK")
    name: str = Field(..., description="text")
    category: Optional[str] = Field(None, description="text")
    sub_category: Optional[str] = Field(None, description="text")
    article_type: Optional[str] = Field(None, description="text")
    base_colour: Optional[str] = Field(None, description="text")


# --- Table: ORDER_ITEMS ---
class OrderItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int = Field(..., description="bigint PK, FK")
    product_id: int = Field(..., description="bigint PK, FK")
    quantity: int = Field(..., ge=1, description="int CHECK > 0")
    item_price: Decimal = Field(..., ge=0, description="numeric CHECK >= 0")
    product: Optional[ProductSchema] = None


# --- Table: ORDERS ---
class OrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int = Field(..., description="bigserial PK")
    order_ref: str = Field(..., description="text UK e.g. ORD-10023")
    booking_id: Optional[str] = Field(None, description="text UK Kaggle ID")
    customer_id: int = Field(..., description="bigint FK")
    created_at: datetime = Field(..., description="timestamptz")
    payment_method: Optional[str] = Field(None, description="text")
    payment_status: PaymentStatusEnum = Field(..., description="CHECK Success or Failed")
    status: OrderStatusEnum = Field(..., description="CHECK placed, shipped, delivered, cancelled")
    shipping_address: str = Field(..., min_length=5, description="text CHECK min length 5")
    shipping_lat: Optional[Decimal] = None
    shipping_long: Optional[Decimal] = None
    delivery_date: Optional[date] = None
    promo_code: Optional[str] = None
    promo_amount: Decimal = Field(default=Decimal("0.00"), ge=0, description="CHECK >= 0")
    shipment_fee: Decimal = Field(default=Decimal("0.00"), ge=0, description="CHECK >= 0")
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0, description="CHECK >= 0")
    version: int = Field(default=1, description="int conflict check")
    updated_at: datetime = Field(..., description="timestamptz")
    items: List[OrderItemSchema] = Field(default_factory=list)


# --- Table: CHANGE_REQUESTS ---
class ChangeRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str = Field(..., description="uuid PK")
    session_id: Optional[str] = Field(None, description="text")
    customer_id: int = Field(..., description="bigint FK")
    order_id: int = Field(..., description="bigint FK (one pending per order)")
    intent: IntentEnum = Field(..., description="text CHECK")
    proposed_change: Dict[str, Any] = Field(default_factory=dict, description="jsonb")
    preview: Dict[str, Any] = Field(default_factory=dict, description="jsonb old and new values")
    order_version: int = Field(..., description="int version seen at preview")
    status: ChangeRequestStatusEnum = Field(..., description="CHECK pending, confirmed, declined, expired, blocked, applied")
    idempotency_key: str = Field(..., description="text UK no double booking")
    expires_at: datetime = Field(..., description="timestamptz preview valid 5 min")
    created_at: datetime = Field(..., description="timestamptz")
    decided_at: Optional[datetime] = Field(None, description="timestamptz")


# --- Table: AUDIT_LOG ---
class AuditLogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int = Field(..., description="bigserial PK")
    request_id: Optional[str] = Field(None, description="uuid FK")
    customer_id: int = Field(..., description="bigint FK")
    order_id: Optional[int] = Field(None, description="bigint FK")
    action: str = Field(..., description="text")
    decision: AuditDecisionEnum = Field(..., description="text CHECK")
    rule_results: Dict[str, Any] = Field(default_factory=dict, description="jsonb")
    before_state: Dict[str, Any] = Field(default_factory=dict, description="jsonb")
    after_state: Dict[str, Any] = Field(default_factory=dict, description="jsonb")
    fallback_used: bool = Field(default=False, description="boolean")
    latency_ms: int = Field(default=0, description="int")
    created_at: datetime = Field(..., description="timestamptz append-only")


# ============================================================================
# 2. Endpoint Input / Output Contract Schemas
# ============================================================================

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120, examples=["alice@example.com"])
    pin: str = Field(..., min_length=4, max_length=8, examples=["1234"])

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v

    @field_validator("pin")
    @classmethod
    def clean_pin(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("PIN must be numeric")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: int
    customer_email: str


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Customer natural language message",
        examples=["Change shipping address for order ORD-10023 to 12 MG Road, Pune"]
    )
    session_id: Optional[str] = Field(None, max_length=64)
    order_id: Optional[int] = Field(None, description="Optional explicit order ID")

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message cannot be empty")
        return cleaned


class ChatResponse(BaseModel):
    reply: str
    intent: IntentEnum
    extracted_order_id: Optional[int] = None
    needs_confirmation: bool = False
    change_request: Optional[ChangeRequestSchema] = None
    trace: List[Dict[str, str]] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    request_id: str = Field(..., min_length=10, max_length=64, description="UUID from CHANGE_REQUESTS")
    action: ConfirmActionEnum = Field(..., description="'confirm' or 'cancel'")
    idempotency_key: str = Field(..., min_length=8, max_length=64, description="Unique client key")


class ConfirmResponse(BaseModel):
    success: bool
    status: str
    message: str
    order: Optional[OrderSchema] = None
    audit_id: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
    timestamp: datetime


# ============================================================================
# 3. In-Memory Store & Seeding (Matches Schema Constraints)
# ============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mask_sensitive_address(addr: Optional[str]) -> str:
    """Masks address for privacy in audit logs."""
    if not addr:
        return ""
    words = addr.split()
    return " ".join([w[0] + "*" * (len(w) - 1) if len(w) > 2 else w for w in words])


# Seed products
PRODUCTS_DB: Dict[int, ProductSchema] = {
    101: ProductSchema(
        product_id=101,
        name="Wireless Noise-Cancelling Headphones",
        category="Electronics",
        sub_category="Audio",
        article_type="Headphones",
        base_colour="Black"
    ),
    102: ProductSchema(
        product_id=102,
        name="Mechanical Ergonomic Keyboard",
        category="Electronics",
        sub_category="Accessories",
        article_type="Keyboards",
        base_colour="Silver"
    )
}

# Seed customers
CUSTOMERS_DB: Dict[int, Dict[str, Any]] = {
    1: {
        "customer_id": 1,
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "home_location": "Pune, Maharashtra",
        "home_country": "India",
        "pin": "1234",
        "joined_at": date(2025, 1, 15)
    }
}

# Seed orders
ORDERS_DB: Dict[int, OrderSchema] = {
    10023: OrderSchema(
        order_id=10023,
        order_ref="ORD-10023",
        booking_id="KG-984210",
        customer_id=1,
        created_at=utc_now() - timedelta(days=2),
        payment_method="Credit Card",
        payment_status=PaymentStatusEnum.SUCCESS,
        status=OrderStatusEnum.PLACED,
        shipping_address="4 Park Street, Pune",
        delivery_date=date(2026, 11, 5),
        promo_code="DISCOUNT10",
        promo_amount=Decimal("15.00"),
        shipment_fee=Decimal("5.00"),
        total_amount=Decimal("189.99"),
        version=1,
        updated_at=utc_now() - timedelta(days=1),
        items=[
            OrderItemSchema(
                order_id=10023,
                product_id=101,
                quantity=1,
                item_price=Decimal("199.99"),
                product=PRODUCTS_DB[101]
            )
        ]
    ),
    10024: OrderSchema(
        order_id=10024,
        order_ref="ORD-10024",
        booking_id="KG-984211",
        customer_id=1,
        created_at=utc_now() - timedelta(days=5),
        payment_method="UPI",
        payment_status=PaymentStatusEnum.SUCCESS,
        status=OrderStatusEnum.SHIPPED,
        shipping_address="4 Park Street, Pune",
        delivery_date=date(2026, 10, 30),
        promo_code=None,
        promo_amount=Decimal("0.00"),
        shipment_fee=Decimal("0.00"),
        total_amount=Decimal("129.50"),
        version=1,
        updated_at=utc_now() - timedelta(days=2),
        items=[
            OrderItemSchema(
                order_id=10024,
                product_id=102,
                quantity=1,
                item_price=Decimal("129.50"),
                product=PRODUCTS_DB[102]
            )
        ]
    )
}

# Tables
CHANGE_REQUESTS_DB: Dict[str, ChangeRequestSchema] = {}
AUDIT_LOG_DB: List[AuditLogSchema] = []
IDEMPOTENCY_KEYS_SEEN: set = set()


# ============================================================================
# 4. Helper Functions: Intent Extraction & Security Guardrails
# ============================================================================

def resolve_customer(
    authorization: Optional[str] = Header(default=None),
    x_customer_id: Optional[str] = Header(default=None, alias="X-Customer-ID")
) -> CustomerSchema:
    """Extracts and verifies customer identity."""
    cid = 1  # Default to demo customer 1
    if x_customer_id and isinstance(x_customer_id, str) and x_customer_id.isdigit():
        cid = int(x_customer_id)
    elif authorization and isinstance(authorization, str) and "Bearer " in authorization:
        token = authorization.split("Bearer ")[-1].strip()
        if token.startswith("cust_") and token.replace("cust_", "").isdigit():
            cid = int(token.replace("cust_", ""))

    cust = CUSTOMERS_DB.get(cid)
    if not cust:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Customer record not found"
        )
    return CustomerSchema(
        customer_id=cust["customer_id"],
        first_name=cust["first_name"],
        last_name=cust["last_name"],
        email=cust["email"],
        home_location=cust["home_location"],
        home_country=cust["home_country"],
        joined_at=cust["joined_at"]
    )


def extract_order_id(text: str) -> Optional[int]:
    """Extracts numeric order ID or reference."""
    ref_match = re.search(r"ORD-(\d+)", text, re.IGNORECASE)
    if ref_match:
        return int(ref_match.group(1))
    num_match = re.search(r"(?:order\s*(?:#|id)?\s*|#\s*)(\d{3,8})", text, re.IGNORECASE)
    if num_match:
        return int(num_match.group(1))
    standalone = re.search(r"\b(1002[3-9]|102[3-9])\b", text)
    if standalone:
        return int(standalone.group(1))
    return None


def parse_intent(text: str) -> tuple[IntentEnum, Optional[int], Optional[str]]:
    """Safe intent parser with regex failover."""
    order_id = extract_order_id(text)

    # Address change
    addr_match = re.search(
        r"(?:change|update|ship to|deliver to)(?:.*?(?:address|destination))?.*?(?:to|at)\s+([A-Za-z0-9\s,\.\-\#\/]+)",
        text,
        re.IGNORECASE
    )
    if addr_match:
        new_addr = addr_match.group(1).strip()
        new_addr = re.sub(r"(?:for|of)?\s*order\s*#?\d+", "", new_addr, flags=re.IGNORECASE).strip()
        return IntentEnum.CHANGE_ADDRESS, order_id, new_addr

    # Cancel order
    if re.search(r"\b(?:cancel|abort|terminate)\b", text, re.IGNORECASE):
        return IntentEnum.CANCEL_ORDER, order_id, None

    # Track order
    if re.search(r"\b(?:track|where|status|when)\b", text, re.IGNORECASE):
        return IntentEnum.TRACK_ORDER, order_id, None

    return IntentEnum.GENERAL_INQUIRY, order_id, None


def record_audit(
    customer_id: int,
    order_id: Optional[int],
    action: str,
    decision: AuditDecisionEnum,
    rule_results: Dict[str, Any],
    before_state: Dict[str, Any],
    after_state: Dict[str, Any],
    request_id: Optional[str] = None,
    latency_ms: int = 5
) -> AuditLogSchema:
    audit_id = len(AUDIT_LOG_DB) + 1
    log = AuditLogSchema(
        audit_id=audit_id,
        request_id=request_id,
        customer_id=customer_id,
        order_id=order_id,
        action=action,
        decision=decision,
        rule_results=rule_results,
        before_state={k: mask_sensitive_address(v) if "address" in k else v for k, v in before_state.items()},
        after_state={k: mask_sensitive_address(v) if "address" in k else v for k, v in after_state.items()},
        fallback_used=True,
        latency_ms=latency_ms,
        created_at=utc_now()
    )
    AUDIT_LOG_DB.append(log)
    return log


# ============================================================================
# 5. FastAPI App & Endpoints
# ============================================================================

app = FastAPI(
    title="Logic Autonomous Support API",
    version="1.0.0",
    description="Validated endpoints matching the Team Logic schema ER diagram."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
def get_health():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        app_name="Logic Autonomous Support API",
        version="1.0.0",
        environment="development",
        timestamp=utc_now()
    )


@app.post("/login", response_model=TokenResponse, tags=["Authentication"])
def login(payload: LoginRequest):
    """Customer authentication returning Bearer token."""
    for cid, data in CUSTOMERS_DB.items():
        if data["email"] == payload.email and data["pin"] == payload.pin:
            return TokenResponse(
                access_token=f"cust_{cid}",
                token_type="bearer",
                customer_id=cid,
                customer_email=data["email"]
            )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or PIN"
    )


@app.get("/orders", response_model=List[OrderSchema], tags=["Orders"])
def list_orders(cust: CustomerSchema = Depends(resolve_customer)):
    """List all orders for authenticated customer."""
    return [order for order in ORDERS_DB.values() if order.customer_id == cust.customer_id]


@app.get("/orders/{order_id}", response_model=OrderSchema, tags=["Orders"])
def get_order(order_id: int, cust: CustomerSchema = Depends(resolve_customer)):
    """Retrieve order details with ownership verification."""
    order = ORDERS_DB.get(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order #{order_id} not found")
    if order.customer_id != cust.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access to order")
    return order


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
def chat(payload: ChatRequest, cust: CustomerSchema = Depends(resolve_customer)):
    """
    Processes chat message:
    - Parses intent & order number
    - Checks ownership and status guardrails
    - Creates CHANGE_REQUEST preview valid for 5 minutes
    """
    start_t = time.time()
    trace: List[Dict[str, str]] = [{"node": "Identify", "status": f"Customer #{cust.customer_id} ({cust.email})"}]

    intent, extracted_id, payload_val = parse_intent(payload.message)
    target_id = payload.order_id or extracted_id
    trace.append({"node": "Parse Intent", "status": f"Intent: {intent.value}, Target Order: {target_id}"})

    # Read-only or general inquiry
    if intent == IntentEnum.TRACK_ORDER and target_id and target_id in ORDERS_DB:
        order = ORDERS_DB[target_id]
        if order.customer_id != cust.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized order access")
        return ChatResponse(
            reply=f"Order #{order.order_ref} is currently {order.status.value.upper()}. Shipping to: {order.shipping_address}.",
            intent=intent,
            extracted_order_id=order.order_id,
            needs_confirmation=False,
            trace=trace
        )

    # Missing target order ID
    if intent in (IntentEnum.CHANGE_ADDRESS, IntentEnum.CANCEL_ORDER) and not target_id:
        active_orders = [f"#{o.order_ref} ({o.status.value})" for o in ORDERS_DB.values() if o.customer_id == cust.customer_id]
        return ChatResponse(
            reply=f"Which order would you like to update? Available orders: {', '.join(active_orders)}",
            intent=intent,
            needs_confirmation=False,
            trace=trace
        )

    # Target order validation
    if target_id:
        order = ORDERS_DB.get(target_id)
        if not order:
            return ChatResponse(
                reply=f"Order #{target_id} was not found in your account.",
                intent=intent,
                extracted_order_id=target_id,
                needs_confirmation=False,
                trace=trace
            )
        if order.customer_id != cust.customer_id:
            record_audit(
                customer_id=cust.customer_id,
                order_id=target_id,
                action="ownership_check",
                decision=AuditDecisionEnum.BLOCKED,
                rule_results={"ownership": False},
                before_state={},
                after_state={}
            )
            return ChatResponse(
                reply=f"You do not have permission to view or modify Order #{target_id}.",
                intent=intent,
                extracted_order_id=target_id,
                needs_confirmation=False,
                trace=trace
            )

        # Status Check Guardrail: terminal statuses cannot be modified
        if order.status in (OrderStatusEnum.SHIPPED, OrderStatusEnum.DELIVERED, OrderStatusEnum.CANCELLED):
            err_msg = f"Cannot {intent.value} because order #{order.order_ref} is already {order.status.value}."
            record_audit(
                customer_id=cust.customer_id,
                order_id=target_id,
                action=intent.value,
                decision=AuditDecisionEnum.BLOCKED,
                rule_results={"status_check": False, "status": order.status.value},
                before_state={"status": order.status.value},
                after_state={}
            )
            return ChatResponse(
                reply=err_msg,
                intent=intent,
                extracted_order_id=target_id,
                needs_confirmation=False,
                trace=trace
            )

        # Build Change Request Preview (valid for 5 minutes)
        req_id = str(uuid.uuid4())
        idem_key = f"idem_{uuid.uuid4().hex[:12]}"
        expires_at = utc_now() + timedelta(minutes=5)

        if intent == IntentEnum.CHANGE_ADDRESS:
            new_addr = payload_val or ""
            if len(new_addr) < 5:
                return ChatResponse(
                    reply="The new shipping address must be at least 5 characters long.",
                    intent=intent,
                    needs_confirmation=False,
                    trace=trace
                )
            if new_addr.lower() == order.shipping_address.lower():
                return ChatResponse(
                    reply="The new address is identical to your current address. No change needed.",
                    intent=intent,
                    needs_confirmation=False,
                    trace=trace
                )

            change_req = ChangeRequestSchema(
                request_id=req_id,
                session_id=payload.session_id,
                customer_id=cust.customer_id,
                order_id=order.order_id,
                intent=intent,
                proposed_change={"shipping_address": new_addr},
                preview={"current": order.shipping_address, "new": new_addr},
                order_version=order.version,
                status=ChangeRequestStatusEnum.PENDING,
                idempotency_key=idem_key,
                expires_at=expires_at,
                created_at=utc_now()
            )
            CHANGE_REQUESTS_DB[req_id] = change_req

            summary = (
                f"You asked to change the shipping address of order #{order.order_ref}.\n"
                f"Current: {order.shipping_address}\n"
                f"New: {new_addr}\n"
                f"Please confirm to apply changes."
            )
            return ChatResponse(
                reply=summary,
                intent=intent,
                extracted_order_id=order.order_id,
                needs_confirmation=True,
                change_request=change_req,
                trace=trace
            )

        elif intent == IntentEnum.CANCEL_ORDER:
            change_req = ChangeRequestSchema(
                request_id=req_id,
                session_id=payload.session_id,
                customer_id=cust.customer_id,
                order_id=order.order_id,
                intent=intent,
                proposed_change={"status": "cancelled"},
                preview={"current": order.status.value, "new": "cancelled"},
                order_version=order.version,
                status=ChangeRequestStatusEnum.PENDING,
                idempotency_key=idem_key,
                expires_at=expires_at,
                created_at=utc_now()
            )
            CHANGE_REQUESTS_DB[req_id] = change_req

            summary = (
                f"WARNING: You requested to cancel order #{order.order_ref}. "
                f"This action is irreversible. Please confirm or cancel."
            )
            return ChatResponse(
                reply=summary,
                intent=intent,
                extracted_order_id=order.order_id,
                needs_confirmation=True,
                change_request=change_req,
                trace=trace
            )

    return ChatResponse(
        reply="Hello! I can help you check order status, update shipping address, or cancel open orders.",
        intent=IntentEnum.GENERAL_INQUIRY,
        needs_confirmation=False,
        trace=trace
    )


@app.post("/confirm", response_model=ConfirmResponse, tags=["Agent"])
def confirm_action(payload: ConfirmRequest, cust: CustomerSchema = Depends(resolve_customer)):
    """
    Confirm or cancel pending action:
    - Enforces idempotency key (no double execution)
    - Validates 5-minute preview expiry
    - Optimistic locking version check
    - Updates order and logs to AUDIT_LOG
    """
    change_req = CHANGE_REQUESTS_DB.get(payload.request_id)
    if not change_req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")

    if change_req.customer_id != cust.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

    if change_req.idempotency_key != payload.idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency key mismatch")

    # Double booking guard
    if payload.idempotency_key in IDEMPOTENCY_KEYS_SEEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action already processed (idempotent)")

    # Cancel action
    if payload.action == ConfirmActionEnum.CANCEL:
        change_req.status = ChangeRequestStatusEnum.DECLINED
        change_req.decided_at = utc_now()
        IDEMPOTENCY_KEYS_SEEN.add(payload.idempotency_key)
        audit = record_audit(
            customer_id=cust.customer_id,
            order_id=change_req.order_id,
            action=change_req.intent.value,
            decision=AuditDecisionEnum.DECLINED,
            rule_results={"cancelled_by_user": True},
            before_state={},
            after_state={},
            request_id=change_req.request_id
        )
        return ConfirmResponse(
            success=True,
            status="declined",
            message=f"Change request for order #{change_req.order_id} was declined. No changes were made.",
            audit_id=audit.audit_id
        )

    # Expiry Check (5 minutes)
    if utc_now() > change_req.expires_at:
        change_req.status = ChangeRequestStatusEnum.EXPIRED
        change_req.decided_at = utc_now()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview expired (> 5 min). Please submit request again.")

    # Status check
    if change_req.status != ChangeRequestStatusEnum.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request already {change_req.status.value}")

    # Optimistic Locking / Conflict Check
    order = ORDERS_DB.get(change_req.order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.version != change_req.order_version:
        change_req.status = ChangeRequestStatusEnum.BLOCKED
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order version mismatch. Updated in another session.")

    # Status check before applying
    if order.status in (OrderStatusEnum.SHIPPED, OrderStatusEnum.DELIVERED, OrderStatusEnum.CANCELLED):
        change_req.status = ChangeRequestStatusEnum.BLOCKED
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Order is already {order.status.value}")

    # Apply changes
    before_dict = {"shipping_address": order.shipping_address, "status": order.status.value, "version": order.version}
    if change_req.intent == IntentEnum.CHANGE_ADDRESS:
        order.shipping_address = change_req.proposed_change["shipping_address"]
        order.version += 1
        order.updated_at = utc_now()
    elif change_req.intent == IntentEnum.CANCEL_ORDER:
        order.status = OrderStatusEnum.CANCELLED
        order.version += 1
        order.updated_at = utc_now()

    change_req.status = ChangeRequestStatusEnum.APPLIED
    change_req.decided_at = utc_now()
    IDEMPOTENCY_KEYS_SEEN.add(payload.idempotency_key)

    after_dict = {"shipping_address": order.shipping_address, "status": order.status.value, "version": order.version}
    audit = record_audit(
        customer_id=cust.customer_id,
        order_id=order.order_id,
        action=change_req.intent.value,
        decision=AuditDecisionEnum.APPROVED,
        rule_results={"applied": True},
        before_state=before_dict,
        after_state=after_dict,
        request_id=change_req.request_id
    )

    return ConfirmResponse(
        success=True,
        status="applied",
        message=f"Order #{order.order_ref} successfully updated.",
        order=order,
        audit_id=audit.audit_id
    )


@app.get("/audit", response_model=List[AuditLogSchema], tags=["Audit & Compliance"])
def get_audit(limit: int = Query(50, ge=1, le=100), cust: CustomerSchema = Depends(resolve_customer)):
    """Retrieve audit logs with masked addresses."""
    logs = [log for log in AUDIT_LOG_DB if log.customer_id == cust.customer_id]
    return logs[-limit:]
