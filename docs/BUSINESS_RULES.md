# Business Rules

Business rules for the Autonomous Customer Support Agent. An order is changed only when **every** applicable rule passes **and** the customer confirms the preview. If any rule fails, nothing is written.

## Sources

| Source | What it gives us |
| --- | --- |
| Use-case brief (Agentic AI, Option B) | Verify identity; block changes if the item has shipped or the payment failed; isolated transactions; no double-booking |
| Dataset (Kaggle, E-commerce App Transactional Dataset) | `payment_status`, `shipment_date_limit`, `home_country` |
| Industry practice | Orders can be cancelled, and the delivery address changed, only before dispatch ([Amazon](https://aboutamazon.co.uk/news/retail/how-to-cancel-an-amazon-order), [Chron](https://smallbusiness.chron.com/change-shipping-address-order-amazon-29640.html)) |
| Team assumption | Documented below; can be changed by agreement |

## Rules

| ID | Rule | Applies to | Enforced in | Source |
| --- | --- | --- | --- | --- |
| R1 | The customer must be logged in. Identity comes only from the verified token, never from the chat text. | All | API (auth) | Brief |
| R2 | The order must exist and belong to the logged-in customer. | All | Code + `WHERE customer_id = :token_customer` | Brief |
| R3 | An order can be cancelled only while its status is `placed`. | Cancel | Code + DB `CHECK` on status | Brief + industry |
| R4 | The shipping address can be changed only while the status is `placed`. | Change address | Code | Brief + industry |
| R5 | If `payment_status` is `Failed`, address changes and postponements are blocked. Cancelling is allowed (nothing was charged). | Change address, postpone | Code | Brief + dataset |
| R6 | The new address must be non-empty, at least 5 characters, and in the order's `shipping_country`. | Change address | Code + DB `CHECK` on length | Assumption + dataset |
| R7 | If the new value equals the current value, no change is made. | All changes | Code | Assumption |
| R8 | Delivery can be postponed only if the order is not delivered or cancelled; the new date must be after today and at most 7 days after `original_delivery_date`. | Postpone | Code | Assumption + dataset |
| R9 | Only one pending change per order; a preview expires 5 minutes after it is shown. | All changes | DB partial unique index + `expires_at` | Assumption |
| R10 | At confirmation, every rule is checked again and the order `version` must match the version seen at preview. | All changes | Code + row lock (`FOR UPDATE`) + version check | Brief (no double-booking) |
| R11 | If the parser's confidence is below 0.70 or a required field is missing, the agent asks a question instead of acting. | All | Code | Assumption |
| R12 | Refunds, returns and unknown requests are escalated to a human agent. | Other | Code | Out of scope |

## Decisions

| Decision | Meaning | Database written? |
| --- | --- | --- |
| `needs_info` | A required field is missing or confidence is low (R11) | No |
| `blocked` | A rule failed; the reason is shown to the customer | No (audit only) |
| `needs_confirmation` | All rules passed; preview shown with old and new values | `change_requests` row only |
| `declined` | The customer chose Cancel at the preview | No (audit only) |
| `expired` | Confirmation arrived after 5 minutes (R9) | No (audit only) |
| `approved` | Confirmed, rules re-checked, change applied in one transaction | Yes |
| `failed` | Database error; transaction rolled back | No (audit only) |
| `escalated` | Handed to a human (R12) | No (audit only) |

## Confirmation before change

Every change that modifies data shows the customer exactly what will change before anything is written. Read-only requests (track an order) need no confirmation.

```
You asked to change the shipping address of order ORD-10023.
Current: 4 Park Street, Pune
New:     12 MG Road, Pune
[Confirm]  [Cancel]
```

The preview is built from the database and the parsed request, not from free LLM text.

## Testing

Each rule has one pass test and one fail test in `tests/test_guardrails.py`, named after its ID (for example `test_r3_cancel_blocked_when_shipped`). The evaluation set must show every should-block message blocked and zero unsafe changes.

## Change control

Rules change only through a reviewed pull request that updates this file, the rule function and its tests together.
