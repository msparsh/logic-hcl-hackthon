"""One pass test and one fail test per business rule (docs/BUSINESS_RULES.md)."""
from datetime import date, timedelta

from app.rules import (
    check_cancel,
    check_change,
    check_change_address,
    check_postpone,
    first_failure,
    rule_check_for_confirm,
)

TODAY = date(2026, 10, 27)


def order(**overrides):
    base = {"order_id": 10001, "order_ref": "ORD-10001", "status": "placed", "payment_status": "Success",
            "shipping_address": "4 Park Street, Pune", "shipping_country": "India",
            "delivery_date": TODAY + timedelta(days=4), "original_delivery_date": TODAY + timedelta(days=4)}
    return {**base, **overrides}


def failed_rules(results):
    return {r["rule"] for r in results if not r["passed"]}


def test_r3_cancel_allowed_when_placed():
    assert first_failure(check_cancel(order())) is None


def test_r3_cancel_blocked_when_shipped():
    assert failed_rules(check_cancel(order(status="shipped"))) == {"R3_cancel_only_when_placed"}


def test_r3_cancel_allowed_when_payment_failed():
    assert first_failure(check_cancel(order(payment_status="Failed"))) is None


def test_r4_address_change_allowed_when_placed():
    assert first_failure(check_change_address(order(), "12 MG Road, Pune")) is None


def test_r4_address_change_blocked_when_delivered():
    assert "R4_address_only_when_placed" in failed_rules(
        check_change_address(order(status="delivered"), "12 MG Road, Pune"))


def test_r5_address_change_blocked_when_payment_failed():
    assert "R5_payment_not_failed" in failed_rules(
        check_change_address(order(payment_status="Failed"), "12 MG Road, Pune"))


def test_r5_postpone_blocked_when_payment_failed():
    assert "R5_payment_not_failed" in failed_rules(
        check_postpone(order(payment_status="Failed"), TODAY + timedelta(days=5), TODAY))


def test_r6_short_address_blocked():
    assert "R6_valid_address" in failed_rules(check_change_address(order(), "abc"))


def test_r6_address_in_other_country_blocked():
    assert "R6_same_country" in failed_rules(
        check_change_address(order(), "1 Orchard Road, Singapore"))


def test_r6_address_in_same_country_allowed():
    assert first_failure(check_change_address(order(), "12 MG Road, Pune, India")) is None


def test_r7_same_address_blocked():
    assert "R7_value_changes" in failed_rules(check_change_address(order(), "4 park street, pune"))


def test_r7_same_delivery_date_blocked():
    assert "R7_value_changes" in failed_rules(check_postpone(order(), TODAY + timedelta(days=4), TODAY))


def test_r8_postpone_within_7_days_allowed():
    assert first_failure(check_postpone(order(), TODAY + timedelta(days=11), TODAY)) is None


def test_r8_postpone_more_than_7_days_blocked():
    assert "R8_within_7_days" in failed_rules(check_postpone(order(), TODAY + timedelta(days=12), TODAY))


def test_r8_postpone_to_past_blocked():
    late = order(delivery_date=TODAY - timedelta(days=2), original_delivery_date=TODAY - timedelta(days=2))
    assert failed_rules(check_postpone(late, TODAY - timedelta(days=1), TODAY)) == {"R8_date_after_today"}


def test_r8_postpone_earlier_than_current_blocked():
    assert "R8_later_than_current" in failed_rules(check_postpone(order(), TODAY + timedelta(days=2), TODAY))


def test_r8_postpone_blocked_when_cancelled():
    assert "R8_not_delivered_or_cancelled" in failed_rules(
        check_postpone(order(status="cancelled"), TODAY + timedelta(days=5), TODAY))


def test_r8_missing_date_blocked():
    assert "R8_valid_date" in failed_rules(check_postpone(order(), None, TODAY))


def test_unsupported_intent_is_never_allowed():
    assert first_failure(check_change("refund", order(), {})) is not None


def test_confirm_adapter_rechecks_current_row():
    request = {"intent": "cancel_order", "proposed_change": {"status": "cancelled"}}
    assert first_failure(rule_check_for_confirm(order(), request)) is None
    assert first_failure(rule_check_for_confirm(order(status="shipped"), request)) is not None
