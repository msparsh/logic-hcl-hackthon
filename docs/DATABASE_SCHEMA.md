# Database Schema

PostgreSQL schema for the Autonomous Customer Support Agent. DDL: [`db/schema.sql`](../db/schema.sql). Rule IDs refer to [`BUSINESS_RULES.md`](BUSINESS_RULES.md).

## Layout

- **`raw` schema:** Kaggle CSVs loaded as-is. Never edited by the application.
- **`app` schema:** clean tables the agent reads and writes. Only `orders`, `change_requests` and `audit_log` are written at runtime.

## Entity relationship diagram

```mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "places"
    ORDERS ||--|{ ORDER_ITEMS : "contains"
    PRODUCTS ||--o{ ORDER_ITEMS : "appears in"
    CUSTOMERS ||--o{ CHANGE_REQUESTS : "asks for"
    ORDERS ||--o{ CHANGE_REQUESTS : "targeted by"
    CHANGE_REQUESTS ||--o{ AUDIT_LOG : "logged as"
    CUSTOMERS ||--o{ AUDIT_LOG : "acted for"
    ORDERS ||--o{ AUDIT_LOG : "history of"

    CUSTOMERS {
        bigint customer_id PK
        text first_name
        text last_name
        text email UK "login"
        text home_location
        text home_country
        text pin_hash "bcrypt"
        date joined_at
    }

    ORDERS {
        bigint order_id PK "identity, starts at 10001"
        text order_ref UK "generated: ORD-order_id"
        text booking_id UK "Kaggle ID"
        bigint customer_id FK
        timestamptz created_at
        text payment_method
        text payment_status "CHECK Success or Failed"
        text status "CHECK placed shipped delivered cancelled"
        text shipping_address "CHECK min length 5"
        text shipping_country "R6"
        numeric shipping_lat
        numeric shipping_long
        date delivery_date
        date original_delivery_date "R8"
        text promo_code
        numeric promo_amount "CHECK >= 0"
        numeric shipment_fee "CHECK >= 0"
        numeric total_amount "CHECK >= 0"
        int version "R10 conflict check"
        timestamptz updated_at
    }

    ORDER_ITEMS {
        bigint order_id PK, FK
        bigint product_id PK, FK
        int quantity "CHECK > 0"
        numeric item_price "CHECK >= 0"
    }

    PRODUCTS {
        bigint product_id PK
        text name
        text category
        text sub_category
        text article_type
        text base_colour
    }

    CHANGE_REQUESTS {
        uuid request_id PK
        text session_id
        bigint customer_id FK
        bigint order_id FK "R9 one pending per order"
        text intent "CHECK"
        numeric confidence "R11"
        jsonb proposed_change
        jsonb preview "old and new values"
        int order_version "R10 version seen at preview"
        text status "pending confirmed declined expired blocked applied"
        text idempotency_key UK "no double booking"
        timestamptz expires_at "R9 preview valid 5 min"
        timestamptz created_at
        timestamptz decided_at
    }

    AUDIT_LOG {
        bigint audit_id PK
        uuid request_id FK
        bigint customer_id FK
        bigint order_id FK
        text action
        text decision "CHECK"
        jsonb rule_results
        jsonb before_state
        jsonb after_state
        boolean fallback_used
        int latency_ms
        timestamptz created_at "append-only"
    }
```

## Tables

| Table | Purpose | Written at runtime |
| --- | --- | --- |
| `customers` | Identity and login (`email` unique, PIN stored as bcrypt hash) | No |
| `products` | Product names shown in previews | No |
| `orders` | Orders the agent may change | Yes, only by the Act step |
| `order_items` | Products in each order, parsed from `product_metadata` | No |
| `change_requests` | Each preview awaiting confirmation | Yes |
| `audit_log` | Every decision, including blocked and declined requests | Yes, append-only |

LangGraph conversation checkpoints are created by `PostgresSaver.setup()` and are not part of this file.

## How the database enforces the rules

| Rule | Enforcement |
| --- | --- |
| Valid status values | `CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled'))` |
| R6 address length | `CHECK (length(trim(shipping_address)) >= 5)` |
| R9 one pending change per order | Partial unique index `uq_one_pending_change_per_order` |
| No double-booking | `UNIQUE (idempotency_key)` |
| R10 no conflicting update | `SELECT ... FOR UPDATE` and `UPDATE ... WHERE version = :seen_version` (0 rows means conflict, so roll back) |
| Tamper-proof history | Trigger blocks `UPDATE` and `DELETE` on `audit_log` |
| Valid intents and decisions | `CHECK` lists matching the API enums |

All of the above were tested on PostgreSQL 16: each invalid write is rejected.

## Dataset mapping

Column names must be confirmed against the downloaded files before loading.

| Kaggle file and column | App column |
| --- | --- |
| `customer.csv`: customer_id, first_name, last_name, email, home_location, home_country, first_join_date | `customers` (same names; `first_join_date` → `joined_at`) |
| `product.csv`: id, productDisplayName, masterCategory, subCategory, articleType, baseColour | `products` |
| `transactions.csv`: booking_id, customer_id, created_at, payment_method, payment_status, promo_code, promo_amount, shipment_fee, shipment_date_limit, shipment_location_lat, shipment_location_long, total_amount | `orders` (`shipment_date_limit` → `delivery_date` and `original_delivery_date`) |
| `transactions.csv`: product_metadata | `order_items` (parsed list of product, quantity, price) |
| `click_stream.csv` | Not loaded (out of scope) |

## Derived fields

These fields are not in the dataset. They are produced by seeded, documented code in `data/load_data.py`, never by an LLM.

| Field | Rule |
| --- | --- |
| `orders.status` | Assigned with a fixed random seed and stated proportions |
| `orders.shipping_address` | Starts from the customer's `home_location`; changed later only through the agent |
| `orders.shipping_country` | Copied from the customer's `home_country` |
| `customers.pin_hash` | One documented demo PIN, stored as a bcrypt hash |
| Dates | Shifted by one fixed offset so the latest order falls on the demo day |
| Row count | A seeded subset of customers and their orders |
