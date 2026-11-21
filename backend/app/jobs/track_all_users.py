import structlog

from backend.app.logging_config import configure_logging

from dotenv import load_dotenv

from backend.app.services.spotify_tracking_service import run_tracking_for_all_users


def main() -> None:
    load_dotenv()
    configure_logging()
    results = run_tracking_for_all_users()
    structlog.get_logger(__name__).info("spotify_sync_batch_completed", user_count=len(results), failed_count=sum("error" in result for result in results.values()))


if __name__ == "__main__":
    main()
