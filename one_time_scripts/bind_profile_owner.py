"""Bind a legacy profile to a person who has already signed in with Google."""

import argparse
import sys

from sqlalchemy.orm import sessionmaker

from backend.app.database import get_engine
from backend.app.services.auth_service import bind_profile_owner


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign a legacy profile to a Google-authenticated account.")
    parser.add_argument("user_slug", help="Existing profile slug, for example jacob")
    parser.add_argument("account_email", help="Verified Google email of an account that has signed in once")
    args = parser.parse_args()
    with sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)() as session:
        try:
            user = bind_profile_owner(session, user_slug=args.user_slug, account_email=args.account_email)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    print(f"Assigned profile {user.slug} to {args.account_email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
