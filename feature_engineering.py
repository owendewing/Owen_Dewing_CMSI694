import os
import glob
import pandas as pd
import numpy as np
from spotify_client import build_genre_map, attach_genres

# -----------------------------
# Load & Time Features
# -----------------------------

def load_yearly_scrobbles(folder_path):
    csv_files = sorted(glob.glob(os.path.join(folder_path, "*.csv")))

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {folder_path}")

    dfs = []
    for path in csv_files:
        df = pd.read_csv(path)
        dfs.append(df)

    full_df = pd.concat(dfs, ignore_index=True)

    # 🔧 FORCE datetime back to proper dtype
    full_df["datetime"] = pd.to_datetime(
        full_df["datetime"],
        utc=True,
        errors="coerce"
    )

    # Optional: drop bad rows (should be none)
    full_df = full_df.dropna(subset=["datetime"])

    full_df.sort_values("datetime", inplace=True)

    return full_df


LISTENING_HISTORY_COLS = [
    "track",
    "artist",
    "album",
    "unix_timestamp",
    "datetime",
    "url",
]


def export_listening_history_csv(raw_df: pd.DataFrame, output_prefix: str) -> None:
    """
    Single merged scrobble list for the dashboard (Top stuff time windows).
    Rewritten on every pipeline run so it stays in sync with {prefix}_scrobbles/*.csv.
    """
    cols = [c for c in LISTENING_HISTORY_COLS if c in raw_df.columns]
    if len(cols) < 4:
        return
    path = f"{output_prefix}_listening_history.csv"
    raw_df[cols].sort_values("datetime").to_csv(path, index=False)


def add_time_features(df):
    df["week"] = df["datetime"].dt.to_period("W").astype(str)
    df["month"] = df["datetime"].dt.to_period("M").astype(str)
    df["year"] = df["datetime"].dt.year
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.day_name()
    df["is_weekend"] = df["datetime"].dt.weekday >= 5

    def season(month):
        if month in [12, 1, 2]:
            return "winter"
        if month in [3, 4, 5]:
            return "spring"
        if month in [6, 7, 8]:
            return "summer"
        return "fall"

    df["season"] = df["datetime"].dt.month.apply(season)

    return df


# -----------------------------
# Helper Metrics
# -----------------------------

def shannon_entropy(series):
    p = series.value_counts(normalize=True)
    return -(p * np.log2(p)).sum()


def top_share(series):
    return series.value_counts(normalize=True).iloc[0]


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0


# -----------------------------
# Weekly Evolution Features
# -----------------------------

def engineer_weekly_features(df):
    weekly = df.groupby("week")

    features = pd.DataFrame({
        "total_listens": weekly.size(),
        "unique_artists": weekly["artist"].nunique(),
        "unique_tracks": weekly["track"].nunique(),
        "unique_genres": weekly["primary_genre"].nunique(),
        "artist_entropy": weekly["artist"].apply(shannon_entropy),
        "genre_entropy": weekly["primary_genre"].apply(shannon_entropy),
        "top_artist_share": weekly["artist"].apply(top_share),
        "avg_listen_hour": weekly["hour"].mean(),
        "listen_hour_std": weekly["hour"].std(),
        "weekend_ratio": weekly["is_weekend"].mean()
    })

    # ---- Discovery velocity ----
    artist_sets = weekly["artist"].apply(set)
    features["new_artists"] = artist_sets.diff().apply(
        lambda x: len(x) if isinstance(x, set) else 0
    )
    features["new_artist_rate"] = (
        features["new_artists"] / features["unique_artists"]
    )

    # ---- Preference stability ----
    features["artist_stability"] = [
        jaccard(prev, curr) if i > 0 else np.nan
        for i, (prev, curr) in enumerate(
            zip(artist_sets.shift(), artist_sets)
        )
    ]


    # ---- Diversity acceleration ----
    features["entropy_delta"] = features["artist_entropy"].diff()

    # ---- Taste shock detection ----
    features["taste_shock"] = features["artist_stability"] < 0.3

    return features.reset_index()


# -----------------------------
# Seasonal Preference Shifts
# -----------------------------

def engineer_seasonal_features(df):
    seasonal = df.groupby("season")

    features = pd.DataFrame({
        "total_listens": seasonal.size(),
        "unique_artists": seasonal["artist"].nunique(),
        "artist_entropy": seasonal["artist"].apply(shannon_entropy),
        "top_artist_share": seasonal["artist"].apply(top_share)
    })

    return features.reset_index()


def engineer_seasonal_timeseries(df):
    """Per calendar year + season (winter/spring/summer/fall) for longitudinal dashboards."""
    df = df.copy()
    df["cal_year"] = df["datetime"].dt.year
    seasonal = df.groupby(["cal_year", "season"], sort=False)
    features = pd.DataFrame({
        "total_listens": seasonal.size(),
        "unique_artists": seasonal["artist"].nunique(),
        "unique_genres": seasonal["primary_genre"].nunique(),
        "artist_entropy": seasonal["artist"].apply(shannon_entropy),
        "genre_entropy": seasonal["primary_genre"].apply(shannon_entropy),
        "top_artist_share": seasonal["artist"].apply(top_share),
        "avg_listen_hour": seasonal["hour"].mean(),
    })
    out = features.reset_index()
    out.rename(columns={"cal_year": "year"}, inplace=True)
    season_order = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}
    out["_so"] = out["season"].map(season_order)
    out.sort_values(["year", "_so"], inplace=True)
    out.drop(columns=["_so"], inplace=True)
    return out.reset_index(drop=True)


