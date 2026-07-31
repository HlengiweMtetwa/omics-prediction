#!/usr/bin/env python3
"""Promote an already-registered user to the Administrator role.

Administrator is not self-service (see ai_wasteguard/permissions.py:
SELF_REGISTERABLE_ROLES). This script is the supported way to grant it -
run it from a trusted environment with direct access to the deployment's
database, not exposed through the web application.

Usage:
    python scripts/create_admin.py user@example.com
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_wasteguard.admin import UserNotFound, promote_user_to_administrator
from ai_wasteguard.db import get_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email address of the already-registered user to promote.")
    args = parser.parse_args()

    try:
        with get_session() as session:
            user = promote_user_to_administrator(session, args.email)
            print(f"OK: {user.email} ({user.full_name}) is now an Administrator.")
        return 0
    except UserNotFound as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
