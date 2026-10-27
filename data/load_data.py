"""Load the Kaggle "E-commerce App Transactional Dataset" into PostgreSQL.

Pipeline: read CSVs -> check columns -> validate rows -> take a seeded subset ->
derive missing fields (documented rules) -> load in ONE transaction -> report.

Usage (from the repository root, after `python scripts/init_db.py`):
    python data/load_data.py                       # 200 customers, seed 42
    python data/load_data.py --customers 500 --seed 7
    python data/load_data.py --check               # validate only, load nothing

Raw files in data/raw/ are never modified. Re-running replaces the app data.
Every derived field is documented in docs/DATABASE_SCHEMA.md.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import bcrypt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
REPORT_FILE = ROOT / "data" / "DATA_REPORT.md"

# Columns we need from each file (after normalising headers to snake_case).
REQUIRED = {
    "customer": ["customer_id", "first_name", "email", "home_location", "home_country"],
    "product": ["id", "product_display_name"],
    "transactions": ["created_at", "customer_id", "booking_id", "product_metadata",
                     "payment_status", "total_amount"],
}
OPTIONAL = {
    "customer": ["last_name", "first_join_date"],
    "product": ["master_category", "sub_category", "article_type", "base_colour"],
    "transactions": ["payment_method", "promo_code", "promo_amount", "shipment_fee",
                     "shipment_date_limit", "shipment_location_lat", "shipment_location_long"],
}

# Derived order status: fixed proportions, assigned with a fixed random seed.
STATUS_SHARES = {"placed": 0.40, "shipped": 0.30, "delivered": 0.25, "cancelled": 0.05}
DEMO_PIN = "1234"


# ---------------------------------------------------------------------------
# Reading and checking
# ---------------------------------------------------------------------------

def snake_case(name: str) -> str:
    """productDisplayName -> product_display_name; ' Home Location ' -> home_location."""
    name = name.strip()
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def find_file(raw_dir: Path, stem: str) -> Path:
    """Find customer.csv / customers.csv etc. (case-insensitive)."""
    for path in sorted(raw_dir.rglob("*.csv")):
        if path.stem.lower() in (stem, stem + "s"):
            return path
    raise FileNotFoundError(f"No {stem}.csv found under {raw_dir}")


def read_csv(raw_dir: Path, stem: str) -> pd.DataFrame:
    """Read a CSV as text, normalise headers and check required columns."""
    path = find_file(raw_dir, stem)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="warn")
    df.columns = [snake_case(c) for c in df.columns]
    missing = [c for c in REQUIRED[stem] if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name}: missing required columns {missing}. Found: {list(df.columns)}. "
            "Update REQUIRED/the mapping in data/load_data.py and docs/DATABASE_SCHEMA.md."
        )
    for col in OPTIONAL[stem]:
        if col not in df.columns:
            df[col] = ""
    df = df.apply(lambda s: s.str.strip())
    print(f"Read {path.name}: {len(df):,} rows")
    return df


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("", np.nan), errors="coerce")


def to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.replace("", np.nan), errors="coerce", utc=True, format="mixed")


def parse_product_metadata(value: str) -> list[dict]:
    """Parse '[{"product_id": 1, "quantity": 2, "item_price": 100}]' (JSON or Python repr).

    Uses json / ast.literal_eval only (never eval). Bad entries are skipped.
    """
    if not value:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            data = parser(value)
            break
        except (ValueError, SyntaxError):
            continue
    else:
        return []
    if isinstance(data, dict):
        data = [data]
    items = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            items.append({
                "product_id": int(float(entry["product_id"])),
                "quantity": int(float(entry.get("quantity", 1))),
                "item_price": float(entry.get("item_price", 0)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return items


# ---------------------------------------------------------------------------
# Cleaning and deriving
# ---------------------------------------------------------------------------

def build_tables(raw_dir: Path, n_customers: int, seed: int, demo_day: date) -> tuple[dict, Counter]:
    """Return clean rows for customers, products, orders, order_items and a reject counter."""
    rejects: Counter = Counter()
    rng = np.random.default_rng(seed)

    cust = read_csv(raw_dir, "customer")
    prod = read_csv(raw_dir, "product")
    tx = read_csv(raw_dir, "transactions")

    # --- customers: need an ID and a unique email (email is the login) ---
    cust["customer_id_num"] = to_number(cust["customer_id"])
    bad = cust["customer_id_num"].isna() | (cust["email"] == "")
    rejects["customer: missing id or email"] += int(bad.sum())
    cust = cust[~bad].copy()
    cust["email_key"] = cust["email"].str.lower()
    dup = cust.duplicated("email_key") | cust.duplicated("customer_id_num")
    rejects["customer: duplicate id or email"] += int(dup.sum())
    cust = cust[~dup].copy()
    cust["customer_id_num"] = cust["customer_id_num"].astype("int64")

    # --- transactions: need booking id, known customer, valid amount and status ---
    tx["customer_id_num"] = to_number(tx["customer_id"])
    tx["created_at_ts"] = to_datetime(tx["created_at"])
    tx["total"] = to_number(tx["total_amount"])
    tx["payment"] = tx["payment_status"].str.capitalize().replace({"Succeeded": "Success",
                                                                   "Successful": "Success",
                                                                   "Fail": "Failed"})
    checks = {
        "transactions: missing booking_id": tx["booking_id"] == "",
        "transactions: bad customer_id": tx["customer_id_num"].isna(),
        "transactions: bad created_at": tx["created_at_ts"].isna(),
        "transactions: bad total_amount": tx["total"].isna() | (tx["total"] < 0),
        "transactions: unknown payment_status": ~tx["payment"].isin(["Success", "Failed"]),
    }
    keep = pd.Series(True, index=tx.index)
    for reason, mask in checks.items():
        rejects[reason] += int((mask & keep).sum())
        keep &= ~mask
    tx = tx[keep].copy()
    dup = tx.duplicated("booking_id")
    rejects["transactions: duplicate booking_id"] += int(dup.sum())
    tx = tx[~dup].copy()
    tx["customer_id_num"] = tx["customer_id_num"].astype("int64")
    unknown = ~tx["customer_id_num"].isin(cust["customer_id_num"])
    rejects["transactions: customer not in customer.csv"] += int(unknown.sum())
    tx = tx[~unknown].copy()

    # --- seeded subset of customers that have at least one order ---
    with_orders = np.sort(tx["customer_id_num"].unique())
    if len(with_orders) == 0:
        raise ValueError("No valid transactions left after validation; see the reject counts.")
    chosen = rng.choice(with_orders, size=min(n_customers, len(with_orders)), replace=False)
    cust = cust[cust["customer_id_num"].isin(chosen)].copy()
    tx = tx[tx["customer_id_num"].isin(chosen)].copy().sort_values("created_at_ts")

    # --- dates: shift by ONE fixed offset so the newest order falls on the demo day ---
    offset = pd.Timestamp(demo_day, tz="UTC") - tx["created_at_ts"].max().normalize()
    tx["created_at_ts"] = tx["created_at_ts"] + offset
    limit = to_datetime(tx["shipment_date_limit"]) + offset
    # Missing delivery date: created_at + 5 days (documented default).
    tx["delivery"] = limit.fillna(tx["created_at_ts"] + pd.Timedelta(days=5)).dt.date

    # --- derived status (fixed seed, fixed shares); failed payments stay 'placed' ---
    statuses = list(STATUS_SHARES)
    tx["status"] = rng.choice(statuses, size=len(tx), p=list(STATUS_SHARES.values()))
    tx.loc[tx["payment"] == "Failed", "status"] = "placed"

    # --- products referenced by the chosen orders ---
    tx["items"] = tx["product_metadata"].map(parse_product_metadata)
    rejects["transactions: unreadable product_metadata"] += int((tx["items"].map(len) == 0).sum())
    prod["product_id_num"] = to_number(prod["id"])
    prod = prod[prod["product_id_num"].notna()].drop_duplicates("product_id_num").copy()
    prod["product_id_num"] = prod["product_id_num"].astype("int64")
    used_ids = {i["product_id"] for items in tx["items"] for i in items}
    prod = prod[prod["product_id_num"].isin(used_ids)]
    known_products = set(prod["product_id_num"])

    pin_hash = bcrypt.hashpw(DEMO_PIN.encode(), bcrypt.gensalt(rounds=12)).decode()
    home = cust.set_index("customer_id_num")[["home_location", "home_country"]]

    customers = [{
        "customer_id": int(r.customer_id_num),
        "first_name": r.first_name or "Customer",
        "last_name": r.last_name or None,
        "email": r.email,
        "home_location": r.home_location or None,
        "home_country": r.home_country or None,
        "pin_hash": pin_hash,
        "joined_at": _date_or_none(r.first_join_date),
    } for r in cust.itertuples()]

    products = [{
        "product_id": int(r.product_id_num),
        "name": r.product_display_name or f"Product {int(r.product_id_num)}",
        "category": r.master_category or None,
        "sub_category": r.sub_category or None,
        "article_type": r.article_type or None,
        "base_colour": r.base_colour or None,
    } for r in prod.itertuples()]

    orders, items = [], []
    for r in tx.itertuples():
        location, country = home.loc[r.customer_id_num]
        address = location if len(location) >= 5 else f"{location}, {country}".strip(", ")
        if len(address) < 5:
            address = "Address on file"  # documented placeholder when the dataset has none
        orders.append({
            "booking_id": r.booking_id,
            "customer_id": int(r.customer_id_num),
            "created_at": r.created_at_ts.to_pydatetime(),
            "payment_method": r.payment_method or None,
            "payment_status": r.payment,
            "status": r.status,
            "shipping_address": address,
            "shipping_country": country or "Unknown",
            "shipping_lat": _float_or_none(r.shipment_location_lat),
            "shipping_long": _float_or_none(r.shipment_location_long),
            "delivery_date": r.delivery,
            "original_delivery_date": r.delivery,
            "promo_code": r.promo_code or None,
            "promo_amount": max(_float_or_none(r.promo_amount) or 0.0, 0.0),
            "shipment_fee": max(_float_or_none(r.shipment_fee) or 0.0, 0.0),
            "total_amount": float(r.total),
        })
        merged: dict[int, dict] = {}
        for item in r.items:
            if item["product_id"] not in known_products or item["quantity"] <= 0 or item["item_price"] < 0:
                rejects["order_items: unknown product or bad quantity/price"] += 1
                continue
            slot = merged.setdefault(item["product_id"], {**item, "quantity": 0})
            slot["quantity"] += item["quantity"]
        items.extend({"booking_id": r.booking_id, **i} for i in merged.values())

    return {"customers": customers, "products": products, "orders": orders, "items": items}, rejects


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _date_or_none(value: str) -> Optional[date]:
    ts = pd.to_datetime(value, errors="coerce") if value else pd.NaT
    return None if pd.isna(ts) else ts.date()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load(tables: dict, database_url: str) -> dict:
    """Replace the app data in ONE transaction. Any error rolls everything back."""
    from sqlalchemy import text

    from app.db import get_engine

    engine = get_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("""TRUNCATE app.audit_log, app.change_requests, app.order_items,
                             app.orders, app.products, app.customers RESTART IDENTITY CASCADE"""))
        conn.execute(text("""INSERT INTO app.customers (customer_id, first_name, last_name, email,
                             home_location, home_country, pin_hash, joined_at)
                             VALUES (:customer_id, :first_name, :last_name, :email, :home_location,
                                     :home_country, :pin_hash, :joined_at)"""), tables["customers"])
        if tables["products"]:
            conn.execute(text("""INSERT INTO app.products (product_id, name, category, sub_category,
                                 article_type, base_colour)
                                 VALUES (:product_id, :name, :category, :sub_category,
                                         :article_type, :base_colour)"""), tables["products"])
        conn.execute(text("""INSERT INTO app.orders (booking_id, customer_id, created_at,
                             payment_method, payment_status, status, shipping_address,
                             shipping_country, shipping_lat, shipping_long, delivery_date,
                             original_delivery_date, promo_code, promo_amount, shipment_fee,
                             total_amount)
                             VALUES (:booking_id, :customer_id, :created_at, :payment_method,
                                     :payment_status, :status, :shipping_address,
                                     :shipping_country, :shipping_lat, :shipping_long,
                                     :delivery_date, :original_delivery_date, :promo_code,
                                     :promo_amount, :shipment_fee, :total_amount)"""),
                     tables["orders"])
        ids = dict(conn.execute(text("SELECT booking_id, order_id FROM app.orders")).all())
        rows = [{"order_id": ids[i["booking_id"]], "product_id": i["product_id"],
                 "quantity": i["quantity"], "item_price": i["item_price"]} for i in tables["items"]]
        if rows:
            conn.execute(text("""INSERT INTO app.order_items (order_id, product_id, quantity, item_price)
                                 VALUES (:order_id, :product_id, :quantity, :item_price)"""), rows)
        counts = conn.execute(text("""SELECT
            (SELECT count(*) FROM app.customers), (SELECT count(*) FROM app.products),
            (SELECT count(*) FROM app.orders), (SELECT count(*) FROM app.order_items)""")).one()
    return dict(zip(["customers", "products", "orders", "order_items"], counts, strict=True))


def write_report(tables: dict, rejects: Counter, loaded: Optional[dict], args: argparse.Namespace) -> None:
    status_counts = Counter(o["status"] for o in tables["orders"])
    payment_counts = Counter(o["payment_status"] for o in tables["orders"])
    lines = [
        "# Data Report",
        "",
        f"Generated by `data/load_data.py` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.",
        f"Settings: customers={args.customers}, seed={args.seed}, demo day={args.demo_day}.",
        "",
        "## Rows prepared" + (" and loaded" if loaded else " (check only, nothing loaded)"),
        "",
        "| Table | Rows |",
        "| --- | --- |",
    ]
    source = loaded or {"customers": len(tables["customers"]), "products": len(tables["products"]),
                        "orders": len(tables["orders"]), "order_items": len(tables["items"])}
    lines += [f"| {k} | {v:,} |" for k, v in source.items()]
    lines += ["", "## Rejected rows", "", "| Reason | Rows |", "| --- | --- |"]
    lines += [f"| {k} | {v:,} |" for k, v in sorted(rejects.items()) if v] or ["| none | 0 |"]
    lines += ["", "## Derived order status (seeded)", "", "| Status | Orders |", "| --- | --- |"]
    lines += [f"| {k} | {v:,} |" for k, v in sorted(status_counts.items())]
    lines += ["", "## Payment status (from dataset)", "", "| Payment | Orders |", "| --- | --- |"]
    lines += [f"| {k} | {v:,} |" for k, v in sorted(payment_counts.items())]
    lines += ["", f"Demo login for every loaded customer: their email and PIN `{DEMO_PIN}`."]
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_FILE.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load the Kaggle dataset into PostgreSQL.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--customers", type=int, default=200, help="Customers in the subset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (subset and status)")
    parser.add_argument("--demo-day", type=date.fromisoformat, default=date.today(),
                        help="Newest order is shifted to this date (YYYY-MM-DD)")
    parser.add_argument("--url", help="Database URL (default: DATABASE_URL from .env)")
    parser.add_argument("--check", action="store_true", help="Validate only; load nothing")
    args = parser.parse_args()

    try:
        tables, rejects = build_tables(args.raw_dir, args.customers, args.seed, args.demo_day)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Data check failed: {exc}")
        return 1

    print(f"Prepared: {len(tables['customers'])} customers, {len(tables['orders'])} orders, "
          f"{len(tables['items'])} order items, {len(tables['products'])} products")
    for reason, count in sorted(rejects.items()):
        if count:
            print(f"  rejected {count:,}: {reason}")

    loaded = None
    if not args.check:
        loaded = load(tables, args.url or get_settings().database_url)
        print(f"Loaded: {loaded}")
    write_report(tables, rejects, loaded, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
