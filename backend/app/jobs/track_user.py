import argparse

from dotenv import load_dotenv

from backend.app.logging_config import configure_logging
from backend.app.services.spotify_tracking_service import run_tracking_for_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Track Spotify plays for an existing profile.")
    parser.add_argument("--user-slug", required=True)
    args = parser.parse_args()
    load_dotenv()
    configure_logging()
    run_tracking_for_user(args.user_slug)


if __name__ == "__main__":
    main()
