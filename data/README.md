# Data

Raw data is **not** committed to this repository. Each team member downloads it once; the cleaned data lives in the shared PostgreSQL database.

## Source register

| Dataset | Publisher | URL | Terms | Downloaded on | By |
| --- | --- | --- | --- | --- | --- |
| E-commerce App Transactional Dataset | bytadit (Kaggle) | https://www.kaggle.com/datasets/bytadit/transactional-ecommerce | For study use only, as stated on the dataset page | _to fill_ | _to fill_ |

## Folder layout

```
data/
  README.md        this file (committed)
  load_data.py     loader script (committed)
  raw/             Kaggle CSVs (git-ignored, never committed)
```

## Start immediately: demo seed

No Kaggle download is needed to start building. `db/seed.sql` loads 2 synthetic customers and 6 orders, one per business-rule case (placed, shipped, delivered, cancelled, payment failed, another customer's order). Demo PIN: `1234`.

```
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed.sql
```

Use the seed for development and tests; load the Kaggle data into the shared database for the demo.

## How to get the data

1. Sign in to Kaggle and download the dataset zip from the URL above.
2. Unzip it into `data/raw/`. Expected files: `customer.csv`, `product.csv`, `transactions.csv`, `click_stream.csv`.
3. Confirm the column headers match the mapping in [`docs/DATABASE_SCHEMA.md`](../docs/DATABASE_SCHEMA.md#dataset-mapping). Report any difference before loading.

## How to load it

1. Set `DATABASE_URL` in `.env` (see `.env.example`).
2. Create the tables: `psql "$DATABASE_URL" -f db/schema.sql`
3. Load and clean: `python data/load_data.py`

The loader validates every file, reports rejected rows, applies the derived-field rules with a fixed seed, loads everything in one transaction, and can be re-run safely.

## Rules for handling data

- Raw files are never edited; every change is made by the loader script.
- Every derived field is documented in [`docs/DATABASE_SCHEMA.md`](../docs/DATABASE_SCHEMA.md#derived-fields).
- Tests use a small synthetic fixture and a separate test database, never the shared data.
- Personal data is masked in logs.
