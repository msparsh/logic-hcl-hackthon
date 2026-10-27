"""
Business-rule guardrails.

Every rule in docs/BUSINESS_RULES.md that can be checked in code has one
function here, named after its rule ID. Each function is pure: it receives the
facts it needs and returns a `RuleResult`. Nothing in this module reads from or
writes to the store, so every rule can be unit-tested in isolation.

The agent runs `evaluate_change()` twice for every change:
  1. before the preview is shown to the customer, and
  2. again at confirmation, while the order is locked (R10).
If any result has `passed=False`, the change is not written.
"""
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.models import (
    ChangeRequestSchema,
    ChangeRequestStatusEnum,
    IntentEnum,
    OrderSchema,
    OrderStatusEnum,
    PaymentStatusEnum,
    WRITE_INTENTS,
)
from app.parser import MIN_CONFIDENCE, ParsedRequest

PREVIEW_TTL = timedelta(minutes=5)          # R9
MAX_POSTPONE_DAYS = 7                       # R8
MAX_APPLIED_CHANGES_PER_ORDER = 3           # R17
ADDRESS_MIN_LENGTH, ADDRESS_MAX_LENGTH = 5, 200   # R6

# Letters (any script), digits, spaces and common address punctuation only.
# Characters used by markup, code or URLs (< > { } : ; = " ` \ etc.) are rejected.
_ADDRESS_ALLOWED = re.compile(r"^[\w\s,.\-#/'()&]+$", re.UNICODE)
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    passed: bool
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _ok(rule_id: str, name: str) -> RuleResult:
    return RuleResult(rule_id, name, True)


def _fail(rule_id: str, name: str, reason: str) -> RuleResult:
    return RuleResult(rule_id, name, False, reason)


def results_to_dict(results: List[RuleResult]) -> Dict[str, Dict[str, Any]]:
    """Format results for the audit log, keyed by rule ID."""
    return {r.rule_id: {"name": r.name, "passed": r.passed, "reason": r.reason} for r in results}


def first_failure(results: List[RuleResult]) -> Optional[RuleResult]:
    return next((r for r in results if not r.passed), None)


# ----------------------------------------------------------------------------
# Request-level rules (run before an order is looked up)
# ----------------------------------------------------------------------------

def check_r11_parse_is_certain(parsed: ParsedRequest) -> RuleResult:
    """R11: low confidence or a missing required field means ask, never act."""
    name = "parse_is_certain"
    if parsed.confidence < MIN_CONFIDENCE:
        return _fail("R11", name, "I'm not sure I understood. Could you rephrase your request?")
    if parsed.intent in WRITE_INTENTS or parsed.intent == IntentEnum.TRACK_ORDER:
        if parsed.order_id is None:
            return _fail("R11", name, "Which order do you mean? Please share the order number, e.g. ORD-10001.")
    if parsed.intent == IntentEnum.CHANGE_ADDRESS and not parsed.new_address:
        return _fail("R11", name, "What is the new shipping address?")
    if parsed.intent == IntentEnum.POSTPONE_DELIVERY and parsed.new_delivery_date is None:
        return _fail("R11", name, "Which date would you like the delivery moved to? (for example 2026-11-05)")
    return _ok("R11", name)


def check_r16_single_order(parsed: ParsedRequest) -> RuleResult:
    """R16: one order per request, so each change gets its own preview and confirmation."""
    if len(parsed.order_ids_mentioned) > 1:
        refs = ", ".join(f"ORD-{oid}" for oid in parsed.order_ids_mentioned)
        return _fail("R16", "single_order",
                     f"Your message mentions several orders ({refs}). Let's handle them one at a time: "
                     "please send a separate message for each order.")
    return _ok("R16", "single_order")


# ----------------------------------------------------------------------------
# Order-level rules
# ----------------------------------------------------------------------------

def check_r2_ownership(order: Optional[OrderSchema], customer_id: int, order_id: Optional[int]) -> RuleResult:
    """
    R2: the order must exist and belong to the logged-in customer.
    The message is the same in both failure cases so order IDs cannot be probed.
    """
    if order is None or order.customer_id != customer_id:
        ref = f"ORD-{order_id}" if order_id else "that order"
        return _fail("R2", "ownership", f"I couldn't find {ref} in your account.")
    return _ok("R2", "ownership")


