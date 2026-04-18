import logging

import metadata_refresh_service as refresh_service
import utils

# Edit these values, then run:
# ./.venv/bin/python refresh_metadata.py

REFRESH_ALL = False

ALBUM_KEYS = ["Bridget St John - Songs For The Gentle Man"]

ALBUMS = [
    # {
    #     "artist": "Bridget St. John",
    #     "album": "Songs for the Gentle Man",
    #     "spotify_url": None,
    # },
]

CONTINUE_ON_ERROR = True


def _print_summary(results):
    refreshed = [result for result in results if result.refreshed]
    failed = [result for result in results if not result.refreshed]

    print(f"Refreshed: {len(refreshed)}")
    print(f"Failed: {len(failed)}")

    for result in refreshed:
        print(f"[OK] {result.key}")

    for result in failed:
        print(f"[FAILED] {result.key}: {result.error}")


def refresh_configured_albums():
    state = utils.load_state()
    results = []

    if REFRESH_ALL:
        results = refresh_service.refresh_all_albums_in_state(
            state,
            continue_on_error=CONTINUE_ON_ERROR,
        )
    else:
        for key in ALBUM_KEYS:
            try:
                result = refresh_service.refresh_album_in_state(state, key=key)
            except Exception as exc:
                if not CONTINUE_ON_ERROR:
                    raise
                results.append(
                    refresh_service.RefreshResult(
                        key=key,
                        artist="",
                        album="",
                        refreshed=False,
                        error=str(exc),
                    )
                )
            else:
                results.append(result)

        for album_request in ALBUMS:
            artist = album_request["artist"]
            album = album_request["album"]
            spotify_url = album_request.get("spotify_url")
            key = f"{artist} - {album}"

            try:
                result = refresh_service.refresh_album_in_state(
                    state,
                    artist=artist,
                    album=album,
                    spotify_url=spotify_url,
                )
            except Exception as exc:
                if not CONTINUE_ON_ERROR:
                    raise
                results.append(
                    refresh_service.RefreshResult(
                        key=key,
                        artist=artist,
                        album=album,
                        refreshed=False,
                        error=str(exc),
                    )
                )
            else:
                results.append(result)

    utils.save_state(state)
    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)

    if not REFRESH_ALL and not ALBUM_KEYS and not ALBUMS:
        raise SystemExit("Set REFRESH_ALL=True or add entries to ALBUM_KEYS/ALBUMS.")

    results = refresh_configured_albums()
    _print_summary(results)


if __name__ == "__main__":
    main()
