"""
Anthropic-powered listening personality copy from feature-engineering CSVs.
Falls back to templated insights if the API is unavailable or errors.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

# Load .env from repo root (next to this file), not from the process cwd — uvicorn cwd varies.
_REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()  # also allow cwd .env to override for local experiments

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Pinned default (Claude 3.5 IDs return 404 on current API). Override with ANTHROPIC_MODEL.
# See https://docs.anthropic.com/en/docs/about-claude/models/overview
DEFAULT_MODEL = "claude-haiku-4-5"

CHART_KEYS = (
    "volume",
    "variety",
    "genres",
    "newArtist",
    "listenHour",
    "seasonal",
    "weekend",
)


def _variety_caption_is_artist_only(text: str) -> bool:
    """Reject variety captions that drift into genres (chart uses monthly artist_entropy only)."""
    if not text or not text.strip():
        return False
    lowered = text.lower()
    return "genre" not in lowered


def _safe_float(x: Any) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
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


def build_feature_context(
    username: str,
    weekly: pd.DataFrame | None,
    monthly: pd.DataFrame | None,
    seasonal_profile: pd.DataFrame | None,
    seasonal_ts: pd.DataFrame | None,
    yearly: pd.DataFrame | None,
) -> dict[str, Any]:
    """
    Compact, human-oriented facts for the model (no raw jargon in keys).
    """
    ctx: dict[str, Any] = {"listener_username": username}

    if monthly is not None and not monthly.empty:
        m = monthly.sort_values("month").copy()
        tail = m.tail(18)
        ctx["recent_months"] = []
        for _, row in tail.iterrows():
            ctx["recent_months"].append(
                {
                    "month": str(row.get("month", "")),
                    "total_plays": int(row["total_listens"])
                    if pd.notna(row.get("total_listens"))
                    else None,
                    "artist_mix_breadth": _safe_float(row.get("artist_entropy")),
                    "top_artist_share_of_plays": _safe_float(row.get("top_artist_share")),
                    "new_artists_first_time_that_month": int(row["new_artists"])
                    if pd.notna(row.get("new_artists"))
                    else None,
                }
            )
        last = m.iloc[-1]
        ctx["latest_month"] = str(last.get("month", ""))

    if weekly is not None and not weekly.empty:
        w = weekly.sort_values("week" if "week" in weekly.columns else "week_start").tail(16)
        rows = []
        for _, row in w.iterrows():
            week_lbl = str(row.get("week_start") or row.get("week", ""))
            rows.append(
                {
                    "week": week_lbl,
                    "plays": int(row["total_listens"]) if pd.notna(row.get("total_listens")) else None,
                    "new_artists_that_week": int(row["new_artists"])
                    if "new_artists" in row and pd.notna(row.get("new_artists"))
                    else None,
                    "weekend_share": _safe_float(row.get("weekend_ratio")),
                    "week_to_week_artist_overlap": _safe_float(row.get("artist_stability")),
                }
            )
        ctx["recent_weeks"] = rows

    if seasonal_profile is not None and not seasonal_profile.empty:
        sp = seasonal_profile.copy()
        ctx["season_totals_all_time"] = [
            {"season": str(r.get("season", "")), "plays": int(r["total_listens"])}
            for _, r in sp.iterrows()
            if pd.notna(r.get("total_listens"))
        ]

    if seasonal_ts is not None and not seasonal_ts.empty:
        st = seasonal_ts.sort_values(["year", "season"])
        ctx["season_by_year_sample"] = json.loads(st.tail(16).to_json(orient="records", date_format="iso"))

    if yearly is not None and not yearly.empty:
        y = yearly.sort_values("year")
        ctx["years"] = []
        for _, row in y.iterrows():
            ctx["years"].append(
                {
                    "year": int(row["year"]) if pd.notna(row.get("year")) else None,
                    "total_plays": int(row["total_listens"]) if pd.notna(row.get("total_listens")) else None,
                    "typical_listen_time_hour": _safe_float(row.get("avg_listen_hour")),
                    "distinct_genre_tags": int(row["unique_genres"])
                    if pd.notna(row.get("unique_genres"))
                    else None,
                }
            )

    if weekly is not None and not weekly.empty and "weekend_ratio" in weekly.columns:
        tail = weekly.sort_values("week" if "week" in weekly.columns else "week_start").tail(52)
        r = float(tail["weekend_ratio"].mean())
        r = min(max(r, 0.0), 1.0)
        ctx["typical_weekend_share_recent"] = round(r * 100, 1)

    return ctx


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    for candidate in (text,):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    m2 = re.search(r"(\{[\s\S]*\})", text)
    if m2:
        try:
            obj = json.loads(m2.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def _normalize_ai_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    tagline = raw.get("tagline") or raw.get("headline")
    if not isinstance(tagline, str) or not tagline.strip():
        return None
    ins = raw.get("insights") or raw.get("bullets")
    if not isinstance(ins, list):
        return None
    insights: list[dict[str, str]] = []
    for item in ins[:8]:
        if isinstance(item, str) and item.strip():
            insights.append({"title": item.strip()[:120], "body": ""})
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("headline") or "").strip()
        body = str(item.get("body") or item.get("detail") or item.get("text") or "").strip()
        if not title:
            continue
        insights.append({"title": title[:160], "body": body[:600]})
    if len(insights) < 3:
        return None

    captions: dict[str, str] = {}
    cc = raw.get("chartCaptions") or raw.get("chart_captions") or {}
    if isinstance(cc, dict):
        for k in CHART_KEYS:
            v = cc.get(k)
            if isinstance(v, str) and v.strip():
                s = v.strip()[:400]
                if k == "variety" and not _variety_caption_is_artist_only(s):
                    continue
                captions[k] = s

    return {
        "source": "anthropic",
        "tagline": tagline.strip()[:280],
        "insights": insights[:5],
        "chartCaptions": captions,
    }


def generate_with_anthropic(context: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns (payload, error_hint). error_hint is set when the key exists but the call
    or parsing failed (for dashboard debugging).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None, None

    system = (
        "You write playful, friendly copy about someone's music listening habits for a dashboard. "
        "Rules: use plain language only — never say entropy, Jaccard, PCA, clustering, silhouette, "
        "or other technical jargon. Talk about variety, favorites, discovery, repetition, seasons, "
        "weekends, and how habits change over time. Be accurate to the JSON facts only; do not invent "
        "numbers. Output a single JSON object with keys: "
        'tagline (one short punchy line, <=140 chars), '
        'insights (array of 3 to 5 objects, each {title, body} — title is a catchy label, '
        "body is 1-2 sentences), "
        "chartCaptions (optional object with any of: volume, variety, genres, newArtist, listenHour, "
        "seasonal, weekend — each a single friendly sentence for a chart subtitle; only include keys "
        "where you have something useful to add). "
        "CRITICAL: chartCaptions.variety must describe ONLY the monthly artist mix (field artist_mix_breadth "
        "in recent_months — how spread out plays are across different artists). Never mention genres, "
        "genre tags, or styles in chartCaptions.variety; those belong only in chartCaptions.genres."
    )
    user_text = (
        "Here is structured listening summary from their Last.fm-derived analytics (values may be null):\n\n"
        + json.dumps(context, indent=2, default=str)
        + "\n\nRespond with ONLY valid JSON, no markdown fences.\n\n"
        "Remember: chartCaptions.variety = monthly artist breadth only (artist_mix_breadth). "
        "No genre language in that caption."
    )

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.environ.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL,
                "max_tokens": 1800,
                "temperature": 0.65,
                "system": system,
                "messages": [{"role": "user", "content": user_text}],
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        blocks = data.get("content") or []
        text_parts: list[str] = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                text_parts.append(str(b.get("text", "")))
        joined = "\n".join(text_parts).strip()
        parsed = _extract_json_object(joined)
        if not parsed:
            return None, "model returned text that was not valid JSON (check server logs / model output)"
        normalized = _normalize_ai_payload(parsed)
        if not normalized:
            return None, "JSON parsed but missing tagline or fewer than 3 insights"
        return normalized, None
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        body = (e.response.text[:300] if e.response is not None else "") or str(e)
        return None, f"HTTP {code}: {body}"
    except requests.RequestException as e:
        return None, f"request failed: {e!s}"[:400]
    except (ValueError, KeyError, TypeError) as e:
        return None, f"parse error: {e!s}"[:400]


def _fallback_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Templated insights when AI is unavailable."""
    insights: list[dict[str, str]] = []
    months = context.get("recent_months") or []
    weeks = context.get("recent_weeks") or []
    years = context.get("years") or []
    seasons = context.get("season_totals_all_time") or []

    if months:
        last = months[-1]
        breadth = last.get("artist_mix_breadth")
        top_share = last.get("top_artist_share_of_plays")
        lm = str(last.get("month", "recently"))
        if isinstance(breadth, (int, float)) and len(months) >= 2:
            prior = [m.get("artist_mix_breadth") for m in months[:-1] if isinstance(m.get("artist_mix_breadth"), (int, float))]
            if prior:
                med = sorted(prior)[len(prior) // 2]
                if breadth >= med * 1.05:
                    insights.append(
                        {
                            "title": "Wide open mix lately",
                            "body": f"In {lm} you rotated through a broader cast of artists than your usual month — lots of names in the queue.",
                        }
                    )
                elif breadth <= med * 0.95:
                    insights.append(
                        {
                            "title": "Comfort-zone month",
                            "body": f"{lm} leaned on a smaller set of go-to artists — cozy repeat listening.",
                        }
                    )
        if isinstance(top_share, (int, float)) and top_share >= 0.32:
            insights.append(
                {
                    "title": "Main character energy",
                    "body": f"One artist soaked up a big slice of plays in {lm} — when you find a favorite, you ride it.",
                }
            )
        elif isinstance(top_share, (int, float)) and top_share <= 0.14:
            insights.append(
                {
                    "title": "No single spotlight",
                    "body": f"Plays in {lm} stayed spread out — no one artist ran the whole month.",
                }
            )

    if weeks and len(weeks) >= 4:
        na = [w.get("new_artists_that_week") for w in weeks if isinstance(w.get("new_artists_that_week"), int)]
        if na:
            avg = sum(na) / len(na)
            last_n = na[-1] if na else 0
            if last_n >= max(5, avg * 1.3):
                insights.append(
                    {
                        "title": "Fresh faces on the playlist",
                        "body": "Recent weeks show more brand-new artists showing up than your usual pace — discovery mode.",
                    }
                )

    if years:
        busiest = max(years, key=lambda y: (y.get("total_plays") or 0))
        yb = busiest.get("year")
        pb = busiest.get("total_plays")
        if yb is not None and pb is not None:
            insights.append(
                {
                    "title": f"{yb} was your biggest year",
                    "body": f"That calendar year logged the most plays in this export — a standout stretch for you.",
                }
            )

    if seasons:
        top = max(seasons, key=lambda s: (s.get("plays") or 0))
        sn = str(top.get("season", "One season")).title()
        insights.append(
            {
                "title": f"{sn} shows up a lot",
                "body": "Across all years in this data, that slice of the calendar carries the heaviest listening.",
            }
        )

    if context.get("typical_weekend_share_recent") is not None:
        pct = float(context["typical_weekend_share_recent"])
        if pct >= 58:
            insights.append(
                {
                    "title": "Weekend listener",
                    "body": "Lately more of your plays land on Saturday and Sunday — music as weekend fuel.",
                }
            )
        elif pct <= 38:
            insights.append(
                {
                    "title": "Weekday groove",
                    "body": "Your recent pattern skews toward weekdays — commutes, work breaks, or weeknight soundtracks.",
                }
            )

    filler = {
        "title": "Your stats, your story",
        "body": "Keep fetching updates as you listen — the dashboard grows with every new week of history.",
    }
    while len(insights) < 3:
        insights.append(deepcopy(filler))

    tagline = "Your listening, decoded — the fun version."
    uname = context.get("listener_username") or "you"
    if isinstance(uname, str) and uname:
        tagline = f"{uname}'s mix: part habit, part adventure."

    captions = {
        "volume": "Taller bars are heavier listening days or months — spot streaks or quiet stretches.",
        "variety": "Each month reflects how spread out your plays were across different artists (not genres). Higher means more names in rotation.",
        "genres": "How many different genre tags showed up each year — a rough map of how wide you cast the net.",
        "newArtist": "Share of plays from artists who were new that week — a simple discovery pulse.",
        "listenHour": "When your plays usually land — think commutes, late nights, or lunch breaks.",
        "seasonal": "Which season holds the biggest share of all-time plays in this export.",
        "weekend": "Split between weekend and weekday listening in recent weeks.",
    }

    return {
        "source": "fallback",
        "tagline": tagline[:280],
        "insights": insights[:5],
        "chartCaptions": captions,
    }


def build_listening_personality(
    username: str,
    weekly: pd.DataFrame | None,
    monthly: pd.DataFrame | None,
    seasonal_profile: pd.DataFrame | None,
    seasonal_ts: pd.DataFrame | None,
    yearly: pd.DataFrame | None,
) -> dict[str, Any]:
    ctx = build_feature_context(username, weekly, monthly, seasonal_profile, seasonal_ts, yearly)
    if not (monthly is not None and not monthly.empty) and not (weekly is not None and not weekly.empty):
        return {
            "source": "fallback",
            "tagline": "Fetch your data to unlock a listening portrait.",
            "insights": [
                {
                    "title": "Almost there",
                    "body": "Run a full data fetch so we can read your weekly and monthly summaries.",
                }
            ],
            "chartCaptions": {},
        }

    had_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    ai, api_err = generate_with_anthropic(ctx)
    if ai:
        return ai
    out = _fallback_from_context(ctx)
    if had_key and api_err:
        out["anthropicError"] = api_err
    return out
