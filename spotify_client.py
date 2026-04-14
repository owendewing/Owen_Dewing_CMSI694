import requests
import base64
import os
import numpy as np
import time
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

def get_access_token():
    auth = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    ).decode()

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth}"
        },
        data={"grant_type": "client_credentials"}
    )

    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Spotify token response missing access_token")
    return token


def pick_best_spotify_image_url(images: list | None) -> str | None:
    if not images:
        return None
    best = max(images, key=lambda im: (im.get("width") or 0, im.get("height") or 0))
    url = (best.get("url") or "").strip()
    return url or None


def spotify_search_json(
    token: str, query: str, types: str, limit: int = 1
) -> dict | None:
    q = (query or "").strip()
    if not q:
        return None
    try:
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": q, "type": types, "limit": str(limit)},
            timeout=12,
        )
        if r.status_code == 429:
            wait = min(int(r.headers.get("Retry-After", "1")), 8)
            time.sleep(wait)
            r = requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "type": types, "limit": str(limit)},
                timeout=12,
            )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def spotify_artist_image_url(token: str, artist_name: str) -> str | None:
    data = spotify_search_json(token, artist_name.strip(), "artist", 1)
    if not data:
        return None
    items = (data.get("artists") or {}).get("items") or []
    if not items:
        return None
    return pick_best_spotify_image_url(items[0].get("images"))


def spotify_album_cover_url(token: str, artist: str, album: str) -> str | None:
    q = f"{album.strip()} {artist.strip()}".strip()
    data = spotify_search_json(token, q, "album", 1)
    if not data:
        return None
    items = (data.get("albums") or {}).get("items") or []
    if not items:
        return None
    return pick_best_spotify_image_url(items[0].get("images"))


def spotify_track_cover_url(token: str, artist: str, track: str) -> str | None:
    q = f"{track.strip()} {artist.strip()}".strip()
    data = spotify_search_json(token, q, "track", 1)
    if not data:
        return None
    items = (data.get("tracks") or {}).get("items") or []
    if not items:
        return None
    tr = items[0]
    album = tr.get("album") or {}
    url = pick_best_spotify_image_url(album.get("images"))
    if url:
        return url
    return pick_best_spotify_image_url(tr.get("images"))

def get_artist_genres(artist_name, token):

    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "q": artist_name,
            "type": "artist",
            "limit": 1
        }
    )

    data = response.json()

    # Handle API errors
    if "artists" not in data:
        # print(f"Spotify search failed for '{artist_name}': {data}")
        return []

    items = data["artists"]["items"]

    if not items:
        return []

    return items[0].get("genres", [])

import pandas as pd

CACHE_FILE = "artist_genre_cache.csv"


def load_genre_cache():
    if os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE)
        return dict(zip(df["artist"], df["genres"].apply(eval)))
    return {}


def save_genre_cache(cache):
    df = pd.DataFrame({
        "artist": list(cache.keys()),
        "genres": list(cache.values())
    })
    df.to_csv(CACHE_FILE, index=False)

def build_genre_map(df):

    token = get_access_token()

    cache = load_genre_cache()

    artists = df["artist"].unique()
    mapping = {}

    for artist in artists:

        if artist in cache:
            mapping[artist] = cache[artist]
            continue

        genres = get_artist_genres(artist, token)

        mapping[artist] = genres
        time.sleep(0.1)
        cache[artist] = genres

        time.sleep(0.1)

    save_genre_cache(cache)

    return mapping

def attach_genres(df, genre_map):

    df["genres"] = df["artist"].map(genre_map)

    df["primary_genre"] = df["genres"].apply(
        lambda g: g[0] if isinstance(g, list) and g else "unknown"
    )

    return df

def genre_entropy(series):
    p = series.value_counts(normalize=True)
    return -(p * np.log2(p)).sum()


if __name__ == "__main__":
    get_access_token()
    # print("Spotify API credentials OK (client credentials flow).")