"""
Unit tests for app/guardrails.py: one passing and one failing case per rule.
Test names start with the rule ID from docs/BUSINESS_RULES.md.
"""
from datetime import date, timedelta

from app import guardrails as g
from app import store
from app.models import (
    ChangeRequestStatusEnum,
    IntentEnum,
    OrderStatusEnum,
    PaymentStatusEnum,
)
from app.parser import ParsedRequest

TODAY = date(2026, 10, 27)
PLACED, SHIPPED, DELIVERED, CANCELLED, PAYMENT_FAILED, BOBS = 10001, 10002, 10003, 10004, 10005, 10006


def order(order_id):
    return store.ORDERS[order_id]


def parsed(**fields):
    defaults = {"intent": IntentEnum.CANCEL_ORDER, "order_id": PLACED, "confidence": 0.9}
    defaults.update(fields)
    return ParsedRequest(**defaults)


# R2 ownership -----------------------------------------------------------------

def test_r2_owner_passes():
    assert g.check_r2_ownership(order(PLACED), 1, PLACED).passed


def test_r2_other_customers_order_blocked():
    result = g.check_r2_ownership(order(BOBS), 1, BOBS)
    assert not result.passed


def test_r2_same_message_for_missing_and_foreign_orders():
    foreign = g.check_r2_ownership(order(BOBS), 1, BOBS).reason
    missing = g.check_r2_ownership(None, 1, BOBS).reason
    assert foreign == missing


# R3 cancel only when placed ---------------------------------------------------

def test_r3_cancel_allowed_when_placed():
    assert g.check_r3_cancel_allowed(order(PLACED)).passed


def test_r3_cancel_blocked_when_shipped():
    assert not g.check_r3_cancel_allowed(order(SHIPPED)).passed


def test_r3_cancel_blocked_when_delivered_or_cancelled():
    assert not g.check_r3_cancel_allowed(order(DELIVERED)).passed
    assert not g.check_r3_cancel_allowed(order(CANCELLED)).passed


# R4 address change only when placed ------------------------------------------

def test_r4_address_change_allowed_when_placed():
    assert g.check_r4_address_change_allowed(order(PLACED)).passed


def test_r4_address_change_blocked_when_shipped():
    assert not g.check_r4_address_change_allowed(order(SHIPPED)).passed


# R5 payment failed -------------------------------------------------------------

def test_r5_paid_order_passes():
    assert g.check_r5_payment_ok(order(PLACED), IntentEnum.CHANGE_ADDRESS).passed


def test_r5_address_change_blocked_when_payment_failed():
    assert not g.check_r5_payment_ok(order(PAYMENT_FAILED), IntentEnum.CHANGE_ADDRESS).passed
    assert not g.check_r5_payment_ok(order(PAYMENT_FAILED), IntentEnum.POSTPONE_DELIVERY).passed


def test_r5_cancel_allowed_when_payment_failed():
    assert g.check_r5_payment_ok(order(PAYMENT_FAILED), IntentEnum.CANCEL_ORDER).passed


# R6 valid address --------------------------------------------------------------

def test_r6_valid_address_passes():
    assert g.check_r6_valid_address("12 MG Road, Pune").passed
    assert g.check_r6_valid_address("Near City Mall, FC Road, Pune").passed


def test_r6_short_or_empty_address_blocked():
    assert not g.check_r6_valid_address("").passed
    assert not g.check_r6_valid_address("ab").passed


def test_r6_markup_and_vague_addresses_blocked():
    assert not g.check_r6_valid_address("<script>alert(1)</script> Road").passed
    assert not g.check_r6_valid_address("http://evil.example 12").passed
    assert not g.check_r6_valid_address("my new flat").passed
    assert not g.check_r6_valid_address("1" * 6).passed           # no letters
    assert not g.check_r6_valid_address("A" * 201 + " 1").passed  # too long


# R7 no-op changes ------------------------------------------------------------------

def test_r7_new_value_passes():
    assert g.check_r7_value_changes(order(PLACED), IntentEnum.CHANGE_ADDRESS,
                                    {"shipping_address": "12 MG Road, Pune"}).passed


def test_r7_same_address_blocked_ignoring_case_and_spaces():
    assert not g.check_r7_value_changes(order(PLACED), IntentEnum.CHANGE_ADDRESS,
                                        {"shipping_address": "4  park street, PUNE"}).passed


# R8 postpone window ------------------------------------------------------------

def test_r8_postpone_within_window_passes():
    o = order(PLACED)
    assert g.check_r8_postpone_allowed(o, o.delivery_date + timedelta(days=2), o.created_at.date()).passed


def test_r8_postpone_beyond_seven_days_blocked():
    o = order(PLACED)
    assert not g.check_r8_postpone_allowed(o, o.original_delivery_date + timedelta(days=8), TODAY).passed


def test_r8_postpone_to_past_or_earlier_date_blocked():
    o = order(PLACED)
    assert not g.check_r8_postpone_allowed(o, TODAY, TODAY).passed
    assert not g.check_r8_postpone_allowed(o, o.delivery_date - timedelta(days=1), TODAY - timedelta(days=30)).passed