def engineer_yearly_features(df):
    yearly = df.groupby("year", sort=True)
    features = pd.DataFrame({
        "total_listens": yearly.size(),
        "unique_artists": yearly["artist"].nunique(),
        "unique_tracks": yearly["track"].nunique(),
        "unique_genres": yearly["primary_genre"].nunique(),
        "artist_entropy": yearly["artist"].apply(shannon_entropy),
        "genre_entropy": yearly["primary_genre"].apply(shannon_entropy),
        "top_artist_share": yearly["artist"].apply(top_share),
        "avg_listen_hour": yearly["hour"].mean(),
        "weekend_ratio": yearly["is_weekend"].mean(),
    })
    return features.reset_index()


# -----------------------------
# Peak / Valley Detection
# -----------------------------

def identify_peak_periods(weekly_features, top_n=5):
    peaks = weekly_features.nlargest(top_n, "artist_entropy")[
        ["week", "artist_entropy"]
    ]
    valleys = weekly_features.nsmallest(top_n, "artist_entropy")[
        ["week", "artist_entropy"]
    ]

    return peaks, valleys

from collections import Counter

def build_genre_transition_matrix(df):

    genres = df["primary_genre"].tolist()

    transitions = Counter()

    for i in range(len(genres) - 1):
        pair = (genres[i], genres[i+1])
        transitions[pair] += 1

    matrix = pd.DataFrame(
        [(a, b, c) for (a, b), c in transitions.items()],
        columns=["from_genre", "to_genre", "count"]
    )

    matrix["probability"] = (
        matrix.groupby("from_genre")["count"]
        .transform(lambda x: x / x.sum())
    )

    return matrix

# -----------------------------
# Artist Lifespan Proxy
# -----------------------------

def artist_lifespan_stats(df):
    first_last = (
        df.groupby("artist")["datetime"]
        .agg(["min", "max", "count"])
        .reset_index()
    )

    first_last["lifespan_days"] = (
        first_last["max"] - first_last["min"]
    ).dt.days

    return {
        "avg_artist_lifespan_days": first_last["lifespan_days"].mean(),
        "median_artist_lifespan_days": first_last["lifespan_days"].median()
    }


# -----------------------------
# Monthly Long-Term Evolution
# -----------------------------

def engineer_monthly_features(df):
    monthly = df.groupby("month")

    features = pd.DataFrame({
        "total_listens": monthly.size(),
        "unique_artists": monthly["artist"].nunique(),
        "artist_entropy": monthly["artist"].apply(shannon_entropy),
        "top_artist_share": monthly["artist"].apply(top_share),
        "avg_listen_hour": monthly["hour"].mean()
    })

    features["entropy_trend"] = features["artist_entropy"].diff()

    return features.reset_index()


# -----------------------------
# Main Pipeline
# -----------------------------

def run_feature_engineering(scrobbles_folder, output_prefix):
    df = load_yearly_scrobbles(scrobbles_folder)
    export_listening_history_csv(df, output_prefix)

    genre_map = build_genre_map(df)

    df = attach_genres(df, genre_map)

    df = add_time_features(df)

    weekly = engineer_weekly_features(df)
    monthly = engineer_monthly_features(df)
    seasonal = engineer_seasonal_features(df)
    seasonal_ts = engineer_seasonal_timeseries(df)
    yearly = engineer_yearly_features(df)
    peaks, valleys = identify_peak_periods(weekly)
    lifespan_stats = artist_lifespan_stats(df)

    weekly.to_csv(f"{output_prefix}_weekly_features.csv", index=False)
    monthly.to_csv(f"{output_prefix}_monthly_features.csv", index=False)
    seasonal.to_csv(f"{output_prefix}_seasonal_features.csv", index=False)
    seasonal_ts.to_csv(f"{output_prefix}_seasonal_timeseries.csv", index=False)
    yearly.to_csv(f"{output_prefix}_yearly_features.csv", index=False)
    peaks.to_csv(f"{output_prefix}_peak_diversity_weeks.csv", index=False)
    valleys.to_csv(f"{output_prefix}_low_diversity_weeks.csv", index=False)

    transition_matrix = build_genre_transition_matrix(df)

    transition_matrix.to_csv(
        f"{output_prefix}_genre_transition_matrix.csv",
        index=False
)

    # print("Feature engineering complete.")
    # print("Artist lifespan stats:", lifespan_stats)


# -----------------------------
# CLI
# -----------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build listening features from scrobble CSVs.")
    parser.add_argument(
        "--scrobbles-folder",
        required=True,
        help="Folder containing yearly CSV files from lastfm.py",
    )
    parser.add_argument(
        "--output-prefix",
        required=True,
        help="Prefix for output CSVs (e.g. odew2 -> odew2_weekly_features.csv)",
    )
    args = parser.parse_args()

    run_feature_engineering(args.scrobbles_folder, args.output_prefix)