"""Tests for ingestion.py. The CSVs below are tiny hand-written test fixtures, not real data."""
import sqlite3

import pandas as pd
import pytest

from ingestion import IngestionError, load_csv, parse_items, run_ingestion

CUSTOMERS = pd.DataFrame({
    "customer_id": [1, 2, 2, 3], "first_name": ["A", "B", "B", "C"], "last_name": ["x"] * 4,
    "email": ["a@x.com", "b@x.com", "b2@x.com", "not-an-email"],
    "home_location": ["Pune, India", "Delhi, India", "Delhi, India", "Goa, India"],
    "home_country": ["India"] * 4, "first_join_date": ["2024-01-01"] * 4})
PRODUCTS = pd.DataFrame({
    "id": [10, 11], "productDisplayName": ["Shirt", "Shoe"], "masterCategory": ["Apparel", "Footwear"],
    "subCategory": ["Top", "Shoes"], "articleType": ["Shirts", "Casual"], "baseColour": ["Blue", "Black"]})
TX = pd.DataFrame({
    "created_at": ["2024-02-01"] * 5, "customer_id": [1, 1, 2, 99, 1],
    "booking_id": ["b1", "b2", "b3", "b4", "b1"],
    "product_metadata": ["[{'product_id': 10, 'quantity': 2, 'item_price': 5.0}]",
                         "garbage",
                         "[{'product_id': 11, 'quantity': 1, 'item_price': 9.0}]",
                         "[{'product_id': 10, 'quantity': 1, 'item_price': 5.0}]",
                         "[{'product_id': 10, 'quantity': 1, 'item_price': 5.0}]"],
    "payment_method": ["UPI"] * 5, "payment_status": ["Success"] * 5,
    "promo_amount": [0, 0, None, 0, 0], "promo_code": [None] * 5, "shipment_fee": [1] * 5,
    "shipment_date_limit": ["2024-02-10"] * 5, "shipment_location_lat": [1.0] * 5,
    "shipment_location_long": [2.0] * 5, "total_amount": [11, 11, 10, 6, 6]})


@pytest.fixture
def raw_dir(tmp_path):
    CUSTOMERS.to_csv(tmp_path / "customer.csv", index=False)
    PRODUCTS.to_csv(tmp_path / "product.csv", index=False)
    TX.to_csv(tmp_path / "transactions.csv", index=False)
    return tmp_path


def test_happy_path_drops_bad_rows(raw_dir, tmp_path):
    db = tmp_path / "out.db"
    rep = run_ingestion(raw_dir, db)
    # customers: dup id 2 (second row) and bad email dropped -> 2 left
    assert rep["rows_written"]["customers"] == 2
    # orders: b1 kept (dup dropped), b2 garbage, b4 unknown customer -> b1 and b3 left
    assert rep["rows_written"]["orders"] == 2
    con = sqlite3.connect(db)
    assert con.execute("select count(*) from order_items").fetchone()[0] == 2
    assert con.execute("select quantity from order_items where order_id=1").fetchone()[0] == 2
    assert con.execute("select promo_amount from orders where booking_id='b3'").fetchone()[0] == 0


def test_rerun_is_idempotent(raw_dir, tmp_path):
    db = tmp_path / "out.db"
    run_ingestion(raw_dir, db)
    assert run_ingestion(raw_dir, db)["rows_written"]["orders"] == 2


def test_missing_file(tmp_path):
    with pytest.raises(IngestionError, match="not found"):
        load_csv(tmp_path / "customer.csv")


def test_empty_file(tmp_path):
    (tmp_path / "customer.csv").write_text("")
    with pytest.raises(IngestionError, match="empty"):
        load_csv(tmp_path / "customer.csv")


def test_missing_columns(tmp_path):
    pd.DataFrame({"customer_id": [1]}).to_csv(tmp_path / "customer.csv", index=False)
    with pytest.raises(IngestionError, match="missing columns"):
        load_csv(tmp_path / "customer.csv")


def test_parse_items_rejects_bad_input():
    assert parse_items(None) == []
    assert parse_items("[{'product_id': 1, 'quantity': 0, 'item_price': 1}]") == []
    assert parse_items("[{'product_id': 1}]") == []
