import os
import math
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

API_KEY = "d064ed9e95ce09817ac0384d1c31c6c7"
BASE_URL = "https://ws.audioscrobbler.com/2.0/"
PER_PAGE = 200


# -----------------------------
# Core Request (with retry)
# -----------------------------

def lastfm_request(params, retries=5, backoff=1.5):
    params.update({
        "api_key": API_KEY,
        "format": "json"
    })

    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code >= 500:
                wait = backoff ** attempt
                print(f"Server error {response.status_code}. Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise e

    raise RuntimeError("Max retries exceeded")


# -----------------------------
# User Metadata
# -----------------------------

def get_user_info(username):
    data = lastfm_request({
        "method": "user.getInfo",
        "user": username
    })

    registered = int(data["user"]["registered"]["unixtime"])
    playcount = int(data["user"]["playcount"])

    return registered, playcount


# -----------------------------
# Recent Tracks
# -----------------------------

def get_recent_tracks(username, page, from_ts, to_ts):
    return lastfm_request({
        "method": "user.getRecentTracks",
        "user": username,
        "limit": PER_PAGE,
        "page": page,
        "from": from_ts,
        "to": to_ts
    })


def parse_tracks(raw):
    records = []
    pacific = ZoneInfo("America/Los_Angeles")

    for track in raw["recenttracks"]["track"]:
        if "@attr" in track and track["@attr"].get("nowplaying") == "true":
            continue

        ts = int(track["date"]["uts"])
        dt = (
            datetime
            .fromtimestamp(ts, tz=timezone.utc)
            .astimezone(pacific)
        )

        records.append({
            "track": track["name"],
            "artist": track["artist"]["#text"],
            "album": track["album"]["#text"],
            "unix_timestamp": ts,
            "datetime": dt,
            "url": track["url"]
        })

    return records


# -----------------------------
# Yearly Ingestion
# -----------------------------

def collect_year(username, year):
    from_ts = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    to_ts = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    # First call to get total pages
    first = get_recent_tracks(username, 1, from_ts, to_ts)
    total_pages = int(first["recenttracks"]["@attr"]["totalPages"])

    print(f"  {year}: {total_pages} pages")

    all_records = parse_tracks(first)

    for page in range(2, total_pages + 1):
        raw = get_recent_tracks(username, page, from_ts, to_ts)
        all_records.extend(parse_tracks(raw))
        time.sleep(0.25)

    return all_records


# -----------------------------
# Main Pipeline
# -----------------------------

def run_yearly_ingestion(username):
    registered_ts, total_scrobbles = get_user_info(username)
    start_year = datetime.fromtimestamp(registered_ts).year
    end_year = datetime.now().year

    output_dir = f"{username}_scrobbles"
    os.makedirs(output_dir, exist_ok=True)

    print(f"User registered in {start_year}")
    print(f"Total scrobbles: {total_scrobbles}")
    print(f"Saving yearly CSVs to: {output_dir}/")

    for year in range(start_year, end_year + 1):
        print(f"\nFetching {year}...")
        records = collect_year(username, year)

        if not records:
            print("  No listens this year.")
            continue

        df = pd.DataFrame(records)
        df.sort_values("datetime", inplace=True)

        out_path = os.path.join(output_dir, f"{username}_{year}.csv")
        df.to_csv(out_path, index=False)

        print(f"  Saved {len(df)} listens")



if __name__ == "__main__":
    USERNAME = "odew2"
    run_yearly_ingestion(USERNAME)