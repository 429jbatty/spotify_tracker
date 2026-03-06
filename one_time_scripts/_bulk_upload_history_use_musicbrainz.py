# historical_bulk_upload.py

import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import album_metadata_service as meta

write_lock = threading.Lock()

file_path = "data/google_sheets_export/Albums Listened To - Sheet1.csv"
output_folder = "data/static_album_state_jsons/"
output_path = Path(output_folder) / "google_sheets_album_state_musicbrainz.json"

# ---------------------------
# CSV Loader
# ---------------------------


def load_csv_data_to_dict(file_path: str):
    data = pd.read_csv(file_path)
    data = data.iloc[:452, :11]
    result = []

    for _, row in data.iterrows():
        artist = row.iloc[0]
        albums = [i for i in row.iloc[1:].to_list() if pd.notna(i)]
        for album in albums:
            result.append((artist, album))

    return result


# ---------------------------
# Bulk Processor
# ---------------------------


def process_album(entry):
    artist, album = entry

    try:
        metadata = meta.get_album_metadata(artist, album)

        if metadata == {}:
            return ("unmatched", (artist, album))

        key = f"{metadata['artist']} - {metadata['name']}"
        return ("success", key, metadata)

    except Exception as e:
        return ("error", artist, album, str(e))


def run_bulk_upload():
    entries = load_csv_data_to_dict(file_path)

    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            album_state = json.load(f)
        album_state["last_checked"] = datetime.utcnow().isoformat()

    else:
        album_state = {
            "last_checked": datetime.utcnow().isoformat(),
            "completed_albums": {},
        }

    unmatched = []
    completed_keys = set(album_state["completed_albums"].keys())
    filtered_entries = []

    for artist, album in entries:
        key = f"{artist} - {album}"
        if key not in completed_keys:
            filtered_entries.append((artist, album))

    print(f"Loaded {len(completed_keys)} completed albums")
    print(f"Remaining: {len(filtered_entries)}")
    with ThreadPoolExecutor(max_workers=3) as executor:

        futures = [executor.submit(process_album, entry) for entry in filtered_entries]
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            with write_lock:
                if result[0] == "success":
                    _, key, metadata = result
                    album_state["completed_albums"][key] = metadata
                    completed_keys.add(key)
                elif result[0] == "unmatched":
                    _, entry = result
                    unmatched.append(entry)
                elif result[0] == "error":
                    _, artist, album, err = result
                    print(f"Error on {artist} - {album}: {err}")
                if i % 25 == 0:
                    with open(
                        output_path,
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump(album_state, f, indent=2)
    if unmatched:
        with open(
            Path(output_folder) / "unmatched_musicbrainz.csv", "w", encoding="utf-8"
        ) as f:
            for artist, album in unmatched:
                f.write(f"{artist},{album}\n")

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(album_state, f, indent=2)

    print(f"Wrote {len(album_state['completed_albums'])} albums.")


if __name__ == "__main__":
    run_bulk_upload()
