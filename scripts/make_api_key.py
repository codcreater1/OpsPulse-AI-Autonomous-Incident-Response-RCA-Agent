"""Generate an API key for one client and the API_KEYS entry that authorises it.

    python -m scripts.make_api_key alice reviewer

Give the printed key to the client once (it is not stored anywhere); put the printed entry into API_KEYS.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import secrets

ROLES = ("reporter", "reviewer", "admin")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="identity name, e.g. alertmanager or alice")
    parser.add_argument("role", choices=ROLES)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.name):
        parser.error("name may contain letters, digits, '_', '.', '-' (max 100)")
    key = secrets.token_urlsafe(32)
    entry = f"{args.name}:{args.role}:{hashlib.sha256(key.encode()).hexdigest()}"
    print(f"API key for {args.name} (shown once, give it to the client):\n  {key}\n")
    print(f"Append to API_KEYS (comma-separated):\n  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
