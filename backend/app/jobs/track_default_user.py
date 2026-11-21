from backend.app.logging_config import configure_logging

from dotenv import load_dotenv

from backend.app.services.spotify_tracking_service import run_tracking_for_default_user


def main() -> None:
    load_dotenv()
    configure_logging()
    run_tracking_for_default_user()


if __name__ == "__main__":
    main()
