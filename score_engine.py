"""Fast athlete scorecard build engine.

HOW SCORING WORKS
-----------------
Every eligible result is assigned an adjusted score before the athlete's
top-N evidence races are averaged into a final scorecard number.

For split disciplines (swim / bike / run):

    base_score  = 0.40 × position_score          # how you ranked in the field
                + 0.30 × time_score               # how close to the fastest split
                + 0.30 × sof_score                # how strong the field was
    × recency   = decay so recent races matter more than old ones
    × relevance = bonus for championship / premium-circuit races
    = adjusted_score  (capped at 100)

For overall (OpenRank / ORS):

    adjusted_score = ORS × recency × relevance    (capped at 100)

ORS already encodes field quality, so the multipliers add recency and
format context on top.

Guardrails prevent weak-field or no-SOF results from dominating:
  - Missing SOF → score capped at 55
  - Field size < 3 → score capped at 45
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

PROFILES = [
    "Long Course / 70.3 + T100",
    "Short Course / WTCS",
    "Full IRONMAN",
    "All",
]
DISCIPLINES = ["overall", "swim", "bike", "run"]

MODEL_ENGINE_VERSION = "score_engine_v6_reliability_prior"

DEFAULT_LOOKBACK_DAYS = 365
FULL_IM_LOOKBACK_DAYS = 730
ALL_LOOKBACK_DAYS = 730


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

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


def _parse_raw_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _first_from_mapping(mapping: Dict[str, Any], aliases: Iterable[str]) -> Any:
    if not mapping:
        return None
    normalized = {str(k).strip().lower().replace("_", " "): k for k in mapping.keys()}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in normalized:
            return mapping[normalized[key]]
    return None


# ---------------------------------------------------------------------------
# Split validation helpers
# ---------------------------------------------------------------------------

def _validate_split_seconds(seconds: Optional[int], discipline: str, race_context: str) -> Optional[int]:
    if seconds is None:
        return None
    rt = (race_context or "").lower()

    if discipline == "swim":
        if "full" in rt or "140.6" in rt:
            return seconds if 35 * 60 <= seconds <= 105 * 60 else None
        if any(x in rt for x in ["sprint", "world triathlon", "continental", "wtcs", "olympic"]):
            return seconds if 3 * 60 <= seconds <= 35 * 60 else None
        return seconds if 12 * 60 <= seconds <= 75 * 60 else None

    if discipline == "bike":
        if any(x in rt for x in ["wtcs", "draft", "world triathlon", "continental"]):
            return None
        if "full" in rt or "140.6" in rt:
            return seconds if 3 * 3600 <= seconds <= 7 * 3600 else None
        if any(x in rt for x in ["sprint", "olympic"]):
            return seconds if 15 * 60 <= seconds <= 2 * 3600 else None
        return seconds if 75 * 60 <= seconds <= 4.5 * 3600 else None

    if discipline == "run":
        if "full" in rt or "140.6" in rt:
            return seconds if 2 * 3600 <= seconds <= 6 * 3600 else None
        if any(x in rt for x in ["sprint", "world triathlon", "continental", "wtcs", "olympic"]):
            return seconds if 12 * 60 <= seconds <= 90 * 60 else None
        return seconds if 55 * 60 <= seconds <= 2.5 * 3600 else None

    return seconds


def _parse_split_seconds(value: Any, discipline: str, race_context: str = "") -> Optional[int]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (int, np.integer)):
        return _validate_split_seconds(int(value), discipline, race_context)
    if isinstance(value, (float, np.floating)):
        if math.isnan(float(value)):
            return None
        if float(value) > 200:
            return _validate_split_seconds(int(round(float(value))), discipline, race_context)

    s = str(value).strip()
    if not s:
        return None
    if re.match(r"^\d{4,}:\d{2}:\d{2}$", s):
        return None
    s = s.replace("—", "").replace("-", "").strip()
    if not s:
        return None

    seconds = None
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = [int(float(x)) for x in parts]
            seconds = h * 3600 + m * 60 + sec
        elif len(parts) == 2:
            a, b = [int(float(x)) for x in parts]
            rt = (race_context or "").lower()
            if discipline == "swim":
                seconds = a * 60 + b
            elif discipline == "bike":
                if any(x in rt for x in ["sprint", "olympic", "world triathlon", "continental", "wtcs"]):
                    seconds = a * 60 + b if a < 90 else a * 3600 + b * 60
                else:
                    seconds = a * 3600 + b * 60
            elif discipline == "run":
                if any(x in rt for x in ["sprint", "olympic", "world triathlon", "continental", "wtcs"]):
                    seconds = a * 60 + b
                else:
                    seconds = a * 3600 + b * 60
        elif len(parts) == 1:
            v = _safe_float(s)
            if v is not None:
                seconds = int(round(v))
    except Exception:
        return None

    return _validate_split_seconds(seconds, discipline, race_context)


def _recover_split_from_row(row: pd.Series, discipline: str) -> Optional[int]:
    aliases = {
        "swim": ["swim_seconds", "Swim Seconds", "Swim", "Swim Split", "Swim Time", "swim", "swim_split", "swim_time"],
        "bike": ["bike_seconds", "Bike Seconds", "Bike", "Bike Split", "Bike Time", "bike", "bike_split", "bike_time"],
        "run":  ["run_seconds",  "Run Seconds",  "Run", "Run Split",  "Run Time",  "run", "run_split",  "run_time"],
    }[discipline]
    race_context = " ".join([_clean(row.get(c)) for c in ["race_name", "race_type", "distance"]])

    col_map = {str(c).strip().lower().replace("_", " "): c for c in row.index}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in col_map:
            sec = _parse_split_seconds(row.get(col_map[key]), discipline, race_context)
            if sec is not None:
                return sec

    raw = _parse_raw_payload(row.get("raw"))
    val = _first_from_mapping(raw, aliases)
    return _parse_split_seconds(val, discipline, race_context)


# ---------------------------------------------------------------------------
# Scoring context multipliers
# ---------------------------------------------------------------------------

def _recency_factor(race_date: Any, as_of: pd.Timestamp) -> float:
    """Decay multiplier: more recent results carry more weight in the scorecard."""
    try:
        rd = pd.to_datetime(race_date)
        if pd.isna(rd):
            return 0.70
        days_ago = max(0, (as_of - rd).days)
    except Exception:
        return 0.70
    if days_ago <= 90:
        return 1.00
    if days_ago <= 180:
        return 0.93
    if days_ago <= 270:
        return 0.86
    if days_ago <= 365:
        return 0.78
    if days_ago <= 540:
        return 0.67
    return 0.57


def _race_relevance_factor(race_text: str, sof: Optional[float]) -> float:
    """Bonus multiplier for high-relevance race formats and strong fields.

    Championship and premium-series races earn a bonus so a world-championship
    result counts more than the same raw performance in a minor race.
    """
    txt = (race_text or "").lower()
    # Pinnacle events
    if any(x in txt for x in [
        "world championship", "olympic games", "ironman world",
        "t100 world", "championship final", "wtcs final",
        "kona", "st george", "nice",
    ]):
        return 1.18
    # Strong series / majors
    if any(x in txt for x in [
        "wtcs", "t100", "pto", "ironman 70.3 world",
        "championship series", "world series",
    ]):
        return 1.10
    # High-SOF field even if unlabelled as a major
    sof_v = _safe_float(sof) or 0.0
    if sof_v >= 80:
        return 1.08
    if sof_v >= 65:
        return 1.04
    return 1.00


# ---------------------------------------------------------------------------
# Profile / lookback helpers
# ---------------------------------------------------------------------------

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
        txt.str.contains("ironman", na=False)
        & ~txt.str.contains("70.3", na=False)
        & ~txt.str.contains("t100|pto", regex=True, na=False)
    )
    is_long = txt.str.contains("70.3|middle|challenge|t100|pto|100k", regex=True, na=False) & ~is_full

    is_wtcs       = txt.str.contains("wtcs|world triathlon championship series|world triathlon championships", regex=True, na=False)
    is_world_cup  = txt.str.contains("world triathlon cup", regex=True, na=False)
    is_olympic    = txt.str.contains("olympic|olympics|olympic games", regex=True, na=False)
    is_conti      = txt.str.contains(
        "continental cup|europe triathlon cup|africa triathlon cup|"
        "americas triathlon cup|asia triathlon cup|oceania triathlon cup",
        regex=True, na=False,
    )

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


# ---------------------------------------------------------------------------
# Result normalisation
# ---------------------------------------------------------------------------

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

    for col in ["ors", "sof"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan

    for disc in ["swim", "bike", "run"]:
        col = f"{disc}_seconds"
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
        missing = df[col].isna()
        if missing.any():
            recovered = df.loc[missing].apply(lambda r, d=disc: _recover_split_from_row(r, d), axis=1)
            df.loc[missing, col] = pd.to_numeric(recovered, errors="coerce").to_numpy()
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "bad_status" in df.columns:
        df["bad_status"] = df["bad_status"].fillna(False).astype(bool)
    else:
        bad = df["status"].fillna("").astype(str).str.upper().str.contains("DNF|DNS|DSQ|DQ|CANCEL", regex=True, na=False)
        df["bad_status"] = bad

    df["athlete_key"] = df["athlete_url"].where(
        df["athlete_url"].astype(str).str.len() > 0,
        df["athlete_name"].str.lower(),
    )
    df = df[df["athlete_key"].astype(str).str.len() > 0].copy()
    return df


# ---------------------------------------------------------------------------
# Confidence / quality helpers
# ---------------------------------------------------------------------------

def _confidence(evidence_count: int, premium_count: int, strong_count: int) -> str:
    if evidence_count <= 0:
        return "No eligible scorecard evidence"
    if evidence_count == 1 and (premium_count >= 1 or strong_count >= 1):
        return "High ceiling - low sample"
    if evidence_count == 1:
        return "Low sample - 1 race"
    if premium_count >= 1 and evidence_count >= 3:
        return "Good - premium proof"
    if strong_count >= 2:
        return "Good - repeated strong proof"
    if strong_count == 1:
        return "Medium - 1 strong race"
    if evidence_count >= 3:
        return "Low - volume but weak evidence"
    return f"Medium - {evidence_count} races"


def _reliability_weight(evidence_count: int, premium_count: int, strong_count: int, prior_available: bool = False) -> float:
    """How much the ranking should trust the recent/profile-specific score.

    A single great race should keep a high performance ceiling, but the ranking
    score should be blended with a prior unless the athlete has repeated proof.
    Strong/premium evidence earns a small bump; a usable prior lets elite
    short-course or historical evidence support a thin recent long-course sample.
    """
    n = max(0, int(evidence_count or 0))
    if n <= 0:
        return 0.0
    base = {1: 0.55, 2: 0.72, 3: 0.88, 4: 0.96}.get(n, 1.00)
    if strong_count >= 1:
        base += 0.04
    if premium_count >= 1:
        base += 0.03
    if prior_available and n <= 2:
        # A real prior gives us confidence that a small sample is not random.
        base += 0.04
    return float(max(0.0, min(base, 1.0)))


def _baseline_prior_score(discipline: str, profile: str) -> float:
    """Conservative prior used when no cross-profile or historical proof exists."""
    if discipline == "run":
        return 60.0
    if discipline == "swim":
        return 58.0
    if discipline == "bike":
        return 56.0
    return 58.0


def _prior_score_map(work: pd.DataFrame, top_n: int) -> Dict[str, Tuple[float, int]]:
    """Return athlete_key -> (prior score, evidence count) from backup evidence rows."""
    if work is None or work.empty or "score_value" not in work.columns:
        return {}
    out: Dict[str, Tuple[float, int]] = {}
    for key, g in work.groupby("athlete_key", sort=False):
        vals = pd.to_numeric(g.sort_values(["score_value", "race_date"], ascending=[False, False])["score_value"], errors="coerce")
        vals = [float(x) for x in vals.dropna().head(int(top_n)) if float(x) > 0]
        if vals:
            out[str(key)] = (float(np.mean(vals)), int(len(vals)))
    return out


def _quality_flags(rows: pd.DataFrame, profile: str, discipline: str) -> Tuple[pd.Series, pd.Series]:
    txt = _race_text(rows)
    sof = pd.to_numeric(rows.get("sof", pd.Series([np.nan] * len(rows), index=rows.index)), errors="coerce").fillna(0)
    premium = txt.str.contains("world championship|championship final|t100|pto|olympic games|wtcs", regex=True, na=False)
    if profile == "Full IRONMAN":
        premium = premium | txt.str.contains(
            "ironman texas|ironman world championship|ironman new zealand|ironman south africa",
            regex=True, na=False,
        )
    strong = (sof >= 65) | premium
    return premium.fillna(False), strong.fillna(False)


# ---------------------------------------------------------------------------
# Scorecard builders
# ---------------------------------------------------------------------------

def _overall_score_rows(df: pd.DataFrame, profile: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return scored overall rows before athlete grouping."""
    if df.empty or "ors" not in df.columns:
        return pd.DataFrame()
    work = df[df["ors"].notna() & (df["ors"] > 0) & (~df["bad_status"])].copy()
    if work.empty:
        return pd.DataFrame()

    race_txt = _race_text(work)
    recency_vals = work["race_date"].map(lambda rd: _recency_factor(rd, as_of))
    relevance_vals = pd.Series(
        [_race_relevance_factor(txt, _safe_float(sof)) for txt, sof in zip(race_txt, work["sof"])],
        index=work.index,
    )

    adjusted = (work["ors"].astype(float) * recency_vals * relevance_vals).clip(upper=100)

    work["score_value"]      = adjusted.round(4)
    work["recency_factor"]   = recency_vals.round(3)
    work["relevance_factor"] = relevance_vals.round(3)

    premium, strong = _quality_flags(work, profile, "overall")
    work["premium_evidence"] = premium
    work["strong_evidence"]  = strong
    return work[work["score_value"] > 0].copy()


