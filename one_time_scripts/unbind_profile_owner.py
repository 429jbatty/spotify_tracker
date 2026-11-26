"""Remove the Google-account ownership binding from a profile."""

import argparse
import sys

from dotenv import load_dotenv

from backend.app.job_database import job_session
from backend.app.services.auth_service import unbind_profile_owner


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Remove a profile's Google-account ownership binding without deleting either record."
    )
    parser.add_argument("user_slug", help="Existing profile slug, for example jacob")
    args = parser.parse_args()

    with job_session() as session:
        try:
            user = unbind_profile_owner(session, user_slug=args.user_slug)
            unbound_slug = user.slug
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print(f"Removed the ownership binding from profile {unbound_slug}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
