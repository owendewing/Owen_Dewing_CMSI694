# Last FM API Exploration (Time-Series Friendly)

API_KEY = "d064ed9e95ce09817ac0384d1c31c6c7"

import requests
from pprint import pprint
from datetime import datetime

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
USERNAME = "odew2"


def lastfm_request(params):
    params.update({
        "api_key": API_KEY,
        "format": "json"
    })
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()


# --- Profile info (static metadata) ---
def get_user_info():
    return lastfm_request({
        "method": "user.getInfo",
        "user": USERNAME
    })


# --- Recently played tracks (CORE DATASET) ---
def get_recent_tracks(limit=200, page=1):
    """
    Returns timestamped listening history.
    This is the backbone of preference evolution analysis.
    """
    return lastfm_request({
        "method": "user.getRecentTracks",
        "user": USERNAME,
        "limit": limit,
        "page": page
    })


# --- Parse recent tracks into structured time-series records ---
def parse_recent_tracks(raw):
    """
    Converts Last.fm response into analysis-ready records.
    """
    records = []

    tracks = raw["recenttracks"]["track"]
    for track in tracks:
        # Skip "now playing" track (no timestamp yet)
        if "@attr" in track and track["@attr"].get("nowplaying") == "true":
            continue

        unix_ts = int(track["date"]["uts"])
        records.append({
            "track": track["name"],
            "artist": track["artist"]["#text"],
            "album": track["album"]["#text"],
            "unix_timestamp": unix_ts,
            "datetime": datetime.utcfromtimestamp(unix_ts),
            "url": track["url"]
        })

    return records


# --- Pull multiple pages for deeper history ---
def collect_listening_history(pages=5, limit=200):
    """
    Collects several pages of listening history.
    Each page goes further back in time.
    """
    all_records = []

    for page in range(1, pages + 1):
        raw = get_recent_tracks(limit=limit, page=page)
        records = parse_recent_tracks(raw)
        all_records.extend(records)

    return all_records


# --- Example usage ---
if __name__ == "__main__":
    print("\n--- USER INFO ---")
    pprint(get_user_info())

    print("\n--- COLLECTING LISTENING HISTORY ---")
    history = collect_listening_history(pages=3)

    print(f"Collected {len(history)} timestamped listens\n")

    print("--- SAMPLE RECORDS ---")
    for row in history[:25]:
        print(
            f"{row['datetime']} | {row['artist']} – {row['track']}"
        )
