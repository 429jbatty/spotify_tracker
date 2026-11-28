import argparse
import sys

from backend.app.job_database import job_session

from backend.app.services.admin_user_service import delete_user_by_slug


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete a user and dependent rows.")
    parser.add_argument("user_slug", help="User slug to delete")
    args = parser.parse_args()

    with job_session(initialize=False) as session:
        try:
            result = delete_user_by_slug(
                session,
                user_slug=args.user_slug,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if not result.found:
        print(f"User not found: {args.user_slug}")
        return 1

    print(f"Deleted user: {result.deleted_user_slug} (id={result.deleted_user_id})")
    print(f"spotify_credentials: {result.deleted_spotify_credentials}")
    print(f"album_listens: {result.deleted_album_listens}")
    print(f"user_albums: {result.deleted_user_albums}")
    print(f"albums_in_progress: {result.deleted_albums_in_progress}")
    print(f"user_app_state: {result.deleted_user_app_state}")
    print(f"users: {result.deleted_users}")
    print(f"orphaned_albums_removed: {result.orphaned_albums_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
