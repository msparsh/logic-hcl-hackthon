"""Business rule checks R3-R8 (docs/BUSINESS_RULES.md).

Every function returns a list of {"rule", "passed", "reason"} dicts. A change
is allowed only if every result has passed=True.

The same checks run twice:
    1. before the preview is shown (so the customer is told "no" early), and
    2. again inside the confirm transaction, on the locked row (R10), through
       ``rule_check_for_confirm``, which is passed to db.apply_change_request.

R1 (login) is enforced by the API token, R2 (ownership) by the SQL filters in
app/db.py, R9/R10 by the database, R11/R12 by app/intent.py and the API.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

MAX_POSTPONE_DAYS = 7  # R8
MIN_ADDRESS_CHARS = 5  # R6

# Used by R6 to spot an address in a different country. Short on purpose:
# the rule is "if the text clearly names another country, block it".
KNOWN_COUNTRIES = (
    "india", "indonesia", "malaysia", "singapore", "thailand", "vietnam", "philippines",
    "china", "japan", "korea", "australia", "united states", "usa", "united kingdom", "uk",
    "canada", "germany", "france", "uae", "dubai", "pakistan", "bangladesh", "sri lanka", "nepal",
)


def _result(rule: str, passed: bool, reason: str = "") -> dict:
    return {"rule": rule, "passed": passed, "reason": "" if passed else reason}


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _mentions_other_country(address: str, country: str) -> bool:
    text = f" {address.lower().replace(',', ' ')} "
    own = (country or "").strip().lower()
    for name in KNOWN_COUNTRIES:
        if name != own and f" {name} " in text and name not in own:
            return True
    return False


def check_cancel(order: dict) -> list[dict]:
    status = order["status"]
    return [_result("R3_cancel_only_when_placed", status == "placed",
                    f"order {order['order_ref']} is already {status}, so it can't be cancelled.")]


def check_change_address(order: dict, new_address: Optional[str]) -> list[dict]:
    status = order["status"]
    address = (new_address or "").strip()
    results = [
        _result("R4_address_only_when_placed", status == "placed",
                f"order {order['order_ref']} is already {status}, so the address can't be changed."),
        _result("R5_payment_not_failed", order["payment_status"] != "Failed",
                f"the payment for order {order['order_ref']} failed, so the address can't be changed."),
        _result("R6_valid_address", len(address) >= MIN_ADDRESS_CHARS,
                "the new address is too short. Please send the full address."),
    ]
    if len(address) >= MIN_ADDRESS_CHARS:
        results.append(_result(
            "R6_same_country", not _mentions_other_country(address, order.get("shipping_country", "")),
            f"the new address must be in {order.get('shipping_country')}."))
        results.append(_result(
            "R7_value_changes", address.lower() != str(order["shipping_address"]).strip().lower(),
            "that is already the shipping address."))
    return results


def check_postpone(order: dict, new_date: Any, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    status = order["status"]
    target = _as_date(new_date)
    current = _as_date(order.get("delivery_date"))
    original = _as_date(order.get("original_delivery_date")) or current
    results = [
        _result("R8_not_delivered_or_cancelled", status not in ("delivered", "cancelled"),
                f"order {order['order_ref']} is already {status}."),
        _result("R5_payment_not_failed", order["payment_status"] != "Failed",
                f"the payment for order {order['order_ref']} failed, so delivery can't be postponed."),
    ]
    if target is None:
        results.append(_result("R8_valid_date", False, "please give the new delivery date."))
        return results
    results.append(_result("R8_date_after_today", target > today,
                           "the new delivery date must be after today."))
    if current is not None:
        results.append(_result("R7_value_changes", target != current,
                               f"the order is already due on {current.isoformat()}."))
        results.append(_result("R8_later_than_current", target >= current,
                               f"the new date must be later than the current date {current.isoformat()}."))
    if original is not None:
        limit = original + timedelta(days=MAX_POSTPONE_DAYS)
        results.append(_result("R8_within_7_days", target <= limit,
                               f"delivery can be postponed until {limit.isoformat()} at the latest."))
    return results


def check_change(intent: str, order: dict, proposed: dict, today: Optional[date] = None) -> list[dict]:
    """Run the rules for one intent. ``proposed`` uses the database column names."""
    if intent == "cancel_order":
        return check_cancel(order)
    if intent == "change_address":
        return check_change_address(order, proposed.get("shipping_address"))
    if intent == "postpone_delivery":
        return check_postpone(order, proposed.get("delivery_date"), today)
    return [_result("R12_supported_action", False, "this request can't be done automatically.")]


def first_failure(results: list[dict]) -> Optional[dict]:
    return next((r for r in results if not r["passed"]), None)


def rule_check_for_confirm(order: dict, change_request: dict) -> list[dict]:
    """Adapter for db.apply_change_request: re-check on the locked row (R10)."""
    return check_change(change_request["intent"], order, change_request.get("proposed_change") or {})
