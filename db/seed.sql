-- =====================================================================
-- Team Logic — demo and test seed data (synthetic, not from Kaggle)
--
-- Purpose: lets every team member run the app and the tests at once,
-- before the Kaggle data is loaded. Each order covers one business
-- rule case from docs/BUSINESS_RULES.md.
--
-- Demo login for every customer: PIN 1234 (stored as a bcrypt hash).
-- Run after db/schema.sql:  psql "$DATABASE_URL" -f db/seed.sql
-- Safe to re-run: it clears the app tables first.
-- =====================================================================

BEGIN;

TRUNCATE app.audit_log, app.change_requests, app.order_items, app.orders,
         app.products, app.customers RESTART IDENTITY CASCADE;

-- Order IDs start at 10001 again after the truncate.
ALTER TABLE app.orders ALTER COLUMN order_id RESTART WITH 10001;

INSERT INTO app.customers
    (customer_id, first_name, last_name, email, home_location, home_country, pin_hash, joined_at)
VALUES
    (1, 'Alice', 'Smith', 'alice@example.com', 'Pune, Maharashtra', 'India',
     '$2b$12$En/xHGYrRK.Fm6h52HlRw.jL2NpFIzeGYRkeryPr6N.KPLFTiOU7y', DATE '2025-01-15'),
    (2, 'Bob', 'Kumar', 'bob@example.com', 'Ahmedabad, Gujarat', 'India',
     '$2b$12$En/xHGYrRK.Fm6h52HlRw.jL2NpFIzeGYRkeryPr6N.KPLFTiOU7y', DATE '2025-03-02');

INSERT INTO app.products
    (product_id, name, category, sub_category, article_type, base_colour)
VALUES
    (101, 'Cotton Crew Neck T-Shirt', 'Apparel', 'Topwear', 'Tshirts', 'Navy'),
    (102, 'Running Shoes', 'Footwear', 'Shoes', 'Sports Shoes', 'Grey'),
    (103, 'Leather Wallet', 'Accessories', 'Wallets', 'Wallets', 'Brown');

-- Dates are relative to the day the seed runs, so the demo always works.
INSERT INTO app.orders
    (booking_id, customer_id, created_at, payment_method, payment_status, status,
     shipping_address, shipping_country, delivery_date, original_delivery_date,
     promo_code, promo_amount, shipment_fee, total_amount)
VALUES
    -- ORD-10001: placed, paid           -> address change and cancel allowed
    ('SEED-0001', 1, now() - interval '1 day', 'Credit Card', 'Success', 'placed',
     '4 Park Street, Pune', 'India', CURRENT_DATE + 4, CURRENT_DATE + 4,
     NULL, 0, 50, 899.00),
    -- ORD-10002: shipped                -> R3/R4 block cancel and address change
    ('SEED-0002', 1, now() - interval '3 days', 'UPI', 'Success', 'shipped',
     '4 Park Street, Pune', 'India', CURRENT_DATE + 1, CURRENT_DATE + 1,
     NULL, 0, 0, 2499.00),
    -- ORD-10003: delivered              -> all changes blocked
    ('SEED-0003', 1, now() - interval '10 days', 'Debit Card', 'Success', 'delivered',
     '4 Park Street, Pune', 'India', CURRENT_DATE - 5, CURRENT_DATE - 5,
     'WELCOME10', 100, 50, 1349.00),
    -- ORD-10004: cancelled              -> all changes blocked
    ('SEED-0004', 1, now() - interval '6 days', 'UPI', 'Success', 'cancelled',
     '4 Park Street, Pune', 'India', CURRENT_DATE + 2, CURRENT_DATE + 2,
     NULL, 0, 0, 599.00),
    -- ORD-10005: placed, payment failed -> R5 blocks address change, cancel allowed
    ('SEED-0005', 1, now() - interval '2 hours', 'Credit Card', 'Failed', 'placed',
     '4 Park Street, Pune', 'India', CURRENT_DATE + 5, CURRENT_DATE + 5,
     NULL, 0, 50, 1899.00),
    -- ORD-10006: Bob's order            -> R2 blocks Alice from touching it
    ('SEED-0006', 2, now() - interval '1 day', 'UPI', 'Success', 'placed',
     '21 CG Road, Ahmedabad', 'India', CURRENT_DATE + 3, CURRENT_DATE + 3,
     NULL, 0, 50, 749.00);

INSERT INTO app.order_items (order_id, product_id, quantity, item_price)
VALUES
    (10001, 101, 1, 849.00),
    (10002, 102, 1, 2499.00),
    (10003, 101, 2, 699.50),
    (10004, 103, 1, 599.00),
    (10005, 102, 1, 1849.00),
    (10006, 103, 1, 699.00);

COMMIT;
