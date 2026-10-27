"""Create a free PostgreSQL database WITHOUT an account (Neon claimable Postgres).

The database lasts 72 hours unless you claim it into a Neon account using the
claim link this script prints. Unclaimed databases are limited to 100 MB.
Docs: https://neon.com/docs/reference/claimable-postgres

Usage (from the repository root):
    python scripts/create_instant_db.py           # create and write DATABASE_URL to .env
    python scripts/create_instant_db.py --print   # create and only print the URL

Share the printed DATABASE_URL with teammates privately (never commit it).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

NEON_NEW_URL = "https://neon.new/api/v1/database"
CLAIMABLE_BASE = "https://claimable.neon.tech/v1"


def create_with_neon_new(client: httpx.Client) -> dict:
    """Older one-call API: returns connection_string, claim_url, expires_at."""
    resp = client.post(NEON_NEW_URL, json={"ref": "team-logic-hcl"})
    resp.raise_for_status()
    data = resp.json()
    return {
        "database_url": data["connection_string"],
        "claim_url": data.get("claim_url", ""),
        "expires_at": data.get("expires_at", ""),
    }


def create_with_claimable(client: httpx.Client) -> dict:
    """Current REST flow: anonymous identity -> token -> credentials -> claim link."""
    ident = client.post(f"{CLAIMABLE_BASE}/agent/identity", json={
        "type": "anonymous", "capabilities": ["postgres"], "source": "team-logic-hcl",
    })
    ident.raise_for_status()
    ident_data = ident.json()
    project = ident_data["project"]

    token = client.post(f"{CLAIMABLE_BASE}/oauth2/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": ident_data["identity_assertion"],
        "resource": "https://claimable.neon.tech/",
    })
    token.raise_for_status()
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    creds = client.get(f"{CLAIMABLE_BASE}/projects/{project['id']}/credentials", headers=headers)
    creds.raise_for_status()

    claim_url = ""
    try:
        claim = client.post(f"{CLAIMABLE_BASE}/projects/{project['id']}/claim", headers=headers)
        claim.raise_for_status()
        claim_url = claim.json().get("verification_uri_complete", "")
    except httpx.HTTPError:
        pass  # the database still works without a claim link

    return {
        "database_url": creds.json()["database_url"],
        "claim_url": claim_url,
        "expires_at": project.get("expires_at", ""),
    }


def write_env(database_url: str) -> None:
    """Set DATABASE_URL in .env, creating .env from .env.example if needed."""
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
    elif ENV_EXAMPLE.exists():
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
    else:
        content = ""
    line = f"DATABASE_URL={database_url}"
    if re.search(r"^DATABASE_URL=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^DATABASE_URL=.*$", lambda _: line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + "\n" + line + "\n"
    ENV_FILE.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a no-signup Neon Postgres database.")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="Only print the URL; do not write .env")
    args = parser.parse_args()

    errors = []
    result = None
    with httpx.Client(timeout=30) as client:
        for name, create in (("claimable Postgres", create_with_claimable),
                             ("neon.new", create_with_neon_new)):
            try:
                result = create(client)
                print(f"Created a database with {name}.")
                break
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                errors.append(f"{name}: {exc}")

    if result is None:
        print("Could not create a database automatically:")
        for err in errors:
            print(f"  - {err}")
        print("Fallback: sign in at https://console.neon.tech (GitHub login works), create a "
              "project and paste its connection string into .env as DATABASE_URL.")
        return 1

    if args.print_only:
        print(f"DATABASE_URL={result['database_url']}")
    else:
        write_env(result["database_url"])
        print("Wrote DATABASE_URL to .env (git-ignored).")
    if result["expires_at"]:
        print(f"Expires at: {result['expires_at']} (unless claimed)")
    if result["claim_url"]:
        print(f"Claim it to keep it: {result['claim_url']}")
    print("Next: python scripts/init_db.py --seed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
