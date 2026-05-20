import logging

from dotenv import load_dotenv

from backend.app.services.spotify_tracking_service import run_tracking_for_default_user


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    run_tracking_for_default_user()


if __name__ == "__main__":
    main()
