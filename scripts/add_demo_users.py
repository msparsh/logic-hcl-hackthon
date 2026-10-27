"""Add the demo customers (Alice, Bob) and their rule-case orders next to loaded data.

Unlike db/seed.sql, this never deletes anything, so it is safe after
data/load_data.py. Safe to re-run: existing rows are left as they are.

    python scripts/add_demo_users.py
Login: alice@example.com / 1234 and bob@example.com / 1234
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db import get_engine  # noqa: E402

PIN_1234 = "$2b$12$En/xHGYrRK.Fm6h52HlRw.jL2NpFIzeGYRkeryPr6N.KPLFTiOU7y"
ALICE, BOB = 900001, 900002

CUSTOMERS = [
    (ALICE, "Alice", "Smith", "alice@example.com", "Pune, Maharashtra", "India"),
    (BOB, "Bob", "Kumar", "bob@example.com", "Ahmedabad, Gujarat", "India"),
]
PRODUCTS = [
    (900101, "Cotton Crew Neck T-Shirt", "Apparel", "Topwear", "Tshirts", "Navy"),
    (900102, "Running Shoes", "Footwear", "Shoes", "Sports Shoes", "Grey"),
    (900103, "Leather Wallet", "Accessories", "Wallets", "Wallets", "Brown"),
]
# booking_id, customer, payment, status, address, days to delivery, product, price, what it demonstrates
ORDERS = [
    ("DEMO-0001", ALICE, "Success", "placed", "4 Park Street, Pune", 4, 900101, 899.00),     # change/cancel OK
    ("DEMO-0002", ALICE, "Success", "shipped", "4 Park Street, Pune", 1, 900102, 2499.00),   # R3/R4 block
    ("DEMO-0003", ALICE, "Success", "delivered", "4 Park Street, Pune", -5, 900101, 1399.00),
    ("DEMO-0004", ALICE, "Success", "cancelled", "4 Park Street, Pune", 2, 900103, 599.00),
    ("DEMO-0005", ALICE, "Failed", "placed", "4 Park Street, Pune", 5, 900102, 1899.00),     # R5 block
    ("DEMO-0006", BOB, "Success", "placed", "21 CG Road, Ahmedabad", 3, 900103, 749.00),     # R2 block
]


def main() -> int:
    with get_engine().begin() as conn:
        for row in CUSTOMERS:
            conn.execute(text("""INSERT INTO app.customers
                    (customer_id, first_name, last_name, email, home_location, home_country, pin_hash, joined_at)
                    VALUES (:id, :fn, :ln, :em, :loc, :ctry, :pin, CURRENT_DATE - 300)
                    ON CONFLICT DO NOTHING"""),
                         dict(zip(("id", "fn", "ln", "em", "loc", "ctry"), row), pin=PIN_1234))
        # If the email already exists (under another ID), use that customer's ID.
        ids = {cid: conn.execute(text("SELECT customer_id FROM app.customers WHERE lower(email) = :e"),
                                 {"e": email}).scalar()
               for cid, _, _, email, _, _ in CUSTOMERS}
        for row in PRODUCTS:
            conn.execute(text("""INSERT INTO app.products
                    (product_id, name, category, sub_category, article_type, base_colour)
                    VALUES (:id, :n, :c, :s, :a, :b) ON CONFLICT DO NOTHING"""),
                         dict(zip(("id", "n", "c", "s", "a", "b"), row)))
        for booking, cust, pay, status, addr, days, product, price in ORDERS:
            order_id = conn.execute(text("""INSERT INTO app.orders
                    (booking_id, customer_id, created_at, payment_method, payment_status, status,
                     shipping_address, shipping_country, delivery_date, original_delivery_date,
                     promo_amount, shipment_fee, total_amount)
                    VALUES (:b, :c, now() - interval '1 day', 'UPI', :p, :s, :a, 'India',
                            CURRENT_DATE + :d, CURRENT_DATE + :d, 0, 0, :t)
                    ON CONFLICT (booking_id) DO NOTHING RETURNING order_id"""),
                                    {"b": booking, "c": ids[cust], "p": pay, "s": status, "a": addr,
                                     "d": days, "t": price}).scalar()
            if order_id is not None:
                conn.execute(text("""INSERT INTO app.order_items (order_id, product_id, quantity, item_price)
                        VALUES (:o, :p, 1, :t)"""), {"o": order_id, "p": product, "t": price})
        refs = conn.execute(text("""SELECT o.order_ref, o.status, o.payment_status, c.first_name
                FROM app.orders o JOIN app.customers c USING (customer_id)
                WHERE o.booking_id LIKE 'DEMO-%' ORDER BY o.order_id""")).all()
    print("Demo users ready: alice@example.com / 1234, bob@example.com / 1234")
    for ref, status, pay, name in refs:
        print(f"  {name:<5} {ref:<10} {status:<9} payment {pay}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