def _build_overall_cards(
    df: pd.DataFrame,
    gender: str,
    profile: str,
    as_of: pd.Timestamp,
    model_version: str,
    top_n: int,
    prior_scores: Optional[Dict[str, Tuple[float, int]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Overall scorecard: ORS adjusted by recency and race relevance."""
    work = _overall_score_rows(df, profile, as_of)
    if work.empty:
        return [], []
    return _group_top_scores(work, gender, profile, "overall", as_of, model_version, top_n, prior_scores=prior_scores)


def _split_score_rows(
    df: pd.DataFrame,
    discipline: str,
    profile: str,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    """Score each split result; apply recency and relevance multipliers."""
    split_col = f"{discipline}_seconds"
    if df.empty or split_col not in df.columns:
        return pd.DataFrame()
    work = df[df[split_col].notna() & (df[split_col] > 0) & (~df["bad_status"])].copy()
    if work.empty:
        return pd.DataFrame()

    work["race_key"] = (
        work["race_date"].dt.strftime("%Y-%m-%d").fillna("") + "|"
        + work["race_name"].fillna("").astype(str) + "|"
        + work["gender"].fillna("").astype(str)
    )
    work["sample_size"]     = work.groupby("race_key")[split_col].transform("count")
    work["split_rank_num"]  = work.groupby("race_key")[split_col].rank(method="min", ascending=True)
    work["fastest_split"]   = work.groupby("race_key")[split_col].transform("min")
    work["pct_behind_fastest"] = (
        (work[split_col] - work["fastest_split"]) / work["fastest_split"] * 100
    ).replace([np.inf, -np.inf], np.nan).fillna(0)

    sample         = work["sample_size"].clip(lower=1)
    rank           = work["split_rank_num"].fillna(sample)
    position_score = 100 * (sample - rank + 1) / sample
    sof_score      = pd.to_numeric(work["sof"], errors="coerce").fillna(0).clip(lower=0, upper=100)
    time_score     = (100 - work["pct_behind_fastest"].fillna(0) * 8).clip(lower=0, upper=100)

    # Base: split performance (40%) + time closeness (30%) + field strength (30%)
    base_score = 0.40 * position_score + 0.30 * time_score + 0.30 * sof_score

    # Apply recency decay and race-relevance bonus
    race_txt = _race_text(work)
    recency_vals = work["race_date"].map(lambda rd: _recency_factor(rd, as_of))
    relevance_vals = pd.Series(
        [_race_relevance_factor(txt, _safe_float(sof)) for txt, sof in zip(race_txt, work["sof"])],
        index=work.index,
    )
    score = (base_score * recency_vals * relevance_vals).clip(upper=100)

    # Guardrails: prevent weak-field / no-SOF results from dominating
    missing_sof = pd.to_numeric(work["sof"], errors="coerce").isna() | (pd.to_numeric(work["sof"], errors="coerce") <= 0)
    score = score.mask(missing_sof, np.minimum(score, 55))
    score = score.mask(work["sample_size"] < 3, np.minimum(score, 45))

    premium, strong = _quality_flags(work, profile, discipline)
    work["premium_evidence"]  = premium
    work["strong_evidence"]   = strong
    work["score_value"]       = score.round(4)
    work["recency_factor"]    = recency_vals.round(3)
    work["relevance_factor"]  = relevance_vals.round(3)
    work["split_text"]        = work[split_col].map(_format_time)
    work["split_rank_display"] = (
        work["split_rank_num"].fillna(0).astype(int).astype(str)
        + "/" + work["sample_size"].fillna(0).astype(int).astype(str)
    )
    return work[work["score_value"] > 0].copy()


def _build_split_cards(
    df: pd.DataFrame,
    gender: str,
    profile: str,
    discipline: str,
    as_of: pd.Timestamp,
    model_version: str,
    top_n: int,
    prior_scores: Optional[Dict[str, Tuple[float, int]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    work = _split_score_rows(df, discipline, profile, as_of)
    if work.empty:
        return [], []
    return _group_top_scores(work, gender, profile, discipline, as_of, model_version, top_n, prior_scores=prior_scores)


def _group_top_scores(
    work: pd.DataFrame,
    gender: str,
    profile: str,
    discipline: str,
    as_of: pd.Timestamp,
    model_version: str,
    top_n: int,
    prior_scores: Optional[Dict[str, Tuple[float, int]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    score_rows: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []
    as_of_label  = as_of.strftime("%Y-%m-%d")
    current_year = int(as_of.year)

    for _, g in work.sort_values(
        ["athlete_key", "score_value", "race_date"], ascending=[True, False, False]
    ).groupby("athlete_key", sort=False):

        top = g.sort_values(["score_value", "race_date"], ascending=[False, False]).head(top_n).copy()
        if top.empty:
            continue
        scores = [float(x) for x in pd.to_numeric(top["score_value"], errors="coerce").dropna() if float(x) > 0]
        if not scores:
            continue

        performance_score = float(np.mean(scores))
        athlete_key  = str(top["athlete_key"].iloc[0])
        athlete_url  = _canonical_url(top["athlete_url"].dropna().iloc[0]) if top["athlete_url"].dropna().size else ""
        athlete_name = (_clean(top["athlete_name"].dropna().iloc[0]) if top["athlete_name"].dropna().size
                        else _clean(top["athlete_key"].iloc[0]))

        last     = top.sort_values("race_date", ascending=False).iloc[0]
        cy       = g[g["race_date"].dt.year == current_year]
        cy_scores = pd.to_numeric(cy["score_value"], errors="coerce").dropna().tolist() if not cy.empty else []

        prem_col  = top.get("premium_evidence", pd.Series([False] * len(top), index=top.index))
        str_col   = top.get("strong_evidence",  pd.Series([False] * len(top), index=top.index))
        premium_count = int(prem_col.fillna(False).astype(bool).sum())
        strong_count  = int(str_col.fillna(False).astype(bool).sum())
        confidence    = _confidence(len(scores), premium_count, strong_count)
        last_race_date = _iso_date(last.get("race_date"))

        prior_available = False
        prior_evidence_count = 0
        prior_score = None
        if prior_scores and athlete_key in prior_scores:
            prior_score, prior_evidence_count = prior_scores[athlete_key]
            prior_available = True
        if prior_score is None:
            prior_score = _baseline_prior_score(discipline, profile)
        reliability_weight = _reliability_weight(len(scores), premium_count, strong_count, prior_available)
        # The saved score is now the ranking score. The raw payload keeps the
        # unadjusted performance/ceiling score for explanation.
        score = (performance_score * reliability_weight) + (float(prior_score) * (1.0 - reliability_weight))
        score = float(max(0.0, min(score, 100.0)))

        # Build the raw explainability payload
        raw: Dict[str, Any] = {
            "best_scores_used":       [round(x, 2) for x in scores],
            "performance_score":       round(performance_score, 4),
            "ranking_score":           round(score, 4),
            "prior_score":             round(float(prior_score), 4),
            "prior_available":         bool(prior_available),
            "prior_evidence_count":    int(prior_evidence_count),
            "reliability_weight":      round(float(reliability_weight), 4),
            "premium_evidence_count": premium_count,
            "strong_evidence_count":  strong_count,
            "evidence_count":         len(scores),
            "ranking_method": "performance_score × reliability_weight + prior_score × (1 - reliability_weight)",
        }
        if discipline != "overall":
            raw.update({
                "OpenRank Split Score":   round(score, 2),
                "Performance Split Score": round(performance_score, 2),
                "Prior Score":            round(float(prior_score), 2),
                "Reliability Weight":     round(float(reliability_weight), 2),
                "Best Split Scores Used": ", ".join(f"{x:.1f}" for x in scores),
                "Premium Evidence Count": premium_count,
                "Strong Evidence Count":  strong_count,
                "Evidence Count":         len(scores),
                "Prior Evidence Count":   int(prior_evidence_count),
                "Last Rank":              _clean(last.get("split_rank_display")),
                "Best Recent Split":      _clean(last.get("split_text")),
            })
        else:
            raw.update({
                "OpenRank Score":          round(score, 2),
                "Performance Score":       round(performance_score, 2),
                "Prior Score":             round(float(prior_score), 2),
                "Reliability Weight":      round(float(reliability_weight), 2),
                "Best Scores Used":        ", ".join(f"{x:.1f}" for x in scores),
                "Prior Evidence Count":    int(prior_evidence_count),
            })

        score_rows.append({
            "model_version":       model_version,
            "as_of_date":          as_of_label,
            "profile":             profile,
            "discipline":          discipline,
            "gender":              gender,
            "athlete_url":         athlete_url,
            "athlete_name":        athlete_name,
            "rank":                None,           # filled after sorting
            "score":               round(score, 4),
            "best_scores":         [round(x, 4) for x in scores],
            "evidence_count":      len(scores),
            "current_year_score":  round(float(np.mean(sorted(cy_scores, reverse=True)[:top_n])), 4) if cy_scores else None,
            "current_year_races":  int(len(cy)) if cy is not None else 0,
            "current_year_scored": int(len([x for x in cy_scores if x > 0])) if cy_scores else 0,
            "confidence":          confidence,
            "last_race_name":      _clean(last.get("race_name")),
            "last_race_date":      last_race_date,
            "computed_source":     f"score_engine_v6 · reliability-prior · {gender} · {profile} · {discipline} · top {top_n}",
            "raw":                 _json_row(raw),
        })

        for used_rank, (_, ev) in enumerate(top.iterrows(), start=1):
            ev_score  = _safe_float(ev.get("score_value"))
            ev_rec    = _safe_float(ev.get("recency_factor"))
            ev_rel    = _safe_float(ev.get("relevance_factor"))
            evidence_rows.append({
                "model_version":    model_version,
                "as_of_date":       as_of_label,
                "profile":          profile,
                "discipline":       discipline,
                "gender":           gender,
                "athlete_url":      athlete_url,
                "athlete_name":     athlete_name,
                "used_rank":        used_rank,
                "race_date":        _iso_date(ev.get("race_date")),
                "race_name":        _clean(ev.get("race_name")),
                "race_type":        _clean(ev.get("race_type")),
                "place":            _clean(ev.get("place")),
                "sof":              _safe_float(ev.get("sof")),
                "ors":              _safe_float(ev.get("ors")),
                "split_text":       _clean(ev.get("split_text")) if discipline != "overall" else "",
                "split_rank":       _clean(ev.get("split_rank_display")) if discipline != "overall" else "",
                "pct_behind_fastest": _safe_float(ev.get("pct_behind_fastest")) if discipline != "overall" else None,
                "evidence_score":   round(ev_score, 4) if ev_score is not None else None,
                "raw": _json_row({
                    "Date":               _iso_date(ev.get("race_date")),
                    "Race":               _clean(ev.get("race_name")),
                    "Race Type":          _clean(ev.get("race_type")),
                    "Place":              _clean(ev.get("place")),
                    "SOF":                _safe_float(ev.get("sof")),
                    "ORS":                _safe_float(ev.get("ors")),
                    "Split":              _clean(ev.get("split_text")),
                    "Split Rank":         _clean(ev.get("split_rank_display")),
                    "% Behind Fastest":   _safe_float(ev.get("pct_behind_fastest")),
                    "Evidence Score":     ev_score,
                    "Recency Factor":     ev_rec,
                    "Relevance Factor":   ev_rel,
                    "Premium Evidence":   bool(ev.get("premium_evidence", False)),
                    "Strong Evidence":    bool(ev.get("strong_evidence", False)),
                }),
            })

    # Assign final rank within this slice
    score_rows.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("athlete_name") or "")))
    for i, row in enumerate(score_rows, start=1):
        row["rank"] = i
    return score_rows, evidence_rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prep_results(results: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw results DataFrame once before passing to the slice builder."""
    return _prep_results(results)


def build_scorecard_slice(
    prep_df: pd.DataFrame,
    gender: str,
    profile: str,
    discipline: str,
    as_of_date: Any,
    model_version: str,
    top_n: int = 5,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Build one gender × profile × discipline scorecard slice.

    The app calls this for each of the 32 slices and saves the results
    separately so no single Supabase request covers the full rebuild.
    """
    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        as_of = pd.Timestamp.today().normalize()

    if prep_df is None or prep_df.empty:
        return [], [], {
            "Gender": gender, "Profile": profile, "Discipline": discipline,
            "Rows After Profile": 0, "Candidate Score Rows": 0,
            "Scorecard Rows": 0, "Evidence Rows": 0,
            "Lookback Days": _lookback_days(profile), "Status": "empty results",
        }

    lookback     = _lookback_days(profile)
    window_start = as_of - pd.Timedelta(days=lookback)
    gdf_base     = prep_df[prep_df["gender"] == gender].copy()
    pdf = gdf_base[
        gdf_base["race_date"].notna()
        & (gdf_base["race_date"] >= window_start)
        & (gdf_base["race_date"] <= as_of)
        & _profile_mask(gdf_base, profile)
    ].copy()

    prior_scores: Dict[str, Tuple[float, int]] = {}
    if profile != "All" and not gdf_base.empty:
        prior_window_start = as_of - pd.Timedelta(days=ALL_LOOKBACK_DAYS)
        prior_pdf = gdf_base[
            gdf_base["race_date"].notna()
            & (gdf_base["race_date"] >= prior_window_start)
            & (gdf_base["race_date"] <= as_of)
        ].copy()
        # Remove the current profile/recent evidence rows so the prior is true
        # backup evidence: older same-profile or cross-profile transfer proof.
        if not pdf.empty:
            prior_pdf = prior_pdf.drop(index=pdf.index, errors="ignore")
        if not prior_pdf.empty:
            if discipline == "overall":
                prior_work = _overall_score_rows(prior_pdf, "All", as_of)
            else:
                prior_work = _split_score_rows(prior_pdf, discipline, "All", as_of)
            prior_scores = _prior_score_map(prior_work, top_n)

    try:
        if discipline == "overall":
            candidate_rows = int(pd.to_numeric(pdf.get("ors", pd.Series(dtype=object)), errors="coerce").gt(0).sum())
            cards, evidence = _build_overall_cards(pdf, gender, profile, as_of, model_version, top_n, prior_scores=prior_scores)
        else:
            split_col      = f"{discipline}_seconds"
            candidate_rows = int(pd.to_numeric(pdf.get(split_col, pd.Series(dtype=object)), errors="coerce").gt(0).sum())
            cards, evidence = _build_split_cards(pdf, gender, profile, discipline, as_of, model_version, top_n, prior_scores=prior_scores)
        status = "ok"
    except Exception as exc:
        candidate_rows  = 0
        cards, evidence = [], []
        status          = f"error: {exc}"

    return cards, evidence, {
        "Gender":               gender,
        "Profile":              profile,
        "Discipline":           discipline,
        "Rows After Profile":   int(len(pdf)),
        "Candidate Score Rows": int(candidate_rows),
        "Scorecard Rows":       int(len(cards)),
        "Evidence Rows":        int(len(evidence)),
        "Prior Athletes":       int(len(prior_scores)),
        "Lookback Days":        int(lookback),
        "Status":               status,
    }


def build_all_scorecards(
    results: pd.DataFrame,
    as_of_date: Any,
    model_version: str,
    top_n: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build every gender × profile × discipline scorecard in one pass.

    Returns (scorecards_df, evidence_df, log_df).
    """
    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        as_of = pd.Timestamp.today().normalize()
    df = _prep_results(results)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{"Status": "empty results"}])

    cards:    List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    logs:     List[Dict[str, Any]] = []

    for gender in ["Men", "Women"]:
        for profile in PROFILES:
            for discipline in DISCIPLINES:
                c, e, log = build_scorecard_slice(df, gender, profile, discipline, as_of, model_version, top_n)
                cards.extend(c)
                evidence.extend(e)
                logs.append(log)

    return pd.DataFrame(cards), pd.DataFrame(evidence), pd.DataFrame(logs)
