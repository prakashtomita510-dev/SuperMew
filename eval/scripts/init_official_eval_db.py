from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth import get_password_hash  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402
from models import User  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the official eval database and seed eval users.")
    parser.add_argument("--username", default="latency_eval_user")
    parser.add_argument("--role", default="user")
    parser.add_argument(
        "--password",
        default=None,
        help="Optional password for the seeded user. Defaults to a generated placeholder.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set before initializing the official eval database.")

    init_db()
    password = args.password or f"eval-{secrets.token_urlsafe(12)}"

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            user = User(
                username=args.username,
                password_hash=get_password_hash(password),
                role=args.role,
            )
            db.add(user)
            db.commit()
            created = True
        else:
            created = False

    print(
        {
            "database_url": database_url,
            "username": args.username,
            "role": args.role,
            "created": created,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