def test_r8_postpone_blocked_when_delivered_or_cancelled():
    assert not g.check_r8_postpone_allowed(order(DELIVERED), TODAY + timedelta(days=3), TODAY).passed
    assert not g.check_r8_postpone_allowed(order(CANCELLED), TODAY + timedelta(days=3), TODAY).passed


# R9 preview expiry and R10 version check -------------------------------------------

def _change(**overrides):
    from app.models import ChangeRequestSchema
    now = store.utc_now()
    fields = dict(request_id="req-0000000001", customer_id=1, order_id=PLACED, intent=IntentEnum.CANCEL_ORDER,
                  order_version=1, status=ChangeRequestStatusEnum.PENDING, idempotency_key="key-00000001",
                  expires_at=now + g.PREVIEW_TTL, created_at=now)
    fields.update(overrides)
    return ChangeRequestSchema(**fields)


def test_r9_fresh_preview_passes():
    assert g.check_r9_preview_not_expired(_change(), store.utc_now()).passed


def test_r9_expired_preview_blocked():
    assert not g.check_r9_preview_not_expired(_change(), store.utc_now() + timedelta(minutes=6)).passed


def test_r10_same_version_passes():
    assert g.check_r10_version_matches(order(PLACED), _change(order_version=1)).passed


def test_r10_changed_version_blocked():
    o = order(PLACED)
    o.version = 2
    assert not g.check_r10_version_matches(o, _change(order_version=1)).passed


# R11 certain parse -------------------------------------------------------------

def test_r11_confident_complete_parse_passes():
    assert g.check_r11_parse_is_certain(parsed()).passed


def test_r11_low_confidence_asks():
    assert not g.check_r11_parse_is_certain(parsed(confidence=0.5)).passed


def test_r11_missing_fields_ask():
    assert not g.check_r11_parse_is_certain(parsed(order_id=None)).passed
    assert not g.check_r11_parse_is_certain(parsed(intent=IntentEnum.CHANGE_ADDRESS, new_address=None)).passed
    assert not g.check_r11_parse_is_certain(parsed(intent=IntentEnum.POSTPONE_DELIVERY)).passed


# R14 confirmation binding ------------------------------------------------------

def test_r14_matching_confirmation_passes():
    assert g.check_r14_confirmation_binding(_change(), 1, "key-00000001").passed


def test_r14_wrong_customer_key_or_state_blocked():
    assert not g.check_r14_confirmation_binding(_change(), 2, "key-00000001").passed
    assert not g.check_r14_confirmation_binding(_change(), 1, "key-99999999").passed
    assert not g.check_r14_confirmation_binding(_change(status=ChangeRequestStatusEnum.APPLIED), 1,
                                                "key-00000001").passed
    assert not g.check_r14_confirmation_binding(None, 1, "key-00000001").passed


# R16 single order per message ----------------------------------------------------

def test_r16_one_order_passes():
    assert g.check_r16_single_order(parsed(order_ids_mentioned=[PLACED])).passed


def test_r16_several_orders_handled_one_at_a_time():
    assert not g.check_r16_single_order(parsed(order_id=None, order_ids_mentioned=[PLACED, SHIPPED])).passed


# R17 change limit ----------------------------------------------------------------

def test_r17_under_limit_passes():
    assert g.check_r17_change_limit(g.MAX_APPLIED_CHANGES_PER_ORDER - 1).passed


def test_r17_limit_reached_blocked():
    assert not g.check_r17_change_limit(g.MAX_APPLIED_CHANGES_PER_ORDER).passed


# R19 read-only switch ------------------------------------------------------------

def test_r19_writes_enabled_passes():
    assert g.check_r19_writes_enabled(False).passed


def test_r19_read_only_mode_blocks():
    assert not g.check_r19_writes_enabled(True).passed


# evaluate_change: the combined rule set -------------------------------------------

def test_evaluate_change_all_pass_for_valid_address_change():
    results = g.evaluate_change(intent=IntentEnum.CHANGE_ADDRESS, order=order(PLACED),
                                proposed={"shipping_address": "12 MG Road, Pune"}, today=TODAY,
                                applied_changes=0, read_only_mode=False)
    assert g.first_failure(results) is None


def test_evaluate_change_reports_every_failed_rule():
    results = g.evaluate_change(intent=IntentEnum.CHANGE_ADDRESS, order=order(PAYMENT_FAILED),
                                proposed={"shipping_address": "x"}, today=TODAY,
                                applied_changes=0, read_only_mode=True)
    failed = {r.rule_id for r in results if not r.passed}
    assert {"R5", "R6", "R19"} <= failed


def test_seed_covers_each_rule_case():
    assert order(PLACED).status == OrderStatusEnum.PLACED
    assert order(SHIPPED).status == OrderStatusEnum.SHIPPED
    assert order(PAYMENT_FAILED).payment_status == PaymentStatusEnum.FAILED
    assert order(BOBS).customer_id == 2
