"""Pre-authorize a Google email to claim an existing profile on first sign-in."""

import argparse
import sys

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.services.auth_service import prebind_profile_owner


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Pre-authorize a Google email to own an existing profile."
    )
    parser.add_argument("user_slug", help="Existing profile slug, for example jacob")
    parser.add_argument("account_email", help="Google email allowed to claim the profile")
    args = parser.parse_args()

    with sessionmaker(bind=create_schema(), autoflush=False, autocommit=False)() as session:
        try:
            user = prebind_profile_owner(
                session,
                user_slug=args.user_slug,
                account_email=args.account_email,
            )
            bound_slug = user.slug
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print(f"Pre-authorized {args.account_email} to claim profile {bound_slug} on Google sign-in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