def check_r3_cancel_allowed(order: OrderSchema) -> RuleResult:
    """R3: an order can be cancelled only while its status is 'placed'."""
    if order.status != OrderStatusEnum.PLACED:
        return _fail("R3", "cancel_only_when_placed",
                     f"Order {order.order_ref} cannot be cancelled because it is already {order.status.value}.")
    return _ok("R3", "cancel_only_when_placed")


def check_r4_address_change_allowed(order: OrderSchema) -> RuleResult:
    """R4: the shipping address can be changed only while the status is 'placed'."""
    if order.status != OrderStatusEnum.PLACED:
        return _fail("R4", "address_change_only_when_placed",
                     f"The address of order {order.order_ref} cannot be changed because it is already "
                     f"{order.status.value}.")
    return _ok("R4", "address_change_only_when_placed")


def check_r5_payment_ok(order: OrderSchema, intent: IntentEnum) -> RuleResult:
    """R5: failed payment blocks address changes and postponements; cancelling stays allowed."""
    if intent in (IntentEnum.CHANGE_ADDRESS, IntentEnum.POSTPONE_DELIVERY) \
            and order.payment_status == PaymentStatusEnum.FAILED:
        return _fail("R5", "payment_not_failed",
                     f"The payment for order {order.order_ref} failed, so it cannot be changed. "
                     "You can still cancel it.")
    return _ok("R5", "payment_not_failed")


def check_r6_valid_address(new_address: Optional[str]) -> RuleResult:
    """
    R6: the new address must be 5-200 characters, contain at least one letter, use only
    address characters, and include a house number or at least two comma-separated parts.
    The country cannot be changed by the agent: only the street address is editable, and
    shipping_country stays as it is.
    """
    name = "valid_address"
    value = (new_address or "").strip()
    if len(value) < ADDRESS_MIN_LENGTH:
        return _fail("R6", name, "Please provide a complete address (at least 5 characters).")
    if len(value) > ADDRESS_MAX_LENGTH:
        return _fail("R6", name, f"The address is too long (maximum {ADDRESS_MAX_LENGTH} characters).")
    if not _HAS_LETTER.search(value) or not _ADDRESS_ALLOWED.match(value):
        return _fail("R6", name, "The address contains characters that are not allowed. "
                                 "Please use letters, numbers and , . - # / ' ( ) & only.")
    # A deliverable address has a house/flat number or at least two comma-separated parts
    # (e.g. "12 MG Road, Pune"). Vague phrases such as "my new flat" are sent back for detail.
    if not any(ch.isdigit() for ch in value) and "," not in value:
        return _fail("R6", name, "Please give the full address, including the house or flat number and the city.")
    return _ok("R6", name)


def check_r7_value_changes(order: OrderSchema, intent: IntentEnum, proposed: Dict[str, Any]) -> RuleResult:
    """R7: if the new value equals the current value, nothing is changed."""
    name = "value_changes"
    if intent == IntentEnum.CHANGE_ADDRESS:
        current = " ".join(order.shipping_address.lower().split())
        new = " ".join(str(proposed.get("shipping_address", "")).lower().split())
        if current == new:
            return _fail("R7", name, "That is already the shipping address for this order. No change is needed.")
    if intent == IntentEnum.POSTPONE_DELIVERY and proposed.get("delivery_date") == order.delivery_date:
        return _fail("R7", name, "The delivery is already scheduled for that date. No change is needed.")
    return _ok("R7", name)


def check_r8_postpone_allowed(order: OrderSchema, new_date: Optional[date], today: date) -> RuleResult:
    """
    R8: delivery can be postponed only if the order is not delivered or cancelled; the new
    date must be after today, later than the current date, and at most 7 days after
    original_delivery_date.
    """
    name = "postpone_window"
    if order.status in (OrderStatusEnum.DELIVERED, OrderStatusEnum.CANCELLED):
        return _fail("R8", name, f"Order {order.order_ref} is already {order.status.value}, "
                                 "so the delivery cannot be postponed.")
    if new_date is None:
        return _fail("R8", name, "Please give the new delivery date.")
    if new_date <= today:
        return _fail("R8", name, "The new delivery date must be in the future.")
    if order.delivery_date and new_date < order.delivery_date:
        return _fail("R8", name, "Deliveries can only be moved later, not earlier.")
    baseline = order.original_delivery_date or order.delivery_date
    if baseline and new_date > baseline + timedelta(days=MAX_POSTPONE_DAYS):
        latest = baseline + timedelta(days=MAX_POSTPONE_DAYS)
        return _fail("R8", name, f"Delivery can be postponed by at most {MAX_POSTPONE_DAYS} days "
                                 f"(latest {latest.isoformat()}).")
    return _ok("R8", name)


