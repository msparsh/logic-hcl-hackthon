"""Run one SQL statement on the project database and print the result as a table.

    python scripts/sql.py "SELECT status, count(*) FROM app.orders GROUP BY status"
    python scripts/sql.py "ALTER TABLE app.customers ADD COLUMN phone TEXT"

Uses DATABASE_URL from .env. A statement that changes data or tables is
committed; if it fails, nothing is changed and the database error is shown.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app.db import get_engine  # noqa: E402


def show(columns: list[str], rows: list) -> None:
    cells = [[("" if v is None else str(v))[:60] for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    print(" | ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in cells:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))
    print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    try:
        with get_engine().begin() as conn:
            result = conn.execute(text(sys.argv[1]))
            if result.returns_rows:
                show(list(result.keys()), result.fetchall())
            else:
                print(f"Done. Rows affected: {result.rowcount if result.rowcount >= 0 else 0}")
    except DBAPIError as exc:
        print("Refused by the database, nothing changed:")
        print("  " + str(exc.orig).strip().splitlines()[0])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
