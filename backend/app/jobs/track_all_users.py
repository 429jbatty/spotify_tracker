import logging

from dotenv import load_dotenv

from backend.app.services.spotify_tracking_service import run_tracking_for_all_users


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    results = run_tracking_for_all_users()
    logging.info("Spotify tracking results: %s", results)


if __name__ == "__main__":
    main()
