import os
import glob
import pandas as pd
import numpy as np

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
        "artist_entropy": weekly["artist"].apply(shannon_entropy),
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
    df = add_time_features(df)

    weekly = engineer_weekly_features(df)
    monthly = engineer_monthly_features(df)
    seasonal = engineer_seasonal_features(df)
    peaks, valleys = identify_peak_periods(weekly)
    lifespan_stats = artist_lifespan_stats(df)

    weekly.to_csv(f"{output_prefix}_weekly_features.csv", index=False)
    monthly.to_csv(f"{output_prefix}_monthly_features.csv", index=False)
    seasonal.to_csv(f"{output_prefix}_seasonal_features.csv", index=False)
    peaks.to_csv(f"{output_prefix}_peak_diversity_weeks.csv", index=False)
    valleys.to_csv(f"{output_prefix}_low_diversity_weeks.csv", index=False)

    print("Feature engineering complete.")
    print("Artist lifespan stats:", lifespan_stats)


# -----------------------------
# CLI
# -----------------------------

if __name__ == "__main__":
    SCROBBLES_FOLDER = "odew2_scrobbles"
    OUTPUT_PREFIX = "odew2"

    run_feature_engineering(SCROBBLES_FOLDER, OUTPUT_PREFIX)