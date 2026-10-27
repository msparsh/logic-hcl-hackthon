"""
Data ingestion: raw Kaggle CSVs -> cleaned, validated rows -> SQLite.

Source: https://www.kaggle.com/datasets/bytadit/transactional-ecommerce
Put the CSVs in data/raw/ (git-ignored):  customer.csv, product.csv, transactions.csv

Flow:  load_csv (check file + columns) -> clean_* (types, empties, duplicates)
       -> build_orders (explode product_metadata into order items)
       -> write_db (SQLite)  -> report (what was kept / rejected, and why)

Run:  python ingestion.py [--raw-dir data/raw] [--db data/support.db]

Nothing is invented here. Bad rows are dropped and counted in the report;
the two places where we derive a value are marked "ASSUMPTION" below.
"""
import argparse
import ast
import sqlite3
from pathlib import Path

import pandas as pd

# Columns each raw file must contain, or ingestion stops with a clear error.
REQUIRED_COLUMNS = {
    "customer.csv": ["customer_id", "first_name", "last_name", "email",
                     "home_location", "home_country", "first_join_date"],
    "product.csv": ["id", "productDisplayName", "masterCategory", "subCategory",
                    "articleType", "baseColour"],
    "transactions.csv": ["created_at", "customer_id", "booking_id", "product_metadata",
                         "payment_method", "payment_status", "promo_amount", "promo_code",
                         "shipment_fee", "shipment_date_limit", "shipment_location_lat",
                         "shipment_location_long", "total_amount"],
}

VALID_PAYMENT_STATUS = {"Success", "Failed"}  # matches PaymentStatusEnum in main.py


class IngestionError(Exception):
    """Raised for input problems the user must fix (missing file, columns, empty file)."""


# ----------------------------------------------------------------------------
# 1. Load + structural checks
# ----------------------------------------------------------------------------
def load_csv(path: Path) -> pd.DataFrame:
    """Read one CSV and check it exists, is not empty and has the required columns."""
    if not path.exists():
        raise IngestionError(f"File not found: {path}")
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise IngestionError(f"{path.name} is empty")
    except pd.errors.ParserError as e:
        raise IngestionError(f"{path.name} is not a valid CSV: {e}")
    if df.empty:
        raise IngestionError(f"{path.name} has a header but no rows")
    missing = [c for c in REQUIRED_COLUMNS[path.name] if c not in df.columns]
    if missing:
        raise IngestionError(f"{path.name} is missing columns: {missing}")
    return df


def _drop(df: pd.DataFrame, mask: pd.Series, reason: str, rejects: list) -> pd.DataFrame:
    """Remove rows where mask is True and record how many, with the reason."""
    if mask.any():
        rejects.append({"reason": reason, "rows": int(mask.sum())})
    return df[~mask]


# ----------------------------------------------------------------------------
# 2. Clean each table
# ----------------------------------------------------------------------------
def clean_customers(df: pd.DataFrame, rejects: list) -> pd.DataFrame:
    df = df[REQUIRED_COLUMNS["customer.csv"]].copy()
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce")
    df["email"] = df["email"].astype("string").str.strip().str.lower()
    df["joined_at"] = pd.to_datetime(df.pop("first_join_date"), errors="coerce").dt.date
    df = _drop(df, df["customer_id"].isna(), "customer: bad/missing customer_id", rejects)
    df = _drop(df, df["email"].isna() | ~df["email"].str.contains("@", na=False),
               "customer: bad/missing email", rejects)
    df = _drop(df, df["joined_at"].isna(), "customer: bad/missing join date", rejects)
    df["customer_id"] = df["customer_id"].astype(int)
    df = _drop(df, df.duplicated("customer_id"), "customer: duplicate customer_id", rejects)
    df = _drop(df, df.duplicated("email"), "customer: duplicate email", rejects)
    return df


