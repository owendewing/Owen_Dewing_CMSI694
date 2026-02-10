import requests
from datetime import datetime
import pandas as pd

API_KEY = "d064ed9e95ce09817ac0384d1c31c6c7"
BASE_URL = "https://ws.audioscrobbler.com/2.0/"


def lastfm_request(params):
    params.update({
        "api_key": API_KEY,
        "format": "json"
    })
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()


def get_recent_tracks(username, limit=200, page=1, from_ts=None, to_ts=None):
    params = {
        "method": "user.getRecentTracks",
        "user": username,
        "limit": limit,
        "page": page
    }

    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    return lastfm_request(params)


def parse_recent_tracks(raw):
    records = []
    tracks = raw["recenttracks"]["track"]

    for track in tracks:
        # Skip "now playing"
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


def collect_listening_history(username, pages=5, limit=200, from_ts=None, to_ts=None):
    all_records = []

    for page in range(1, pages + 1):
        raw = get_recent_tracks(
            username=username,
            limit=limit,
            page=page,
            from_ts=from_ts,
            to_ts=to_ts
        )
        records = parse_recent_tracks(raw)
        all_records.extend(records)

    return all_records


def save_to_csv(records, filename):
    df = pd.DataFrame(records)
    df.sort_values("datetime", inplace=True)
    df.to_csv(filename, index=False)
    return df


if __name__ == "__main__":
    USERNAME = "odew2"
    PAGES = 8     

    history = collect_listening_history(USERNAME, pages=PAGES, from_ts=1767225600, to_ts=1769903999)

    df = save_to_csv(history, f"{USERNAME}_listening_history.csv")

    print(f"Collected {len(df)} listens")
    print(df.head())
