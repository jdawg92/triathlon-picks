"""Fast athlete scorecard build engine.

This module keeps the heavy scorecard rebuild out of streamlit_app.py.
It builds all athlete/profile/discipline scorecards in a small number of grouped
operations, then returns rows ready for Supabase inserts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import math
import re

import numpy as np
import pandas as pd

PROFILES = [
    "Long Course / 70.3 + T100",
    "Short Course / WTCS",
    "Full IRONMAN",
    "All",
]
DISCIPLINES = ["overall", "swim", "bike", "run"]

DEFAULT_LOOKBACK_DAYS = 365
FULL_IM_LOOKBACK_DAYS = 730
ALL_LOOKBACK_DAYS = 730


# ---------- small normalization helpers ----------
def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _norm_gender(value: Any) -> str:
    s = _clean(value).lower()
    if s in {"m", "male", "men", "man", "mens", "men's", "elite men", "pro men"}:
        return "Men"
    if s in {"f", "female", "women", "woman", "womens", "women's", "elite women", "pro women"}:
        return "Women"
    return ""


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
        if not value:
            return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    v = _safe_float(value)
    if v is None:
        return None
    return int(round(v))


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def _canonical_url(value: Any) -> str:
    s = _clean(value)
    if not s:
        return ""
    s = s.split("?")[0].rstrip("/")
    s = s.replace("https://protrinews.com/en/athletes/", "https://protrinews.com/athletes/")
    s = s.replace("http://protrinews.com/en/athletes/", "https://protrinews.com/athletes/")
    s = s.replace("http://protrinews.com/athletes/", "https://protrinews.com/athletes/")
    return s


def _to_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return _iso_date(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _json_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k): _to_json_value(v) for k, v in row.items()}


def _format_time(seconds: Any) -> str:
    sec = _safe_int(seconds)
    if sec is None or sec < 0:
        return ""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _race_text(df: pd.DataFrame) -> pd.Series:
    parts = []
    for col in ["race_name", "race_type", "distance"]:
        if col in df.columns:
            parts.append(df[col].fillna("").astype(str).str.lower())
        else:
            parts.append(pd.Series([""] * len(df), index=df.index))
    return parts[0] + " " + parts[1] + " " + parts[2]


def _profile_mask(df: pd.DataFrame, profile: str) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool, index=df.index)
    txt = _race_text(df)
    sof = pd.to_numeric(df.get("sof", pd.Series([np.nan] * len(df), index=df.index)), errors="coerce")

    is_full = txt.str.contains(r"\b140\.6\b|full ironman|\bfull\b", regex=True, na=False) | (
        txt.str.contains("ironman", na=False) & ~txt.str.contains("70.3", na=False) & ~txt.str.contains("t100|pto", regex=True, na=False)
    )
    is_long = txt.str.contains("70.3|middle|challenge|t100|pto|100k", regex=True, na=False) & ~is_full

    is_wtcs = txt.str.contains("wtcs|world triathlon championship series|world triathlon championships", regex=True, na=False)
    is_world_cup = txt.str.contains("world triathlon cup", regex=True, na=False)
    is_olympic = txt.str.contains("olympic|olympics|olympic games", regex=True, na=False)
    is_sprint = txt.str.contains("sprint|super sprint", regex=True, na=False)
    is_conti = txt.str.contains("continental cup|europe triathlon cup|africa triathlon cup|americas triathlon cup|asia triathlon cup|oceania triathlon cup", regex=True, na=False)

    # For short course, permit true WTCS/World Cup sprint rows, but keep low-tier
    # continental sprint rows out unless they are Olympic-distance and have strong SOF.
    short = is_wtcs | is_world_cup | is_olympic | ((is_conti & is_olympic) & (sof >= 65))
    short = short & ~txt.str.contains("super sprint", regex=True, na=False)

    if profile == "Long Course / 70.3 + T100":
        return is_long
    if profile == "Short Course / WTCS":
        return short
    if profile == "Full IRONMAN":
        return is_full
    if profile == "All":
        return pd.Series([True] * len(df), index=df.index)
    return pd.Series([True] * len(df), index=df.index)


def _lookback_days(profile: str) -> int:
    if profile == "Full IRONMAN":
        return FULL_IM_LOOKBACK_DAYS
    if profile == "All":
        return ALL_LOOKBACK_DAYS
    return DEFAULT_LOOKBACK_DAYS


def _prep_results(results: pd.DataFrame) -> pd.DataFrame:
    df = results.copy()
    if df.empty:
        return df

    for col in ["athlete_url", "athlete_name", "gender", "race_name", "race_type", "distance", "place", "status"]:
        if col not in df.columns:
            df[col] = ""
    if "race_date" not in df.columns:
        df["race_date"] = pd.NaT

    df["athlete_url"] = df["athlete_url"].map(_canonical_url)
    df["athlete_name"] = df["athlete_name"].map(_clean)
    df["gender"] = df["gender"].map(_norm_gender)
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")

    for col in ["ors", "sof", "swim_seconds", "bike_seconds", "run_seconds"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan

    if "bad_status" in df.columns:
        df["bad_status"] = df["bad_status"].fillna(False).astype(bool)
    else:
        bad = df["status"].fillna("").astype(str).str.upper().str.contains("DNF|DNS|DSQ|DQ|CANCEL", regex=True, na=False)
        df["bad_status"] = bad

    # Prefer URL as grouping key; fallback to lower name for rows with missing URL.
    df["athlete_key"] = df["athlete_url"].where(df["athlete_url"].astype(str).str.len() > 0, df["athlete_name"].str.lower())
    df = df[df["athlete_key"].astype(str).str.len() > 0].copy()
    return df


def _confidence(evidence_count: int, premium_count: int, strong_count: int) -> str:
    if evidence_count <= 0:
        return "No eligible scorecard evidence"
    if premium_count >= 1 and evidence_count >= 3:
        return "Good - premium proof"
    if strong_count >= 2:
        return "Good - repeated strong proof"
    if strong_count == 1:
        return "Medium - 1 strong race"
    if evidence_count >= 3:
        return "Low - volume but weak evidence"
    return f"Low - {evidence_count} race" if evidence_count == 1 else f"Medium - {evidence_count} races"


def _quality_flags(rows: pd.DataFrame, profile: str, discipline: str) -> Tuple[pd.Series, pd.Series]:
    txt = _race_text(rows)
    sof = pd.to_numeric(rows.get("sof", pd.Series([np.nan] * len(rows), index=rows.index)), errors="coerce").fillna(0)
    premium = txt.str.contains("world championship|championship final|t100|pto|olympic games|wtcs", regex=True, na=False)
    if profile == "Full IRONMAN":
        premium = premium | txt.str.contains("ironman texas|ironman world championship|ironman new zealand|ironman south africa", regex=True, na=False)
    strong = (sof >= 65) | premium
    return premium.fillna(False), strong.fillna(False)


# ---------- scorecard builders ----------
def _build_overall_cards(df: pd.DataFrame, gender: str, profile: str, as_of: pd.Timestamp, model_version: str, top_n: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if df.empty or "ors" not in df.columns:
        return [], []
    work = df[df["ors"].notna() & (df["ors"] > 0) & (~df["bad_status"])].copy()
    if work.empty:
        return [], []
    work["score_value"] = work["ors"].astype(float)
    premium, strong = _quality_flags(work, profile, "overall")
    work["premium_evidence"] = premium
    work["strong_evidence"] = strong
    return _group_top_scores(work, gender, profile, "overall", as_of, model_version, top_n)


def _split_score_rows(df: pd.DataFrame, discipline: str, profile: str) -> pd.DataFrame:
    split_col = f"{discipline}_seconds"
    if df.empty or split_col not in df.columns:
        return pd.DataFrame()
    work = df[df[split_col].notna() & (df[split_col] > 0) & (~df["bad_status"])].copy()
    if work.empty:
        return pd.DataFrame()

    work["race_key"] = (
        work["race_date"].dt.strftime("%Y-%m-%d").fillna("") + "|" +
        work["race_name"].fillna("").astype(str) + "|" +
        work["gender"].fillna("").astype(str)
    )
    work["sample_size"] = work.groupby("race_key")[split_col].transform("count")
    work["split_rank_num"] = work.groupby("race_key")[split_col].rank(method="min", ascending=True)
    work["fastest_split"] = work.groupby("race_key")[split_col].transform("min")
    work["pct_behind_fastest"] = ((work[split_col] - work["fastest_split"]) / work["fastest_split"] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    sample = work["sample_size"].clip(lower=1)
    rank = work["split_rank_num"].fillna(sample)
    position_score = 100 * (sample - rank + 1) / sample
    sof_score = pd.to_numeric(work["sof"], errors="coerce").fillna(0).clip(lower=0, upper=100)
    time_score = (100 - work["pct_behind_fastest"].fillna(0) * 8).clip(lower=0, upper=100)
    score = 0.35 * position_score + 0.35 * sof_score + 0.30 * time_score

    # Guardrails for tiny / missing-SOF samples. This prevents development-cup rows
    # with 3 athletes and no SOF from beating championship / T100 evidence.
    missing_sof = pd.to_numeric(work["sof"], errors="coerce").isna() | (pd.to_numeric(work["sof"], errors="coerce") <= 0)
    score = score.mask(missing_sof, np.minimum(score, 55))
    score = score.mask(work["sample_size"] < 3, np.minimum(score, 45))

    premium, strong = _quality_flags(work, profile, discipline)
    work["premium_evidence"] = premium
    work["strong_evidence"] = strong
    work["score_value"] = score.round(4)
    work["split_text"] = work[split_col].map(_format_time)
    work["split_rank_display"] = work["split_rank_num"].fillna(0).astype(int).astype(str) + "/" + work["sample_size"].fillna(0).astype(int).astype(str)
    return work[work["score_value"] > 0].copy()


def _build_split_cards(df: pd.DataFrame, gender: str, profile: str, discipline: str, as_of: pd.Timestamp, model_version: str, top_n: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    work = _split_score_rows(df, discipline, profile)
    if work.empty:
        return [], []
    return _group_top_scores(work, gender, profile, discipline, as_of, model_version, top_n)


def _group_top_scores(work: pd.DataFrame, gender: str, profile: str, discipline: str, as_of: pd.Timestamp, model_version: str, top_n: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    score_rows: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []
    as_of_label = as_of.strftime("%Y-%m-%d")
    current_year = int(as_of.year)

    for _, g in work.sort_values(["athlete_key", "score_value", "race_date"], ascending=[True, False, False]).groupby("athlete_key", sort=False):
        top = g.sort_values(["score_value", "race_date"], ascending=[False, False]).head(top_n).copy()
        if top.empty:
            continue
        scores = [float(x) for x in pd.to_numeric(top["score_value"], errors="coerce").dropna().tolist() if float(x) > 0]
        if not scores:
            continue
        score = float(np.mean(scores))
        athlete_url = _canonical_url(top["athlete_url"].dropna().iloc[0]) if top["athlete_url"].dropna().size else ""
        athlete_name = _clean(top["athlete_name"].dropna().iloc[0]) if top["athlete_name"].dropna().size else _clean(top["athlete_key"].iloc[0])
        last = top.sort_values("race_date", ascending=False).iloc[0]
        cy = g[g["race_date"].dt.year == current_year]
        cy_scores = pd.to_numeric(cy["score_value"], errors="coerce").dropna().tolist() if not cy.empty else []
        premium_count = int(top.get("premium_evidence", pd.Series([False] * len(top), index=top.index)).fillna(False).astype(bool).sum())
        strong_count = int(top.get("strong_evidence", pd.Series([False] * len(top), index=top.index)).fillna(False).astype(bool).sum())
        confidence = _confidence(len(scores), premium_count, strong_count)
        last_race_date = _iso_date(last.get("race_date"))

        raw = {
            "best_scores_used": [round(x, 2) for x in scores],
            "premium_evidence_count": premium_count,
            "strong_evidence_count": strong_count,
            "evidence_count": len(scores),
        }
        if discipline != "overall":
            raw.update({
                "OpenRank Split Score": round(score, 2),
                "Best Split Scores Used": ", ".join(f"{x:.1f}" for x in scores),
                "Premium Evidence Count": premium_count,
                "Strong Evidence Count": strong_count,
                "Evidence Count": len(scores),
                "Last Rank": _clean(last.get("split_rank_display")),
                "Best Recent Split": _clean(last.get("split_text")),
            })
        else:
            raw.update({
                "OpenRank Score": round(score, 2),
                "Best Scores Used": ", ".join(f"{x:.1f}" for x in scores),
            })

        score_rows.append({
            "model_version": model_version,
            "as_of_date": as_of_label,
            "profile": profile,
            "discipline": discipline,
            "gender": gender,
            "athlete_url": athlete_url,
            "athlete_name": athlete_name,
            "rank": None,  # filled after sorting
            "score": round(score, 4),
            "best_scores": [round(x, 4) for x in scores],
            "evidence_count": len(scores),
            "current_year_score": round(float(np.mean(sorted(cy_scores, reverse=True)[:top_n])), 4) if cy_scores else None,
            "current_year_races": int(len(cy)) if cy is not None else 0,
            "current_year_scored": int(len([x for x in cy_scores if x > 0])) if cy_scores else 0,
            "confidence": confidence,
            "last_race_name": _clean(last.get("race_name")),
            "last_race_date": last_race_date,
            "computed_source": f"fast_score_engine · {gender} · {profile} · {discipline} · top {top_n}",
            "raw": _json_row(raw),
        })

        for used_rank, (_, ev) in enumerate(top.iterrows(), start=1):
            ev_score = _safe_float(ev.get("score_value"))
            evidence_rows.append({
                "model_version": model_version,
                "as_of_date": as_of_label,
                "profile": profile,
                "discipline": discipline,
                "gender": gender,
                "athlete_url": athlete_url,
                "athlete_name": athlete_name,
                "used_rank": used_rank,
                "race_date": _iso_date(ev.get("race_date")),
                "race_name": _clean(ev.get("race_name")),
                "race_type": _clean(ev.get("race_type")),
                "place": _clean(ev.get("place")),
                "sof": _safe_float(ev.get("sof")),
                "ors": _safe_float(ev.get("ors")),
                "split_text": _clean(ev.get("split_text")) if discipline != "overall" else "",
                "split_rank": _clean(ev.get("split_rank_display")) if discipline != "overall" else "",
                "pct_behind_fastest": _safe_float(ev.get("pct_behind_fastest")) if discipline != "overall" else None,
                "evidence_score": round(ev_score, 4) if ev_score is not None else None,
                "raw": _json_row({
                    "Date": _iso_date(ev.get("race_date")),
                    "Race": _clean(ev.get("race_name")),
                    "Race Type": _clean(ev.get("race_type")),
                    "Place": _clean(ev.get("place")),
                    "SOF": _safe_float(ev.get("sof")),
                    "ORS": _safe_float(ev.get("ors")),
                    "Split": _clean(ev.get("split_text")),
                    "Split Rank": _clean(ev.get("split_rank_display")),
                    "% Behind Fastest": _safe_float(ev.get("pct_behind_fastest")),
                    "Evidence Score": ev_score,
                    "Premium Evidence": bool(ev.get("premium_evidence", False)),
                    "Strong Evidence": bool(ev.get("strong_evidence", False)),
                }),
            })

    # rank inside slice
    score_rows.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("athlete_name") or "")))
    for i, row in enumerate(score_rows, start=1):
        row["rank"] = i
    return score_rows, evidence_rows


def build_all_scorecards(
    results: pd.DataFrame,
    as_of_date: Any,
    model_version: str,
    top_n: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (scorecards, evidence, log) for all genders/profiles/disciplines.

    This is intentionally one engine call: the app should load/normalize once, call
    this once, then bulk-save the returned rows.
    """
    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        as_of = pd.Timestamp.today().normalize()
    df = _prep_results(results)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{"Status": "empty results"}])

    cards: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    for gender in ["Men", "Women"]:
        gdf_base = df[df["gender"] == gender].copy()
        for profile in PROFILES:
            lookback = _lookback_days(profile)
            window_start = as_of - pd.Timedelta(days=lookback)
            pdf = gdf_base[
                (gdf_base["race_date"].notna()) &
                (gdf_base["race_date"] >= window_start) &
                (gdf_base["race_date"] <= as_of) &
                (_profile_mask(gdf_base, profile))
            ].copy()
            for discipline in DISCIPLINES:
                before_cards = len(cards)
                before_ev = len(evidence)
                try:
                    if discipline == "overall":
                        c, e = _build_overall_cards(pdf, gender, profile, as_of, model_version, top_n)
                    else:
                        c, e = _build_split_cards(pdf, gender, profile, discipline, as_of, model_version, top_n)
                    cards.extend(c)
                    evidence.extend(e)
                    status = "saved"
                except Exception as exc:
                    status = f"error: {exc}"
                logs.append({
                    "Gender": gender,
                    "Profile": profile,
                    "Discipline": discipline,
                    "Rows After Profile": int(len(pdf)),
                    "Scorecard Rows": int(len(cards) - before_cards),
                    "Evidence Rows": int(len(evidence) - before_ev),
                    "Lookback Days": int(lookback),
                    "Status": status,
                })

    return pd.DataFrame(cards), pd.DataFrame(evidence), pd.DataFrame(logs)
