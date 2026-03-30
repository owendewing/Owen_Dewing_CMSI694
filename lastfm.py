import os
import math
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed


API_KEY = "d064ed9e95ce09817ac0384d1c31c6c7"
BASE_URL = "https://ws.audioscrobbler.com/2.0/"
PER_PAGE = 200

session = requests.Session()

def lastfm_request(params, retries=5, backoff=1.5):
    params.update({
        "api_key": API_KEY,
        "format": "json"
    })

    for attempt in range(retries):
        try:
            response = session.get(BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if response.status_code >= 500:
                wait = backoff ** attempt
                # print(f"Server error {response.status_code}. Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise e

        except requests.exceptions.RequestException as e:
            # catches timeouts, connection errors, etc.
            wait = backoff ** attempt
            # print(f"Request failed ({e}). Retrying in {wait:.1f}s...")
            time.sleep(wait)

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

    first = get_recent_tracks(username, 1, from_ts, to_ts)
    total_pages = int(first["recenttracks"]["@attr"]["totalPages"])

    # print(f"  {year}: {total_pages} pages")

    all_records = parse_tracks(first)

    def fetch_page(page):
        raw = get_recent_tracks(username, page, from_ts, to_ts)
        return parse_tracks(raw)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_page, page)
            for page in range(2, total_pages + 1)
        ]

        for future in as_completed(futures):
            all_records.extend(future.result())

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

    # print(f"User registered in {start_year}")
    # print(f"Total scrobbles: {total_scrobbles}")
    # print(f"Saving yearly CSVs to: {output_dir}/")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(collect_year, username, year): year
            for year in range(start_year, end_year + 1)
        }

        for future in as_completed(futures):
            year = futures[future]
            # print(f"\nFinished fetching {year}")

            records = future.result()

            if not records:
                # print(f"  {year}: No listens.")
                continue

            df = pd.DataFrame(records)
            df.sort_values("datetime", inplace=True)

            out_path = os.path.join(output_dir, f"{username}_{year}.csv")
            df.to_csv(out_path, index=False)

            # print(f"  {year}: Saved {len(df)} listens")
        



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Last.fm scrobbles by year.")
    parser.add_argument(
        "--username",
        required=True,
        help="Last.fm username (output goes to {username}_scrobbles/)",
    )
    args = parser.parse_args()

    start = time.time()
    run_yearly_ingestion(args.username)
    end = time.time()

    # print(f"\nTotal runtime: {end - start:.2f} seconds")