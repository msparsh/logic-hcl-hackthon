"""Create the database tables, and optionally load the demo seed.

Usage (from the repository root):
    python scripts/init_db.py            # create schema only
    python scripts/init_db.py --seed     # create schema and load db/seed.sql
    python scripts/init_db.py --reset --seed   # drop app/raw schemas first

No psql client is needed. Uses DATABASE_URL from .env (or --url).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

SCHEMA_FILE = ROOT / "db" / "schema.sql"
SEED_FILE = ROOT / "db" / "seed.sql"


def to_libpq_url(url: str) -> str:
    """psycopg wants plain postgresql:// (no SQLAlchemy driver suffix)."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1).strip()


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Run a whole .sql file. Without parameters, psycopg sends it as one script."""
    conn.execute(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the Team Logic database schema.")
    parser.add_argument("--url", help="Database URL (default: DATABASE_URL from .env)")
    parser.add_argument("--seed", action="store_true", help="Load db/seed.sql demo data")
    parser.add_argument("--reset", action="store_true", help="Drop the app and raw schemas first")
    args = parser.parse_args()

    url = to_libpq_url(args.url or get_settings().database_url)
    if url.startswith("sqlite"):
        print("DATABASE_URL points to SQLite. Set a PostgreSQL URL in .env first.")
        return 1

    try:
        with psycopg.connect(url, autocommit=True, connect_timeout=15) as conn:
            if args.reset:
                conn.execute("DROP SCHEMA IF EXISTS app CASCADE; DROP SCHEMA IF EXISTS raw CASCADE;")
                print("Dropped schemas app and raw.")
            run_sql_file(conn, SCHEMA_FILE)
            print(f"Schema ready ({SCHEMA_FILE.relative_to(ROOT)}).")
            if args.seed:
                run_sql_file(conn, SEED_FILE)
                print(f"Seed loaded ({SEED_FILE.relative_to(ROOT)}). Demo login: alice@example.com / 1234")
            counts = conn.execute(
                "SELECT (SELECT count(*) FROM app.customers), (SELECT count(*) FROM app.orders)"
            ).fetchone()
            print(f"Rows now: customers={counts[0]}, orders={counts[1]}")
    except psycopg.OperationalError as exc:
        print(f"Could not connect to the database: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