def clean_products(df: pd.DataFrame, rejects: list) -> pd.DataFrame:
    df = df[REQUIRED_COLUMNS["product.csv"]].rename(columns={
        "id": "product_id", "productDisplayName": "name", "masterCategory": "category",
        "subCategory": "sub_category", "articleType": "article_type",
        "baseColour": "base_colour"}).copy()
    df["product_id"] = pd.to_numeric(df["product_id"], errors="coerce")
    df = _drop(df, df["product_id"].isna(), "product: bad/missing id", rejects)
    df = _drop(df, df["name"].isna() | (df["name"].astype("string").str.strip() == ""),
               "product: missing name", rejects)
    df["product_id"] = df["product_id"].astype(int)
    df = _drop(df, df.duplicated("product_id"), "product: duplicate id", rejects)
    return df


def clean_transactions(df: pd.DataFrame, customer_ids: set, rejects: list) -> pd.DataFrame:
    df = df[REQUIRED_COLUMNS["transactions.csv"]].copy()
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce")
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["delivery_date"] = pd.to_datetime(df.pop("shipment_date_limit"), errors="coerce").dt.date
    for col in ["promo_amount", "shipment_fee", "total_amount",
                "shipment_location_lat", "shipment_location_long"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = _drop(df, df["booking_id"].isna(), "order: missing booking_id", rejects)
    df = _drop(df, df.duplicated("booking_id"), "order: duplicate booking_id", rejects)
    df = _drop(df, df["customer_id"].isna(), "order: bad/missing customer_id", rejects)
    df["customer_id"] = df["customer_id"].astype(int)
    df = _drop(df, ~df["customer_id"].isin(customer_ids),
               "order: customer_id not in customer table", rejects)
    df = _drop(df, df["created_at"].isna(), "order: bad/missing created_at", rejects)
    df = _drop(df, ~df["payment_status"].isin(VALID_PAYMENT_STATUS),
               "order: payment_status not Success/Failed", rejects)
    df = _drop(df, df["total_amount"].isna() | (df["total_amount"] < 0),
               "order: bad/negative total_amount", rejects)
    df["promo_amount"] = df["promo_amount"].fillna(0).clip(lower=0)
    df["shipment_fee"] = df["shipment_fee"].fillna(0).clip(lower=0)
    return df


# ----------------------------------------------------------------------------
# 3. Build orders + order items
# ----------------------------------------------------------------------------
def parse_items(raw) -> list:
    """product_metadata is a Python-literal list of dicts (product_id, quantity, item_price).
    Returns [] if it cannot be parsed or any item is invalid."""
    try:
        items = ast.literal_eval(raw) if isinstance(raw, str) else []
    except (ValueError, SyntaxError):
        return []
    if not isinstance(items, list) or not items:
        return []
    out = []
    for it in items:
        try:
            pid, qty, price = int(it["product_id"]), int(it["quantity"]), float(it["item_price"])
        except (KeyError, TypeError, ValueError):
            return []
        if qty < 1 or price < 0:
            return []
        out.append({"product_id": pid, "quantity": qty, "item_price": price})
    return out


def build_orders(tx: pd.DataFrame, customers: pd.DataFrame, product_ids: set, rejects: list):
    """Return (orders, order_items) DataFrames."""
    tx = tx.copy()
    tx["items"] = tx["product_metadata"].map(parse_items)
    tx = _drop(tx, tx["items"].map(len) == 0, "order: product_metadata empty/invalid", rejects)
    tx = _drop(tx, tx["items"].map(lambda its: any(i["product_id"] not in product_ids for i in its)),
               "order: item product_id not in product table", rejects)

    # ASSUMPTION 1: the dataset has no shipping address text, only coordinates.
    # We use the customer's home_location as the shipping address.
    home = customers.set_index("customer_id")["home_location"]
    tx["shipping_address"] = tx["customer_id"].map(home).astype("string").str.strip()
    tx = _drop(tx, tx["shipping_address"].isna() | (tx["shipping_address"].str.len() < 5),
               "order: no usable shipping address (home_location missing/too short)", rejects)

    # Stable ids: oldest order gets 1. booking_id (Kaggle id) is kept as the unique key.
    tx = tx.sort_values(["created_at", "booking_id"]).reset_index(drop=True)
    tx["order_id"] = tx.index + 1
    tx["order_ref"] = "ORD-" + tx["order_id"].astype(str)
    # ASSUMPTION 2: the dataset has no order status; every order is loaded as 'placed'.
    tx["status"] = "placed"
    tx["version"] = 1
    tx["updated_at"] = tx["created_at"]

    items = tx[["order_id", "items"]].explode("items")
    items = pd.concat([items["order_id"].reset_index(drop=True),
                       pd.DataFrame(items["items"].tolist())], axis=1)
    # One row per (order, product): merge repeats by summing quantity (PK is order+product).
    items = items.groupby(["order_id", "product_id"], as_index=False).agg(
        quantity=("quantity", "sum"), item_price=("item_price", "first"))

    orders = tx.drop(columns=["items", "product_metadata"])
    orders = orders.rename(columns={"shipment_location_lat": "shipping_lat",
                                    "shipment_location_long": "shipping_long"})
    return orders, items


# ----------------------------------------------------------------------------
# 4. Write to SQLite
# ----------------------------------------------------------------------------
SCHEMA = """
DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;    DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
    email TEXT NOT NULL UNIQUE, home_location TEXT, home_country TEXT, joined_at TEXT NOT NULL);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT,
    sub_category TEXT, article_type TEXT, base_colour TEXT);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY, order_ref TEXT NOT NULL UNIQUE, booking_id TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    created_at TEXT NOT NULL, payment_method TEXT,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('Success','Failed')),
    status TEXT NOT NULL CHECK (status IN ('placed','shipped','delivered','cancelled')),
    shipping_address TEXT NOT NULL CHECK (length(shipping_address) >= 5),
    shipping_lat REAL, shipping_long REAL, delivery_date TEXT, promo_code TEXT,
    promo_amount REAL NOT NULL CHECK (promo_amount >= 0),
    shipment_fee REAL NOT NULL CHECK (shipment_fee >= 0),
    total_amount REAL NOT NULL CHECK (total_amount >= 0),
    version INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    item_price REAL NOT NULL CHECK (item_price >= 0),
    PRIMARY KEY (order_id, product_id));
"""


def write_db(db_path: Path, customers, products, orders, items) -> None:
    """Rebuild the tables from scratch (re-running ingestion is safe and gives the same result)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(SCHEMA)
        for name, df in [("customers", customers), ("products", products),
                         ("orders", orders), ("order_items", items)]:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
            out = df[cols].astype(object).where(df[cols].notna(), None)
            out = out.map(lambda v: str(v) if hasattr(v, "isoformat") else v)  # dates -> text
            con.executemany(f"INSERT INTO {name} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                            out.itertuples(index=False, name=None))
        con.commit()
    finally:
        con.close()


# ----------------------------------------------------------------------------
# 5. Orchestration
# ----------------------------------------------------------------------------
def run_ingestion(raw_dir: Path, db_path: Path) -> dict:
    """Run the full pipeline. Returns a report dict (counts + rejected-row reasons)."""
    raw_dir = Path(raw_dir)
    rejects: list = []
    raw = {name: load_csv(raw_dir / name) for name in REQUIRED_COLUMNS}

    customers = clean_customers(raw["customer.csv"], rejects)
    products = clean_products(raw["product.csv"], rejects)
    tx = clean_transactions(raw["transactions.csv"], set(customers["customer_id"]), rejects)
    orders, items = build_orders(tx, customers, set(products["product_id"]), rejects)
    if orders.empty:
        raise IngestionError("No valid orders left after cleaning; see rejected-row reasons")

    write_db(Path(db_path), customers, products, orders, items)
    return {"db": str(db_path),
            "rows_read": {n: len(d) for n, d in raw.items()},
            "rows_written": {"customers": len(customers), "products": len(products),
                             "orders": len(orders), "order_items": len(items)},
            "rejected": rejects}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--db", default="data/support.db")
    args = ap.parse_args()
    try:
        rep = run_ingestion(Path(args.raw_dir), Path(args.db))
    except IngestionError as e:
        raise SystemExit(f"Ingestion failed: {e}")
    print(f"Wrote {rep['db']}")
    print("Rows read:   ", rep["rows_read"])
    print("Rows written:", rep["rows_written"])
    for r in rep["rejected"]:
        print(f"  rejected {r['rows']:>6}  {r['reason']}")
