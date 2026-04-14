"""
Build JSON payloads for the listening analytics dashboard from pipeline CSVs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _read_csv_optional(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def _df_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _safe_float(x) -> float | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _weekly_month_period(weekly: pd.DataFrame) -> pd.Series:
    if "week_start" in weekly.columns:
        ws = weekly["week_start"]
    else:
        ws = weekly["week"].astype(str).str.split("/").str[0]
    dt = pd.to_datetime(ws, errors="coerce")
    return dt.dt.to_period("M").astype(str)


def _discovery_by_month(weekly: pd.DataFrame) -> pd.DataFrame:
    w = weekly.copy()
    w["_month"] = _weekly_month_period(w)
    w = w[w["_month"].notna() & (w["_month"] != "NaT")]
    if "new_artists" not in w.columns:
        return pd.DataFrame(columns=["month", "new_artists"])
    g = w.groupby("_month", sort=True, as_index=False)["new_artists"].sum()
    g.rename(columns={"_month": "month"}, inplace=True)
    return g


def _trends_monthly_payload(
    monthly: pd.DataFrame | None, weekly: pd.DataFrame | None
) -> list[dict[str, Any]]:
    if monthly is None or monthly.empty:
        return []
    m = monthly.sort_values("month").copy()
    disc = (
        _discovery_by_month(weekly)
        if weekly is not None and not weekly.empty
        else pd.DataFrame()
    )
    if not disc.empty:
        m = m.merge(disc, on="month", how="left")
    else:
        m["new_artists"] = 0
    m["new_artists"] = m["new_artists"].fillna(0).astype(int)
    tl = m["total_listens"].replace(0, np.nan)
    m["discovery_rate"] = (m["new_artists"] / tl).fillna(0.0)
    out = m[
        [
            "month",
            "total_listens",
            "artist_entropy",
            "new_artists",
            "discovery_rate",
        ]
    ].copy()
    return json.loads(out.to_json(orient="records", date_format="iso"))


def _weekend_split_payload(weekly: pd.DataFrame | None, tail_weeks: int = 52) -> dict[str, Any] | None:
    if weekly is None or weekly.empty or "weekend_ratio" not in weekly.columns:
        return None
    w = weekly.sort_values("week").tail(tail_weeks)
    r = float(w["weekend_ratio"].mean())
    r = min(max(r, 0.0), 1.0)
    return {
        "weekendPercent": round(r * 100, 1),
        "weekdayPercent": round((1.0 - r) * 100, 1),
        "detail": f"Estimated from your last {len(w)} weeks: share of scrobbles on Saturday–Sunday vs Monday–Friday.",
    }


def _empty_top_window(label: str) -> dict[str, Any]:
    return {
        "topArtists": [],
        "topAlbums": [],
        "topTracks": [],
        "windowLabel": label,
    }


def _load_listening_history_df(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    need = {"artist", "track", "album", "datetime"}
    if not need.issubset(set(df.columns)):
        return None
    df = df.dropna(subset=["artist", "track", "album", "datetime"])
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    df = df.dropna(subset=["datetime"])
    if df.empty:
        return None
    return df


def _tops_from_scrobble_df(df: pd.DataFrame, top_n: int) -> dict[str, Any]:
    if df.empty:
        return {"topArtists": [], "topAlbums": [], "topTracks": []}
    artists = (
        df["artist"]
        .value_counts()
        .head(top_n)
        .rename_axis("name")
        .reset_index(name="plays")
    )
    albums = (
        df.groupby(["artist", "album"], as_index=False)
        .size()
        .nlargest(top_n, "size")
        .rename(columns={"size": "plays"})
    )
    tracks = (
        df.groupby(["artist", "track"], as_index=False)
        .size()
        .nlargest(top_n, "size")
        .rename(columns={"size": "plays"})
    )
    return {
        "topArtists": [
            {"name": str(r["name"]), "plays": int(r["plays"]), "imageUrl": None}
            for _, r in artists.iterrows()
        ],
        "topAlbums": [
            {
                "artist": str(r["artist"]),
                "album": str(r["album"]),
                "plays": int(r["plays"]),
                "coverUrl": None,
            }
            for _, r in albums.iterrows()
        ],
        "topTracks": [
            {
                "artist": str(r["artist"]),
                "track": str(r["track"]),
                "plays": int(r["plays"]),
                "coverUrl": None,
            }
            for _, r in tracks.iterrows()
        ],
    }


def _spotify_client_token() -> str | None:
    try:
        from spotify_client import CLIENT_ID, CLIENT_SECRET, get_access_token

        if not CLIENT_ID or not CLIENT_SECRET:
            return None
        return get_access_token()
    except Exception:
        return None


def _cache_key_artist(name: str) -> str:
    return f"a::{name.strip().lower()}"


def _cache_key_album(artist: str, album: str) -> str:
    return f"al::{artist.strip().lower()}||{album.strip().lower()}"


def _cache_key_track(artist: str, track: str) -> str:
    return f"tr::{artist.strip().lower()}||{track.strip().lower()}"


def _fill_spotify_art_cache(
    windows: list[dict[str, Any]], token: str | None, cache: dict[str, str | None]
) -> None:
    if not token:
        return
    try:
        from spotify_client import (
            spotify_album_cover_url,
            spotify_artist_image_url,
            spotify_track_cover_url,
        )
    except Exception:
        return

    artists: set[str] = set()
    albums: set[tuple[str, str]] = set()
    tracks: set[tuple[str, str]] = set()
    for w in windows:
        for row in w.get("topArtists") or []:
            if row.get("name"):
                artists.add(str(row["name"]))
        for row in w.get("topAlbums") or []:
            if row.get("artist") and row.get("album"):
                albums.add((str(row["artist"]), str(row["album"])))
        for row in w.get("topTracks") or []:
            if row.get("artist") and row.get("track"):
                tracks.add((str(row["artist"]), str(row["track"])))

    for name in sorted(artists):
        k = _cache_key_artist(name)
        if k not in cache:
            cache[k] = spotify_artist_image_url(token, name)
            time.sleep(0.05)

    for artist, album in sorted(albums):
        k = _cache_key_album(artist, album)
        if k not in cache:
            cache[k] = spotify_album_cover_url(token, artist, album)
            time.sleep(0.05)

    for artist, track in sorted(tracks):
        k = _cache_key_track(artist, track)
        if k not in cache:
            cache[k] = spotify_track_cover_url(token, artist, track)
            time.sleep(0.05)


def _apply_spotify_art_cache(windows: list[dict[str, Any]], cache: dict[str, str | None]) -> None:
    for w in windows:
        for row in w.get("topArtists") or []:
            name = row.get("name")
            if name:
                row["imageUrl"] = cache.get(_cache_key_artist(str(name)))
        for row in w.get("topAlbums") or []:
            ar, al = row.get("artist"), row.get("album")
            if ar and al:
                row["coverUrl"] = cache.get(_cache_key_album(str(ar), str(al)))
        for row in w.get("topTracks") or []:
            ar, tr = row.get("artist"), row.get("track")
            if ar and tr:
                row["coverUrl"] = cache.get(_cache_key_track(str(ar), str(tr)))


def _build_top_stuff_by_windows(history_path: Path, top_n: int = 8) -> dict[str, Any]:
    empty = {
        "week": _empty_top_window("Last 7 days (no scrobbles in this window)."),
        "month": _empty_top_window("Last 30 days (no scrobbles in this window)."),
        "year": _empty_top_window("Last 365 days (no scrobbles in this window)."),
    }
    df = _load_listening_history_df(history_path)
    if df is None or df.empty:
        return empty

    anchor = df["datetime"].max()
    anchor_d = anchor.date().isoformat()

    def windowed(days: int, label: str) -> dict[str, Any]:
        sub = df[df["datetime"] >= anchor - pd.Timedelta(days=days)]
        tops = _tops_from_scrobble_df(sub, top_n)
        tops["windowLabel"] = f"{label} (through {anchor_d})."
        return tops

    week = windowed(7, "Last 7 days")
    month = windowed(30, "Last 30 days")
    year = windowed(365, "Last 365 days")

    cache: dict[str, str | None] = {}
    token = _spotify_client_token()
    _fill_spotify_art_cache([week, month, year], token, cache)
    _apply_spotify_art_cache([week, month, year], cache)

    return {"week": week, "month": month, "year": year}


def _build_personality_cards(
    weekly: pd.DataFrame | None,
    monthly: pd.DataFrame | None,
    seasonal_profile: pd.DataFrame | None,
    yearly: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    if monthly is None or monthly.empty:
        return cards

    m = monthly.sort_values("month")
    last = m.iloc[-1]
    last_month = str(last["month"])
    variety = _safe_float(last.get("artist_entropy"))
    share = _safe_float(last.get("top_artist_share"))

    ent_series = m["artist_entropy"].dropna()
    if len(ent_series) >= 2 and variety is not None:
        q50 = float(ent_series.median())
        q75 = float(ent_series.quantile(0.75))
        if variety >= q75:
            cards.append(
                {
                    "headline": "You're a high-variety listener",
                    "detail": f"In {last_month}, your mix of artists was wider than about three quarters of your other months. "
                    "Higher variety means more different artists in the same number of plays.",
                    "kind": "highlight",
                }
            )
        elif variety >= q50:
            cards.append(
                {
                    "headline": "You balance favorites with variety",
                    "detail": f"In {last_month}, your artist mix sat around the middle of your own history — not too narrow, not maximal spread.",
                    "kind": "info",
                }
            )
        else:
            cards.append(
                {
                    "headline": "You've been leaning into favorites",
                    "detail": f"In {last_month}, fewer artists accounted for most of your plays compared with your typical month.",
                    "kind": "info",
                }
            )

    if weekly is not None and not weekly.empty and "new_artists" in weekly.columns:
        w = weekly.copy()
        w["_month"] = _weekly_month_period(w)
        w = w[w["_month"].notna() & (w["_month"] != "NaT")]
        by_m = w.groupby("_month", sort=True)["new_artists"].sum()
        if last_month in by_m.index:
            discovered = int(by_m.loc[last_month])
            prior = by_m[by_m.index < last_month]
            if len(prior) >= 3:
                med = float(prior.median())
                if discovered >= med * 1.25 and discovered >= 5:
                    cards.append(
                        {
                            "headline": "You explored more new artists than usual recently",
                            "detail": f"In {last_month}, about {discovered} artist appearances were new compared with the prior week "
                            "(summed across weeks). That's above your usual pace.",
                            "kind": "highlight",
                        }
                    )
                elif discovered > 0:
                    cards.append(
                        {
                            "headline": f"You folded in about {discovered} new-to-the-week artists in {last_month}",
                            "detail": "We count artists who show up in a week but not the week before — a simple discovery signal.",
                            "kind": "info",
                        }
                    )
            elif discovered > 0:
                cards.append(
                    {
                        "headline": f"You folded in about {discovered} new-to-the-week artists in {last_month}",
                        "detail": "We count artists who show up in a week but not the week before — a simple discovery signal.",
                        "kind": "info",
                    }
                )

    if share is not None:
        if share >= 0.35:
            cards.append(
                {
                    "headline": "You tend to loop your favorites",
                    "detail": f"In {last_month}, your top artist alone accounted for about {share * 100:.0f}% of plays — a high repeat rate.",
                    "kind": "highlight",
                }
            )
        elif share <= 0.12:
            cards.append(
                {
                    "headline": "Your plays are spread across many artists",
                    "detail": f"In {last_month}, your repeat rate was low — no single artist dominated your listening.",
                    "kind": "info",
                }
            )

    if weekly is not None and not weekly.empty and "artist_stability" in weekly.columns:
        tail = weekly.sort_values("week").tail(8)["artist_stability"].dropna()
        if len(tail) >= 4:
            stab = float(tail.mean())
            if stab >= 0.45:
                cards.append(
                    {
                        "headline": "Your listening is consistent week to week",
                        "detail": "Artist overlap between consecutive weeks stayed high recently — similar casts of artists each week.",
                        "kind": "info",
                    }
                )
            elif stab <= 0.28:
                cards.append(
                    {
                        "headline": "Your listening lineup shifts a lot week to week",
                        "detail": "Low consistency means less overlap of artists between consecutive weeks — more rotation or exploration.",
                        "kind": "highlight",
                    }
                )

    if yearly is not None and not yearly.empty:
        y_sorted = yearly.sort_values("year")
        y0, y1 = int(y_sorted["year"].iloc[0]), int(y_sorted["year"].iloc[-1])
        busiest = y_sorted.loc[y_sorted["total_listens"].idxmax()]
        cards.append(
            {
                "headline": f"Your busiest year was {int(busiest['year'])}",
                "detail": f"Across {y1 - y0 + 1} year(s) in this export ({y0}–{y1}), that year had the most total plays.",
                "kind": "info",
            }
        )
    elif seasonal_profile is not None and not seasonal_profile.empty:
        top = seasonal_profile.loc[seasonal_profile["total_listens"].idxmax()]
        sn = str(top["season"]).title()
        cards.append(
            {
                "headline": f"{sn} is your heaviest listening season",
                "detail": "Totals combine every year — useful for spotting long-run seasonal habits.",
                "kind": "info",
            }
        )

    return cards[:5]


def _generate_insights(
    weekly: pd.DataFrame | None,
    monthly: pd.DataFrame | None,
    seasonal_profile: pd.DataFrame | None,
    seasonal_ts: pd.DataFrame | None,
    yearly: pd.DataFrame | None,
    clustered: pd.DataFrame | None,
    peaks: pd.DataFrame | None,
    transition: pd.DataFrame | None,
    username: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    if weekly is None or weekly.empty:
        out.append(
            {
                "title": "Welcome",
                "description": f"Use “Fetch my data” to build personalized dashboards for {username}.",
                "kind": "info",
            }
        )
        return out

    # --- Listening volume & time span ---
    if yearly is not None and not yearly.empty:
        y_sorted = yearly.sort_values("year")
        y0, y1 = int(y_sorted["year"].iloc[0]), int(y_sorted["year"].iloc[-1])
        span = y1 - y0 + 1
        busiest = y_sorted.loc[y_sorted["total_listens"].idxmax()]
        out.append(
            {
                "title": "Your listening timeline",
                "description": f"Charts cover {span} year(s) ({y0}–{y1}). Your busiest year was {int(busiest['year'])} "
                f"with {int(busiest['total_listens'])} scrobbles.",
                "kind": "highlight",
            }
        )

    # --- Diversity trend (monthly) ---
    if monthly is not None and len(monthly) >= 3:
        m = monthly.sort_values("month")
        first_e = _safe_float(m["artist_entropy"].iloc[0])
        last_e = _safe_float(m["artist_entropy"].iloc[-1])
        if first_e is not None and last_e is not None:
            delta = last_e - first_e
            if delta > 0.15:
                out.append(
                    {
                        "title": "Growing exploration",
                        "description": "Your music variety increased from the start to the end of your history — "
                        "you've been exploring more artists over time.",
                        "kind": "highlight",
                    }
                )
            elif delta < -0.15:
                out.append(
                    {
                        "title": "More focused listening",
                        "description": "Artist diversity decreased over the period — recent months lean toward a smaller set of artists.",
                        "kind": "info",
                    }
                )

        recent = m.tail(6)
        if len(recent) >= 4:
            ent = recent["artist_entropy"].dropna()
            if len(ent) >= 3 and ent.iloc[-1] > ent.mean() + 0.1:
                out.append(
                    {
                        "title": "Recent variety spike",
                        "description": "In the last several months, your listening was more varied than usual for that window.",
                        "kind": "highlight",
                    }
                )

    # --- Seasonal profile (all-time) ---
    if seasonal_profile is not None and not seasonal_profile.empty:
        top = seasonal_profile.loc[seasonal_profile["total_listens"].idxmax()]
        sn = str(top["season"]).title()
        out.append(
            {
                "title": "Seasonal listening",
                "description": f"Across all years, {sn} accounts for the most total listens. See the seasonal chart below for the full picture.",
                "kind": "info",
            }
        )

    # --- Seasonal timeseries: year-over-year contrast ---
    if seasonal_ts is not None and len(seasonal_ts) >= 4:
        last_y = seasonal_ts["year"].max()
        prev_rows = seasonal_ts[seasonal_ts["year"] == last_y]
        if not prev_rows.empty:
            top_s = prev_rows.loc[prev_rows["total_listens"].idxmax()]
            out.append(
                {
                    "title": f"Last full year in data ({int(last_y)})",
                    "description": f"In {int(last_y)}, {str(top_s['season']).title()} was your most active season by play count.",
                    "kind": "info",
                }
            )

    # --- Taste shocks (weekly) ---
    # if "taste_shock" in weekly.columns:
    #     ts = weekly["taste_shock"]
    #     if ts.dtype == bool:
    #         n_shocks = int(ts.sum())
    #     else:
    #         n_shocks = int(ts.astype(str).str.lower().isin(["true", "1"]).sum())
    #     if n_shocks > 0:
    #         out.append(
    #             {
    #                 "title": "Preference shifts",
    #                 "description": f"{n_shocks} week(s) look like taste shocks — artist overlap with the prior week dropped sharply, "
    #                 "often meaning a deliberate shift or discovery binge.",
    #                 "kind": "highlight",
    #             }
    #         )

    # --- Peak diversity weeks ---
    # if peaks is not None and not peaks.empty:
    #     row = peaks.iloc[0]
    #     ae = _safe_float(row.get("artist_entropy"))
    #     ent_part = f" (artist entropy **{ae:.2f}**)" if ae is not None else ""
    #     out.append(
    #         {
    #             "title": "Peak discovery week",
    #             "description": f"Your highest artist-diversity sample week is {row['week']}{ent_part}.",
    #             "kind": "info",
    #         }
    #     )

    # --- Clusters ---
    # if clustered is not None and "cluster" in clustered.columns and not clustered.empty:
    #     vc = clustered["cluster"].value_counts(normalize=True)
    #     dominant = int(vc.index[0])
    #     pct = 100.0 * float(vc.iloc[0])
    #     out.append(
    #         {
    #             "title": "Listening modes (ML clusters)",
    #             "description": f"{pct:.0f}% of your weeks fall into cluster {dominant} — your most common latent listening mode. "
    #             "The Clusters tab shows PCA space and how modes evolve.",
    #             "kind": "highlight",
    #         }
    #     )

    if (
        weekly is not None
        and not weekly.empty
        and (yearly is None or yearly.empty or seasonal_ts is None or seasonal_ts.empty)
    ):
        out.append(
            {
                "title": "Refresh for full timelines",
                "description": "Re-run “Fetch my data” after updating the pipeline to load year-level and season-by-year charts (newer exports include these files).",
                "kind": "info",
            }
        )

    # --- Genre transitions ---
    if transition is not None and not transition.empty:
        top = transition.nlargest(1, "count").iloc[0]
        fg = top.get("from_genre", "?")
        tg = top.get("to_genre", "?")
        prob = _safe_float(top.get("probability"))
        prob_s = f" ({prob * 100:.0f}% of plays after {fg})" if prob else ""
        out.append(
            {
                "title": "Genre flow",
                "description": f"Your most common consecutive-genre jump is {fg} → {tg}{prob_s}.",
                "kind": "info",
            }
        )

    return out


def build_dashboard_payload(root: Path, username: str) -> dict[str, Any]:
    u = username.strip()

    def _p(suffix: str) -> Path:
        return root / f"{u}_{suffix}"

    weekly = _read_csv_optional(_p("weekly_features.csv"))
    monthly = _read_csv_optional(_p("monthly_features.csv"))
    seasonal_profile = _read_csv_optional(_p("seasonal_features.csv"))
    seasonal_ts = _read_csv_optional(_p("seasonal_timeseries.csv"))
    yearly = _read_csv_optional(_p("yearly_features.csv"))
    clustered = _read_csv_optional(_p("clustered_weeks.csv"))
    peaks = _read_csv_optional(_p("peak_diversity_weeks.csv"))
    valleys = _read_csv_optional(_p("low_diversity_weeks.csv"))
    transition = _read_csv_optional(_p("genre_transition_matrix.csv"))

    if weekly is not None and "week_start" not in weekly.columns and "week" in weekly.columns:
        weekly = weekly.copy()
        weekly["week_start"] = weekly["week"].str.split("/").str[0]

    insights = _generate_insights(
        weekly, monthly, seasonal_profile, seasonal_ts, yearly, clustered, peaks, transition, u
    )

    top_stuff = _build_top_stuff_by_windows(root / f"{u}_listening_history.csv")
    trends_monthly = _trends_monthly_payload(monthly, weekly)
    personality_cards = _build_personality_cards(
        weekly, monthly, seasonal_profile, yearly
    )
    weekend_listening = _weekend_split_payload(weekly)

    cluster_summary: list[dict[str, Any]] = []
    if clustered is not None and "cluster" in clustered.columns:
        num_cols = [
            c
            for c in clustered.select_dtypes(include=[np.number]).columns
            if c not in ("PC1", "PC2", "cluster")
        ]
        use = [c for c in num_cols if c in clustered.columns][:8]
        if use:
            grp = clustered.groupby("cluster")[use].mean().reset_index()
            cluster_summary = _df_records(grp)

    top_transitions: list[dict[str, Any]] = []
    if transition is not None and not transition.empty:
        top_transitions = _df_records(transition.nlargest(8, "count"))

    has_data = weekly is not None and not weekly.empty

    date_range: dict[str, str] | None = None
    if clustered is not None and "week_start" in clustered.columns and not clustered.empty:
        ws = pd.to_datetime(clustered["week_start"], errors="coerce").dropna()
        if not ws.empty:
            date_range = {"start": ws.min().date().isoformat(), "end": ws.max().date().isoformat()}

    return {
        "username": u,
        "hasData": has_data,
        "dateRange": date_range,
        "weekly": _df_records(weekly),
        "monthly": _df_records(monthly),
        "seasonalProfile": _df_records(seasonal_profile),
        "seasonalTimeseries": _df_records(seasonal_ts),
        "yearly": _df_records(yearly),
        "clusters": _df_records(clustered),
        "clusterSummary": cluster_summary,
        "peaks": _df_records(peaks),
        "valleys": _df_records(valleys),
        "topTransitions": top_transitions,
        "insights": insights,
        "personalityCards": personality_cards,
        "trendsMonthly": trends_monthly,
        "weekendListening": weekend_listening,
        "topStuff": top_stuff,
        "plots": {
            "pcaScatter": f"/api/plots/{u}/scatter",
            "pcaTimeline": f"/api/plots/{u}/timeline",
        },
    }