def check_r17_change_limit(applied_changes: int) -> RuleResult:
    """R17: at most 3 applied changes per order, to limit abuse."""
    if applied_changes >= MAX_APPLIED_CHANGES_PER_ORDER:
        return _fail("R17", "change_limit",
                     "This order has reached the maximum number of changes. "
                     "Please contact a support agent for further help.")
    return _ok("R17", "change_limit")


def check_r19_writes_enabled(read_only_mode: bool) -> RuleResult:
    """R19: the read-only switch blocks every write."""
    if read_only_mode:
        return _fail("R19", "writes_enabled",
                     "Order changes are temporarily unavailable. Please try again later.")
    return _ok("R19", "writes_enabled")


# ----------------------------------------------------------------------------
# Confirmation-time rules
# ----------------------------------------------------------------------------

def check_r9_preview_not_expired(change: ChangeRequestSchema, now: datetime) -> RuleResult:
    """R9: a preview is valid for 5 minutes after it is shown."""
    if now > change.expires_at:
        return _fail("R9", "preview_not_expired",
                     "This confirmation has expired (older than 5 minutes). Please send your request again.")
    return _ok("R9", "preview_not_expired")


def check_r10_version_matches(order: OrderSchema, change: ChangeRequestSchema) -> RuleResult:
    """R10: the order must not have changed since the preview was shown."""
    if order.version != change.order_version:
        return _fail("R10", "no_conflicting_update",
                     "This order was updated after the preview was shown. Please review it and try again.")
    return _ok("R10", "no_conflicting_update")


def check_r14_confirmation_binding(change: Optional[ChangeRequestSchema], customer_id: int,
                                   idempotency_key: str) -> RuleResult:
    """
    R14: a confirmation is accepted only for a pending preview that belongs to the
    logged-in customer and carries the idempotency key issued with that preview.
    """
    name = "confirmation_binding"
    if change is None or change.customer_id != customer_id:
        return _fail("R14", name, "Change request not found.")
    if change.idempotency_key != idempotency_key:
        return _fail("R14", name, "This confirmation does not match the preview that was shown.")
    if change.status != ChangeRequestStatusEnum.PENDING:
        return _fail("R14", name, f"This request has already been {change.status.value}.")
    return _ok("R14", name)


# ----------------------------------------------------------------------------
# Rule sets per intent
# ----------------------------------------------------------------------------

def evaluate_change(*, intent: IntentEnum, order: OrderSchema, proposed: Dict[str, Any],
                    today: date, applied_changes: int, read_only_mode: bool) -> List[RuleResult]:
    """
    Run every order-level rule that applies to the intent and return all results.
    Ownership (R2) is checked by the caller before this function is used.
    """
    results = [check_r19_writes_enabled(read_only_mode)]
    if intent == IntentEnum.CANCEL_ORDER:
        results.append(check_r3_cancel_allowed(order))
    elif intent == IntentEnum.CHANGE_ADDRESS:
        results += [
            check_r4_address_change_allowed(order),
            check_r5_payment_ok(order, intent),
            check_r6_valid_address(proposed.get("shipping_address")),
            check_r7_value_changes(order, intent, proposed),
        ]
    elif intent == IntentEnum.POSTPONE_DELIVERY:
        results += [
            check_r5_payment_ok(order, intent),
            check_r8_postpone_allowed(order, proposed.get("delivery_date"), today),
            check_r7_value_changes(order, intent, proposed),
        ]
    else:
        results.append(_fail("R12", "supported_intent", "This request is not supported."))
    results.append(check_r17_change_limit(applied_changes))
    return results
