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

    return response.json()["access_token"]

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
        print(f"Spotify search failed for '{artist_name}': {data}")
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