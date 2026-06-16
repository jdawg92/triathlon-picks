import json
import math
import re
import time
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Triathlon Picks", page_icon="🏁", layout="wide")

# ============================================================
# Supabase connection
# ============================================================
@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# ============================================================
# Visual styling
# ============================================================
def apply_dashboard_theme() -> None:
    """Stripe-inspired UI styling that keeps the app distinct from PTN."""
    st.markdown(
        """
        <style>
        :root {
            --ptn-bg: #F6F9FC;
            --ptn-panel: #FFFFFF;
            --ptn-panel-2: #F7FAFC;
            --ptn-border: #E3E8EF;
            --ptn-text: #0A2540;
            --ptn-muted: #5F6B7A;
            --ptn-red: #635BFF;
            --ptn-orange: #00D4FF;
            --ptn-blue: #635BFF;
            --ptn-green: #00A878;
            --ptn-purple: #7A5CFA;
            --stripe-navy: #0A2540;
            --stripe-purple: #635BFF;
            --stripe-cyan: #00D4FF;
            --stripe-slate: #425466;
            --stripe-soft: #F6F9FC;
        }

        .stApp {
            background:
                radial-gradient(circle at 10% -10%, rgba(99, 91, 255, 0.15), transparent 28rem),
                radial-gradient(circle at 90% 0%, rgba(0, 212, 255, 0.14), transparent 30rem),
                linear-gradient(180deg, #FFFFFF 0%, #F6F9FC 34%, #EEF4FB 100%);
            color: var(--ptn-text);
        }

        [data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.92);
            border-right: 1px solid var(--ptn-border);
            box-shadow: 10px 0 30px rgba(10, 37, 64, 0.04);
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label {
            color: var(--ptn-text);
        }

        .ptn-sidebar-brand {
            padding: 0.85rem 0.35rem 1rem 0.35rem;
            margin-bottom: 0.5rem;
            border-bottom: 1px solid var(--ptn-border);
        }

        .ptn-sidebar-brand .logo {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2.2rem;
            height: 2.2rem;
            border-radius: 0.75rem;
            margin-right: 0.5rem;
            color: white;
            background: linear-gradient(135deg, #635BFF, #00D4FF);
            box-shadow: 0 10px 24px rgba(99, 91, 255, 0.18);
        }

        .ptn-sidebar-brand .title {
            font-weight: 800;
            font-size: 1.05rem;
            color: var(--stripe-navy);
            letter-spacing: -0.025em;
        }

        .ptn-sidebar-brand .subtitle {
            color: var(--ptn-muted);
            font-size: 0.78rem;
            margin-top: 0.15rem;
        }

        .ptn-sidebar-section {
            color: #697386;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            margin: 1.05rem 0 0.35rem 0;
            padding-top: 0.55rem;
            border-top: 1px solid var(--ptn-border);
        }

        .ptn-hero {
            position: relative;
            overflow: hidden;
            padding: 1.45rem 1.6rem;
            border: 1px solid rgba(99, 91, 255, 0.16);
            border-radius: 1.35rem;
            background:
                linear-gradient(135deg, rgba(99, 91, 255, 0.10), rgba(0, 212, 255, 0.08)),
                #FFFFFF;
            box-shadow: 0 24px 65px rgba(10, 37, 64, 0.08);
            margin: 0.25rem 0 1.2rem 0;
        }

        .ptn-hero:after {
            content: "";
            position: absolute;
            width: 18rem;
            height: 18rem;
            right: -7rem;
            top: -8rem;
            background: radial-gradient(circle, rgba(99, 91, 255, 0.18), transparent 64%);
            pointer-events: none;
        }

        .ptn-hero .eyebrow,
        .ptn-race-card .eyebrow {
            color: var(--stripe-purple);
            font-size: 0.74rem;
            font-weight: 900;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .ptn-hero h1 {
            color: var(--stripe-navy);
            font-size: 2.15rem;
            line-height: 1.05;
            margin: 0;
            letter-spacing: -0.045em;
        }

        .ptn-hero p {
            color: var(--ptn-muted);
            margin: 0.55rem 0 0 0;
            font-size: 1rem;
        }

        .ptn-race-card,
        [data-testid="stMetric"],
        div[data-testid="stExpander"] {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid var(--ptn-border);
            box-shadow: 0 18px 45px rgba(10, 37, 64, 0.06);
        }

        .ptn-race-card {
            padding: 1.15rem 1.25rem;
            border-radius: 1.15rem;
            margin: 0.35rem 0 1rem 0;
        }

        .ptn-race-card h2 {
            margin: 0;
            color: var(--stripe-navy);
            font-size: 1.55rem;
            letter-spacing: -0.035em;
        }

        .ptn-race-card .meta {
            color: var(--ptn-muted);
            margin-top: 0.4rem;
            font-size: 0.92rem;
        }

        .ptn-section-title {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: var(--stripe-navy);
            font-weight: 850;
            font-size: 1.3rem;
            letter-spacing: -0.03em;
            margin: 1.25rem 0 0.7rem 0;
        }

        .ptn-pill {
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 750;
            color: #3B2DBF;
            background: rgba(99, 91, 255, 0.10);
            border: 1px solid rgba(99, 91, 255, 0.18);
        }

        [data-testid="stMetric"] {
            border-radius: 1rem;
            padding: 0.9rem 1rem;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--ptn-muted) !important;
            font-weight: 750;
        }

        [data-testid="stMetricValue"] {
            color: var(--stripe-navy);
            font-weight: 900;
        }

        .stDataFrame,
        [data-testid="stDataFrame"] {
            border-radius: 1rem;
            overflow: hidden;
            border: 1px solid var(--ptn-border);
            box-shadow: 0 14px 34px rgba(10, 37, 64, 0.05);
        }

        div[data-testid="stExpander"] {
            border-radius: 1rem;
            overflow: hidden;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }

        .stTabs [data-baseweb="tab"] {
            height: 2.65rem;
            border-radius: 999px;
            padding: 0 1rem;
            background: #FFFFFF;
            color: var(--stripe-slate);
            border: 1px solid var(--ptn-border);
        }

        .stTabs [aria-selected="true"] {
            background: rgba(99, 91, 255, 0.10);
            border-color: rgba(99, 91, 255, 0.32);
            color: var(--stripe-purple);
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 0.72rem;
            border: 1px solid var(--ptn-border);
            background: #FFFFFF;
            color: var(--stripe-navy);
            font-weight: 760;
            box-shadow: 0 8px 18px rgba(10, 37, 64, 0.04);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: rgba(99, 91, 255, 0.34);
            background: #F7F9FF;
            color: var(--stripe-purple);
        }

        [data-testid="stSidebar"] .stButton > button {
            justify-content: flex-start;
            text-align: left;
            padding-left: 0.85rem;
            background: #FFFFFF !important;
            border-color: #E6EBF2 !important;
            color: #344054 !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: #F6F9FC !important;
            border-color: rgba(99, 91, 255, 0.28) !important;
            color: var(--stripe-purple) !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] .stButton button[data-testid="baseButton-primary"] {
            background: rgba(99, 91, 255, 0.09) !important;
            border-color: rgba(99, 91, 255, 0.34) !important;
            color: #3B2DBF !important;
            box-shadow: none !important;
        }

        .stSelectbox,
        .stSlider,
        .stRadio,
        .stFileUploader,
        .stCheckbox,
        label,
        p,
        span,
        div {
            color: inherit;
        }

        div[data-testid="stAlert"] {
            border-radius: 1rem;
            border: 1px solid var(--ptn-border);
        }

        h1,
        h2,
        h3 {
            color: var(--stripe-navy);
            letter-spacing: -0.035em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_app_hero(page_name: str) -> None:
    st.markdown(
        f"""
        <div class="ptn-hero">
            <div class="eyebrow">Triathlon Picks Lab</div>
            <h1>🏁 {page_name}</h1>
            <p>Race predictions, split picks, evidence drilldowns, and scoring audits powered by Supabase.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_race_card(race_name: str, gender: str, race_date: Any, window_start: Any) -> None:
    st.markdown(
        f"""
        <div class="ptn-race-card">
            <div class="eyebrow">Selected Race</div>
            <h2>{race_name}</h2>
            <div class="meta">{gender} · Race date {format_date(race_date)} · Analysis window {format_date(window_start)} to {format_date(race_date)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(icon: str, title: str) -> None:
    st.markdown(f'<div class="ptn-section-title"><span>{icon}</span><span>{title}</span></div>', unsafe_allow_html=True)

# ============================================================
# Basic helpers
# ============================================================
def clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "—", "-"}:
        return None
    return s


def first_col(row: pd.Series, aliases: Iterable[str]) -> Any:
    normalized = {str(c).strip().lower(): c for c in row.index}
    for alias in aliases:
        key = alias.strip().lower()
        if key in normalized:
            return row[normalized[key]]
    return None


def parse_date_value(value: Any) -> Optional[str]:
    s = clean_str(value)
    if not s:
        return None
    s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?.*$", "", s).strip()
    for fmt in ["%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%b %d, %y", "%B %d, %y"]:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date().isoformat()
    except Exception:
        return None


def parse_number(value: Any) -> Optional[float]:
    s = clean_str(value)
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").strip()
    is_percent = s.endswith("%")
    s = s.replace("%", "")
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s):
        return None
    try:
        n = float(s)
        if is_percent and n <= 1:
            n *= 100
        return n
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    n = parse_number(value)
    if n is None:
        return None
    return int(round(n))

def dedupe_start_athletes(start_athletes: pd.DataFrame) -> pd.DataFrame:
    """Return one row per athlete for the selected start list.

    Start lists can be imported more than once or contain duplicate athlete rows.
    Pandas lookup tables require unique keys, and duplicate start-list rows also
    inflate dashboard counts and split scoring. Prefer rows with an athlete URL
    and the lowest OpenRank when duplicates exist.
    """
    if start_athletes is None or start_athletes.empty:
        return pd.DataFrame() if start_athletes is None else start_athletes

    df = start_athletes.copy()
    if "athlete_url" not in df.columns:
        df["athlete_url"] = None
    if "athlete_name" not in df.columns:
        df["athlete_name"] = None
    if "open_rank" not in df.columns:
        df["open_rank"] = None

    df["__athlete_url_key"] = df["athlete_url"].map(lambda x: (canonical_athlete_url(x) or "").strip().lower())
    df["__athlete_name_key"] = df["athlete_name"].map(lambda x: (clean_str(x) or "").strip().lower())
    df["__athlete_key"] = df["__athlete_url_key"]
    missing_url = df["__athlete_key"].eq("")
    df.loc[missing_url, "__athlete_key"] = df.loc[missing_url, "__athlete_name_key"]
    df = df[df["__athlete_key"].ne("")].copy()
    if df.empty:
        return df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore")

    df["__has_url"] = df["__athlete_url_key"].ne("").astype(int)
    df["__open_rank_num"] = df["open_rank"].map(parse_int)
    df["__open_rank_sort"] = df["__open_rank_num"].fillna(999999)
    df = df.sort_values(["__athlete_key", "__has_url", "__open_rank_sort"], ascending=[True, False, True])
    df = df.drop_duplicates(subset=["__athlete_key"], keep="first").copy()
    return df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore").reset_index(drop=True)


def start_lookup_maps(start_athletes: pd.DataFrame) -> tuple[dict, dict]:
    """Build safe URL/name lookup maps for a de-duplicated start list."""
    df = dedupe_start_athletes(start_athletes)
    url_lookup = {}
    name_lookup = {}
    if df.empty:
        return url_lookup, name_lookup
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        url = canonical_athlete_url(row.get("athlete_url"))
        name = clean_str(row.get("athlete_name"))
        if url and url not in url_lookup:
            url_lookup[url] = row_dict
        if name:
            key = name.lower()
            if key not in name_lookup:
                name_lookup[key] = row_dict
    return url_lookup, name_lookup


def parse_status(row: pd.Series) -> Optional[str]:
    status = clean_str(first_col(row, ["Status", "Result Status"]))
    place = clean_str(first_col(row, ["Place", "Rank", "Finish Place"]))
    combined = " ".join([x for x in [status, place] if x]).upper()
    for token in ["DNF", "DNS", "DSQ", "DQ"]:
        if token in combined:
            return token
    return status


def is_bad_status(status: Any, place: Any = None) -> bool:
    combined = " ".join([clean_str(status) or "", clean_str(place) or ""]).upper()
    return any(token in combined for token in ["DNF", "DNS", "DSQ", "DQ", "DNQ"])


def is_excluded_for_split_status(status: Any, place: Any = None, discipline: str = "") -> bool:
    """Return whether a result status should exclude a discipline split.

    Default rule: DNF/DNS/DSQ/DQ/DNQ rows are audit-only and never part of
    the used split score. We still keep them in the "All evaluated rows" view
    so it is clear why a recent result did not count, but they should not show
    under "Used in score" and should not affect split ranks, gap percentages,
    or evidence scores.
    """
    combined = " ".join([clean_str(status) or "", clean_str(place) or ""]).upper()
    return any(token in combined for token in ["DNF", "DNS", "DSQ", "DQ", "DNQ"])


def parse_place(value: Any) -> Optional[str]:
    s = clean_str(value)
    if not s:
        return None
    if re.search(r"DNF|DNS|DSQ|DQ", s, re.I):
        return s.upper()
    n = parse_number(s)
    if n is not None and 0 < n < 10000:
        return str(int(round(n)))
    return s


def parse_place_number(value: Any) -> Optional[int]:
    s = clean_str(value)
    if not s or re.search(r"DNF|DNS|DSQ|DQ", s, re.I):
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    return int(m.group(0))


def normalize_gender(value: Any) -> Optional[str]:
    s = clean_str(value)
    if not s:
        return None
    low = s.lower()
    if low.startswith("m"):
        return "Men"
    if low.startswith("w") or low.startswith("f"):
        return "Women"
    return s


def race_gender_compatible(race_name: Any, selected_gender: str) -> bool:
    """Use race-name hints to avoid obvious mixed-gender field comparisons.

    Many imported Athlete Results rows do not have gender. If we require a
    gender value, the same-race field collapses to only the current start-list
    athletes and every split gets excluded. This allows unknown-gender rows
    unless the race name clearly says the opposite gender.
    """
    name = (clean_str(race_name) or "").lower()
    gender = normalize_gender(selected_gender) or selected_gender
    women_hints = ["women", "women's", "female", "femmes"]
    men_hints = ["men", "men's", "male", "hommes"]
    if gender == "Men":
        return not any(h in name for h in women_hints)
    if gender == "Women":
        return not any(h in name for h in men_hints)
    return True


def format_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        d = pd.to_datetime(value, errors="coerce")
        if pd.isna(d):
            return str(value)
        return d.strftime("%-d %b %Y")
    except Exception:
        try:
            d = datetime.strptime(str(value), "%Y-%m-%d")
            return d.strftime("%-d %b %Y")
        except Exception:
            return str(value)


def parse_split_seconds(value: Any, discipline: str, race_type: Optional[str] = None) -> Optional[int]:
    s = clean_str(value)
    if not s:
        return None

    # If it came from DB as a numeric seconds value, use it.
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)) and not math.isnan(float(value)):
        # Ignore tiny spreadsheet date fractions; accept realistic seconds.
        if value > 200:
            return int(round(value))

    # Reject obvious corrupted Sheets durations like 2028:00:00.
    if re.match(r"^\d{4,}:\d{2}:\d{2}$", s):
        return None

    parts = s.split(":")
    seconds = None
    try:
        if len(parts) == 3:
            h, m, sec = [int(float(p)) for p in parts]
            seconds = h * 3600 + m * 60 + sec
        elif len(parts) == 2:
            a, b = [int(float(p)) for p in parts]
            rt = (race_type or "").lower()
            if discipline == "swim":
                seconds = a * 60 + b
            elif discipline == "bike":
                seconds = a * 3600 + b * 60
            elif discipline == "run":
                short_course = any(x in rt for x in ["wtcs", "world triathlon", "continental", "sprint", "olympic"])
                if short_course and a >= 14:
                    seconds = a * 60 + b
                else:
                    seconds = a * 3600 + b * 60
        elif len(parts) == 1:
            n = parse_number(s)
            if n is not None:
                seconds = int(round(n))
    except Exception:
        return None

    if seconds is None:
        return None
    return validate_split_seconds(seconds, discipline, race_type)


def validate_split_seconds(seconds: Optional[int], discipline: str, race_type: Optional[str]) -> Optional[int]:
    if seconds is None:
        return None
    rt = (race_type or "").lower()

    if discipline == "swim":
        if "full" in rt or "140.6" in rt:
            return seconds if 35 * 60 <= seconds <= 95 * 60 else None
        if any(x in rt for x in ["sprint", "world triathlon", "continental", "wtcs", "olympic"]):
            return seconds if 5 * 60 <= seconds <= 25 * 60 else None
        return seconds if 12 * 60 <= seconds <= 65 * 60 else None

    if discipline == "bike":
        if any(x in rt for x in ["wtcs", "draft", "world triathlon", "continental"]):
            return None
        if "full" in rt or "140.6" in rt:
            return seconds if 3 * 3600 <= seconds <= 6 * 3600 else None
        if any(x in rt for x in ["sprint", "olympic"]):
            return seconds if 15 * 60 <= seconds <= 2 * 3600 else None
        return seconds if 75 * 60 <= seconds <= 4 * 3600 else None

    if discipline == "run":
        if "full" in rt or "140.6" in rt:
            return seconds if 2 * 3600 <= seconds <= 5 * 3600 else None
        if any(x in rt for x in ["sprint", "world triathlon", "continental", "wtcs", "olympic"]):
            return seconds if 14 * 60 <= seconds <= 75 * 60 else None
        return seconds if 55 * 60 <= seconds <= 2.25 * 3600 else None

    return seconds


def format_seconds(seconds: Any) -> str:
    if seconds is None or pd.isna(seconds):
        return ""
    seconds = int(round(float(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def normalize_race_type(race_name: Optional[str], race_type: Optional[str], distance: Optional[str]) -> Optional[str]:
    # Values coming back from Supabase/pandas may be strings, floats, NaN, dates, or numbers.
    # Always coerce through clean_str before joining so the app does not crash on imported CSV data.
    txt = " ".join([clean_str(race_name) or "", clean_str(race_type) or "", clean_str(distance) or ""]).lower()
    if "t100" in txt or "pto" in txt:
        return "T100"
    if "wtcs" in txt or "world triathlon championship series" in txt:
        return "WTCS"
    if "world triathlon cup" in txt:
        return "World Triathlon Cup"
    if any(x in txt for x in ["americas triathlon cup", "europe triathlon cup", "asia triathlon cup", "africa triathlon cup", "oceania triathlon cup"]):
        return "Continental Cup"
    if "challenge" in txt:
        return "Challenge Middle"
    if ("ironman" in txt and "70.3" not in txt) or "140.6" in txt or "full" in txt:
        return "Full"
    if "70.3" in txt or "middle" in txt:
        return "70.3"
    if "olympic" in txt:
        return "Olympic"
    if "sprint" in txt:
        return "Sprint"
    return clean_str(race_type) or clean_str(distance)


def filter_rankings_by_gender(df: pd.DataFrame, selected_gender: str) -> pd.DataFrame:
    """Gender filter for global athlete rankings.

    Known opposite-gender rows are excluded. Unknown-gender rows are kept only
    when the race name does not explicitly indicate the opposite gender. This is
    important because older athlete-history imports often have blank gender, and
    excluding every unknown row hides athletes such as short-course/T100 racers
    whose profiles were imported before gender was available.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    gender = normalize_gender(selected_gender)
    if not gender:
        return df.copy()

    out = df.copy()
    if "gender" not in out.columns:
        out["gender"] = None
    out["__gender_norm"] = out["gender"].map(normalize_gender)

    if "race_name" in out.columns:
        names = out["race_name"].map(lambda x: (clean_str(x) or "").lower())
        explicit_men = names.str.contains(r"\bmen\b|men's|male", regex=True, na=False)
        explicit_women = names.str.contains(r"\bwomen\b|women's|female", regex=True, na=False)
        missing = out["__gender_norm"].isna()
        out.loc[missing & explicit_men, "__gender_norm"] = "Men"
        out.loc[missing & explicit_women, "__gender_norm"] = "Women"

    known_match = out["__gender_norm"].eq(gender)
    unknown = out["__gender_norm"].isna()
    if "race_name" in out.columns:
        compatible_unknown = unknown & out["race_name"].map(lambda x: race_gender_compatible(x, gender))
    else:
        compatible_unknown = unknown

    out = out[known_match | compatible_unknown].copy()
    out["gender_filter_note"] = np.where(out["__gender_norm"].isna(), "unknown gender included", "known gender")
    return out.drop(columns=["__gender_norm"], errors="ignore")


def ranking_scope_mask(df: pd.DataFrame, scope: str) -> pd.Series:
    """Return a boolean mask for the selected race-family ranking scope."""
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    rt = df.get("race_type", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    race = df.get("race_name", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    dist = df.get("distance", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    txt = (rt + " " + race + " " + dist)

    if scope == "IRONMAN 70.3 / Middle":
        return txt.str.contains("70.3|middle|challenge", regex=True, na=False) & ~txt.str.contains("t100|pto", regex=True, na=False)
    if scope == "T100 / PTO":
        return txt.str.contains("t100|pto", regex=True, na=False)
    if scope == "Full IRONMAN":
        return txt.str.contains("full|140.6", regex=True, na=False) | ((txt.str.contains("ironman", na=False)) & ~txt.str.contains("70.3", na=False))
    if scope == "Short Course / WTCS":
        return txt.str.contains("wtcs|world triathlon|continental|olympic|sprint", regex=True, na=False)
    return pd.Series([True] * len(df), index=df.index)




def prediction_scope_from_race(race_name: Any, race_type: Any = None, distance: Any = None) -> str:
    """Choose which result family should feed a selected-race predictor.

    For WTCS/World Triathlon/short-course start lists, we should not pull in
    70.3 or full-distance evidence. Those races answer a different question.
    """
    rt = normalize_race_type(race_name, race_type, distance)
    txt = " ".join([clean_str(race_name) or "", clean_str(race_type) or "", clean_str(distance) or ""]).lower()
    if rt in {"WTCS", "World Triathlon Cup", "Continental Cup", "Olympic", "Sprint"}:
        return "Short Course / WTCS"
    if any(x in txt for x in ["wtcs", "world triathlon", "olympic", "sprint", "triathlon cup"]):
        return "Short Course / WTCS"
    if rt == "T100":
        return "T100 / PTO"
    if rt == "Full":
        return "Full IRONMAN"
    return "IRONMAN 70.3 / Middle"


def apply_prediction_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """Filter results to the race family appropriate for the selected predictor.

    Short-course/WTCS prediction uses only sprint, Olympic, WTCS, World
    Triathlon Cup, and continental-cup style evidence. For 70.3/T100/full, we
    leave the broader two-year window available because cross-family evidence
    can still be useful and is already weighted/capped by the scoring model.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if scope == "Short Course / WTCS":
        return df[ranking_scope_mask(df, "Short Course / WTCS")].copy()
    return df.copy()


def championship_result_score(row: pd.Series) -> float:
    """Extra overall signal for championship wins/podiums.

    This helps the global 70.3 ranking respect athletes with true world-title
    evidence instead of overrating normal race consistency.
    """
    race = (clean_str(row.get("race_name")) or "").lower()
    rt = (clean_str(row.get("race_type")) or "").lower()
    place = parse_place_number(row.get("place"))
    if place is None:
        return 0.0
    is_champs = any(x in race for x in ["world championship", "world championships", "championship final", "olympic games"])
    if not is_champs:
        return 0.0
    base = 0.0
    if place == 1:
        base = 100.0
    elif place == 2:
        base = 94.0
    elif place == 3:
        base = 90.0
    elif place <= 5:
        base = 84.0
    elif place <= 10:
        base = 76.0
    else:
        base = 62.0
    # 70.3 Worlds and T100 finals are especially relevant to those ranking scopes.
    if "70.3" in race or "70.3" in rt or "t100" in race or "t100" in rt:
        return base
    return base * 0.8

def json_safe_row(row: pd.Series) -> Dict[str, Any]:
    out = {}
    for k, v in row.to_dict().items():
        if isinstance(v, float) and math.isnan(v):
            out[str(k)] = None
        elif isinstance(v, (np.integer,)):
            out[str(k)] = int(v)
        elif isinstance(v, (np.floating,)):
            out[str(k)] = float(v)
        else:
            out[str(k)] = None if pd.isna(v) else str(v)
    return out


def parse_raw_payload(value: Any) -> Dict[str, Any]:
    """Return the original imported CSV row stored in athlete_results.raw.

    Supabase may return jsonb as a dict, but older imports or previews can come
    back as JSON strings. This lets the dashboard re-parse split times without
    requiring a full CSV re-import.
    """
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, float) and math.isnan(value):
        return {}
    if isinstance(value, str):
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def first_from_mapping(mapping: Dict[str, Any], aliases: Iterable[str]) -> Any:
    if not mapping:
        return None
    normalized = {str(k).strip().lower(): k for k in mapping.keys()}
    for alias in aliases:
        key = alias.strip().lower()
        if key in normalized:
            return mapping[normalized[key]]
    return None


def recover_split_from_raw(row: pd.Series, discipline: str) -> Optional[int]:
    raw = parse_raw_payload(row.get("raw"))
    if not raw:
        return None
    aliases = {
        "swim": ["Swim", "Swim Split", "swim", "swim_seconds"],
        "bike": ["Bike", "Bike Split", "bike", "bike_seconds"],
        "run": ["Run", "Run Split", "run", "run_seconds"],
    }[discipline]
    value = first_from_mapping(raw, aliases)
    return parse_split_seconds(value, discipline, clean_str(row.get("race_type")))



def recover_number_from_raw(row: pd.Series, aliases: Iterable[str]) -> Optional[float]:
    """Recover numeric fields such as ORS/SOF from the stored raw CSV payload.

    This protects older imports where the normalized column was blank because
    the uploaded CSV used a slightly different header, while the original value
    still exists inside the jsonb raw column.
    """
    raw = parse_raw_payload(row.get("raw"))
    if not raw:
        return None
    value = first_from_mapping(raw, aliases)
    return parse_number(value)


ORS_ALIASES = [
    "ORS", "OpenRank Score", "Open Rank Score", "Race Score", "Result Score",
    "Score", "score", "ors", "openrank_score", "open_rank_score", "race_score",
]

SOF_ALIASES = [
    "SOF", "Strength of Field", "Field Strength", "sof", "strength_of_field",
]


def read_uploaded_csv(uploaded_file) -> pd.DataFrame:
    try:
        return pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, encoding="latin-1")


def pct_fmt(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{decimals}f}%"


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


def weighted_avg(values: List[float], weights: Optional[List[float]] = None) -> Optional[float]:
    vals = []
    wts = []
    for i, v in enumerate(values):
        fv = safe_float(v)
        if fv is None:
            continue
        w = 1.0 if weights is None else safe_float(weights[i])
        if w is None or w <= 0:
            continue
        vals.append(fv)
        wts.append(w)
    if not vals:
        return None
    return sum(v * w for v, w in zip(vals, wts)) / sum(wts)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

# ============================================================
# Supabase data helpers
# ============================================================
def fetch_all(table_name: str, select: str = "*", page_size: int = 1000) -> List[Dict[str, Any]]:
    """Fetch every row from Supabase using explicit pagination.

    Supabase/PostgREST responses are range-limited, so a single select can
    silently look like it only has the first page. This helper keeps paging
    until the table is exhausted.
    """
    all_rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        res = supabase.table(table_name).select(select).range(start, end).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size
    return all_rows


def count_rows(table_name: str) -> Optional[int]:
    """Return an exact Supabase table count when available."""
    try:
        res = supabase.table(table_name).select("id", count="exact").limit(1).execute()
        return int(res.count or 0)
    except Exception:
        return None


@st.cache_data(ttl=60)
def load_table(table_name: str) -> pd.DataFrame:
    """Load a Supabase table. Missing optional tables return an empty frame."""
    try:
        return pd.DataFrame(fetch_all(table_name))
    except Exception:
        return pd.DataFrame()


def clear_cache():
    st.cache_data.clear()


def delete_all(table_name: str):
    supabase.table(table_name).delete().gte("id", 0).execute()


def insert_chunks(table_name: str, rows: List[Dict[str, Any]], chunk_size: int = 500):
    if not rows:
        return
    for i in range(0, len(rows), chunk_size):
        supabase.table(table_name).insert(rows[i:i + chunk_size]).execute()


def upsert_chunks(table_name: str, rows: List[Dict[str, Any]], on_conflict: str, chunk_size: int = 500):
    if not rows:
        return
    for i in range(0, len(rows), chunk_size):
        supabase.table(table_name).upsert(rows[i:i + chunk_size], on_conflict=on_conflict).execute()


def athlete_upsert_rows_preserve_gender(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prepare athlete upserts without overwriting known gender with blank/null.

    Supabase upserts can update provided columns on conflict. Imported Athlete
    Results often have gender blank, so sending {gender: None} can erase a
    gender that was already learned from a start list. This helper omits the
    gender key when it is missing.
    """
    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        athlete_url = canonical_athlete_url(row.get("athlete_url"))
        athlete_name = clean_str(row.get("athlete_name"))
        if not athlete_url:
            continue
        out = {"athlete_url": athlete_url, "athlete_name": athlete_name}
        g = normalize_gender(row.get("gender"))
        if g in ["Men", "Women"]:
            out["gender"] = g
        key = (athlete_url, out.get("gender"))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(out)
    return cleaned


def upsert_athletes_preserve_gender(rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Merge athlete records by canonical URL without creating duplicates.

    This does not rely only on Supabase upsert because older DBs may not yet
    have a unique constraint on athletes.athlete_url. It first checks existing
    athletes by canonical URL, updates the existing row when found, and inserts
    only truly new athlete URLs.

    Returns: (inserted_count, updated_count).
    """
    prepared = athlete_upsert_rows_preserve_gender(rows)
    if not prepared:
        return 0, 0

    existing = load_table("athletes")
    existing_map: Dict[str, Dict[str, Any]] = {}
    if existing is not None and not existing.empty and "athlete_url" in existing.columns:
        for _, r in existing.iterrows():
            url = canonical_athlete_url(r.get("athlete_url"))
            if not url or url in existing_map:
                continue
            existing_map[url] = r.to_dict()

    to_insert: List[Dict[str, Any]] = []
    updated = 0
    for row in prepared:
        url = canonical_athlete_url(row.get("athlete_url"))
        if not url:
            continue
        row = dict(row)
        row["athlete_url"] = url
        existing_row = existing_map.get(url)
        if existing_row:
            payload: Dict[str, Any] = {"athlete_url": url}
            incoming_name = clean_str(row.get("athlete_name"))
            existing_name = clean_str(existing_row.get("athlete_name"))
            incoming_gender = normalize_gender(row.get("gender"))
            existing_gender = normalize_gender(existing_row.get("gender"))
            if incoming_name and not existing_name:
                payload["athlete_name"] = incoming_name
            if incoming_gender in ["Men", "Women"] and existing_gender not in ["Men", "Women"]:
                payload["gender"] = incoming_gender
            existing_url_raw = clean_str(existing_row.get("athlete_url"))
            if len(payload) > 1 or existing_url_raw != url:
                try:
                    if existing_row.get("id") is not None:
                        supabase.table("athletes").update(payload).eq("id", existing_row.get("id")).execute()
                    else:
                        supabase.table("athletes").update(payload).eq("athlete_url", existing_row.get("athlete_url")).execute()
                    updated += 1
                except Exception:
                    pass
        else:
            to_insert.append(row)
            existing_map[url] = row

    if to_insert:
        insert_chunks("athletes", to_insert)
    return len(to_insert), updated


def start_list_import_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Stable key for one athlete in one race/gender start list."""
    race_name = (clean_str(row.get("race_name")) or "").strip().lower()
    race_date = clean_str(row.get("race_date")) or ""
    gender = normalize_gender(row.get("gender")) or ""
    athlete_key = canonical_athlete_url(row.get("athlete_url")) or (clean_str(row.get("athlete_name")) or "").strip().lower()
    return race_name, race_date, gender, athlete_key


def dedupe_start_list_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate rows inside one uploaded start-list CSV."""
    best: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for row in rows or []:
        row = dict(row)
        row["athlete_url"] = canonical_athlete_url(row.get("athlete_url"))
        key = start_list_import_key(row)
        if not key[-1]:
            continue
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        row_rank = parse_int(row.get("open_rank")) or 999999
        current_rank = parse_int(current.get("open_rank")) or 999999
        if (row.get("athlete_url") and not current.get("athlete_url")) or row_rank < current_rank:
            best[key] = row
    return list(best.values())


def merge_start_list_rows(rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Insert only new start-list athletes; skip rows already present."""
    rows = dedupe_start_list_rows(rows)
    if not rows:
        return 0, 0

    existing = load_table("start_lists")
    existing_keys = set()
    if existing is not None and not existing.empty:
        existing = canonicalize_athlete_url_column(existing)
        for _, r in existing.iterrows():
            existing_keys.add(start_list_import_key(r.to_dict()))

    to_insert = []
    skipped = 0
    for row in rows:
        key = start_list_import_key(row)
        if key in existing_keys:
            skipped += 1
            continue
        to_insert.append(row)
        existing_keys.add(key)

    if to_insert:
        insert_chunks("start_lists", to_insert)
    return len(to_insert), skipped


def delete_matching_start_lists(rows: List[Dict[str, Any]]) -> int:
    """Delete only the race/date/gender groups included in an uploaded start list."""
    groups = set()
    for row in rows or []:
        race_name = clean_str(row.get("race_name"))
        race_date = clean_str(row.get("race_date"))
        gender = normalize_gender(row.get("gender"))
        if race_name and race_date and gender:
            groups.add((race_name, race_date, gender))
    deleted_groups = 0
    for race_name, race_date, gender in groups:
        try:
            supabase.table("start_lists").delete().eq("race_name", race_name).eq("race_date", race_date).eq("gender", gender).execute()
            deleted_groups += 1
        except Exception:
            pass
    return deleted_groups


def merge_duplicate_athlete_urls() -> pd.DataFrame:
    """Canonicalize athlete URLs and merge duplicate athlete records."""
    athletes_df = load_table("athletes")
    if athletes_df is None or athletes_df.empty or "athlete_url" not in athletes_df.columns:
        return pd.DataFrame()

    df = athletes_df.copy()
    df["canonical_url"] = df["athlete_url"].map(canonical_athlete_url)
    df = df[df["canonical_url"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    logs: List[Dict[str, Any]] = []
    related_tables = ["athlete_results", "race_field_results", "start_lists", "race_overrides"]

    for canonical_url, group in df.groupby("canonical_url", dropna=True):
        original_urls = sorted({clean_str(x) for x in group["athlete_url"].tolist() if clean_str(x)})
        needs_merge = len(group) > 1 or any(u != canonical_url for u in original_urls)
        if not needs_merge:
            continue

        g = group.copy()
        g["__is_canonical"] = g["athlete_url"].map(lambda x: 1 if clean_str(x) == canonical_url else 0)
        g["__has_gender"] = g["gender"].map(lambda x: 1 if normalize_gender(x) in ["Men", "Women"] else 0) if "gender" in g.columns else 0
        g["__has_name"] = g["athlete_name"].map(lambda x: 1 if clean_str(x) else 0) if "athlete_name" in g.columns else 0
        g = g.sort_values(["__is_canonical", "__has_gender", "__has_name", "id"], ascending=[False, False, False, True])
        keeper = g.iloc[0].to_dict()
        keeper_id = keeper.get("id")

        name_vals = [clean_str(x) for x in group.get("athlete_name", pd.Series(dtype=object)).tolist() if clean_str(x)]
        gender_vals = [normalize_gender(x) for x in group.get("gender", pd.Series(dtype=object)).tolist() if normalize_gender(x) in ["Men", "Women"]]
        merged_name = clean_str(keeper.get("athlete_name")) or (name_vals[0] if name_vals else None)
        merged_gender = normalize_gender(keeper.get("gender")) or (gender_vals[0] if gender_vals else None)

        ref_updates = 0
        for table in related_tables:
            for old_url in original_urls:
                if not old_url or old_url == canonical_url:
                    continue
                try:
                    supabase.table(table).update({"athlete_url": canonical_url}).eq("athlete_url", old_url).execute()
                    ref_updates += 1
                except Exception:
                    pass

        deleted = 0
        for _, r in g.iterrows():
            rid = r.get("id")
            if keeper_id is not None and rid == keeper_id:
                continue
            if rid is None:
                continue
            try:
                supabase.table("athletes").delete().eq("id", rid).execute()
                deleted += 1
            except Exception:
                pass

        payload = {"athlete_url": canonical_url}
        if merged_name:
            payload["athlete_name"] = merged_name
        if merged_gender in ["Men", "Women"]:
            payload["gender"] = merged_gender
        try:
            if keeper_id is not None:
                supabase.table("athletes").update(payload).eq("id", keeper_id).execute()
            else:
                supabase.table("athletes").update(payload).eq("athlete_url", keeper.get("athlete_url")).execute()
        except Exception:
            pass

        logs.append({
            "Canonical URL": canonical_url,
            "Kept Athlete": merged_name,
            "Gender": merged_gender,
            "Original URL Count": len(original_urls),
            "Duplicate Athlete Rows Deleted": deleted,
            "Related Table URL Updates Attempted": ref_updates,
            "Original URLs": "; ".join(original_urls),
        })

    clear_cache()
    return pd.DataFrame(logs)


def infer_gender_from_race_name(value: Any) -> Optional[str]:
    """Infer competition category only from explicit race-name wording."""
    name = (clean_str(value) or "").lower()
    if re.search(r"\bwomen\b|women['’]s|\bfemale\b|\bfemmes\b", name):
        return "Women"
    # Match Men safely without firing on Women.
    if re.search(r"(?<!wo)\bmen\b|men['’]s|\bmale\b|\bhommes\b", name):
        return "Men"
    return None


def build_gender_suggestions(athletes: pd.DataFrame, starts: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Build high-confidence gender suggestions from data we already own.

    Sources, in order of trust:
    1. Start lists imported with a Men/Women category.
    2. Existing known gender values in athlete/result tables.
    3. Explicit race-name hints such as Men's/Women's.

    We do not infer from athlete name, image, country, or profile scraping.
    """
    rows: Dict[str, Dict[str, Any]] = {}

    def add_signal(url: Any, name: Any, gender: Any, source: str, confidence: str):
        g = normalize_gender(gender)
        if g not in ["Men", "Women"]:
            return
        u = canonical_athlete_url(url)
        n = clean_str(name)
        if not u and not n:
            return
        key = u or f"name::{(n or '').lower()}"
        rec = rows.setdefault(key, {
            "Athlete URL": u,
            "Athlete": n,
            "Signals": [],
            "Source": source,
            "Confidence": confidence,
        })
        if n and not rec.get("Athlete"):
            rec["Athlete"] = n
        if u and not rec.get("Athlete URL"):
            rec["Athlete URL"] = u
        rec["Signals"].append((g, source, confidence))

    if starts is not None and not starts.empty:
        for _, r in starts.iterrows():
            add_signal(r.get("athlete_url"), r.get("athlete_name"), r.get("gender"), "Start list", "High")

    for df_name, df in [("Athletes table", athletes), ("Result gender", results)]:
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            add_signal(r.get("athlete_url"), r.get("athlete_name"), r.get("gender"), df_name, "High" if df_name == "Athletes table" else "Medium")

    if results is not None and not results.empty:
        for _, r in results.iterrows():
            g = infer_gender_from_race_name(r.get("race_name"))
            add_signal(r.get("athlete_url"), r.get("athlete_name"), g, "Race name hint", "Medium")

    output = []
    for rec in rows.values():
        genders = {g for g, _, _ in rec.get("Signals", []) if g in ["Men", "Women"]}
        sources = sorted({src for _, src, _ in rec.get("Signals", [])})
        confidences = {conf for _, _, conf in rec.get("Signals", [])}
        if len(genders) == 1:
            suggested = next(iter(genders))
            confidence = "High" if "High" in confidences else "Medium"
            conflict = "No"
        elif len(genders) > 1:
            suggested = "Conflict"
            confidence = "Low"
            conflict = "Yes"
        else:
            suggested = None
            confidence = "None"
            conflict = "No"
        output.append({
            "Athlete": rec.get("Athlete"),
            "Athlete URL": rec.get("Athlete URL"),
            "Suggested Gender": suggested,
            "Confidence": confidence,
            "Conflict": conflict,
            "Sources": ", ".join(sources),
            "Signal Count": len(rec.get("Signals", [])),
        })
    if not output:
        return pd.DataFrame(columns=["Athlete", "Athlete URL", "Suggested Gender", "Confidence", "Conflict", "Sources", "Signal Count"])
    return pd.DataFrame(output).sort_values(["Conflict", "Confidence", "Athlete"], ascending=[True, True, True])


def apply_gender_updates(suggestions: pd.DataFrame, include_medium: bool = False) -> int:
    """Apply selected gender suggestions across athlete/result tables."""
    if suggestions is None or suggestions.empty:
        return 0
    allowed_conf = ["High", "Medium"] if include_medium else ["High"]
    work = suggestions[
        suggestions["Suggested Gender"].isin(["Men", "Women"])
        & suggestions["Confidence"].isin(allowed_conf)
        & suggestions["Conflict"].ne("Yes")
    ].copy()
    applied = 0
    progress = st.progress(0, text="Applying gender updates...") if len(work) else None
    for idx, (_, r) in enumerate(work.iterrows(), start=1):
        g = normalize_gender(r.get("Suggested Gender"))
        url = canonical_athlete_url(r.get("Athlete URL"))
        name = clean_str(r.get("Athlete"))
        if not g or (not url and not name):
            continue
        for table in ["athletes", "athlete_results", "race_field_results", "start_lists"]:
            try:
                query = supabase.table(table).update({"gender": g})
                if url:
                    query = query.eq("athlete_url", url)
                else:
                    query = query.eq("athlete_name", name)
                query.execute()
            except Exception:
                # Optional table may not exist or row may not be present.
                pass
        applied += 1
        if progress is not None and (idx % 25 == 0 or idx == len(work)):
            progress.progress(idx / max(len(work), 1), text=f"Applied {idx:,} of {len(work):,} gender updates...")
    if progress is not None:
        progress.empty()
    clear_cache()
    return applied


def apply_gender_updates_from_rows(rows: List[Dict[str, Any]]) -> int:
    """Immediately propagate gender from newly imported start-list rows."""
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    if df.empty or "gender" not in df.columns:
        return 0
    # Only apply unambiguous athlete -> one gender signals.
    key_col = "athlete_url" if "athlete_url" in df.columns else "athlete_name"
    df["gender_norm"] = df["gender"].map(normalize_gender)
    df = df[df["gender_norm"].isin(["Men", "Women"])]
    if df.empty:
        return 0
    suggestions = []
    for key, g in df.groupby(df[key_col].fillna(df.get("athlete_name", ""))):
        genders = set(g["gender_norm"].dropna())
        if len(genders) != 1:
            continue
        row = g.iloc[0]
        suggestions.append({
            "Athlete URL": canonical_athlete_url(row.get("athlete_url")),
            "Athlete": clean_str(row.get("athlete_name")),
            "Suggested Gender": next(iter(genders)),
            "Confidence": "High",
            "Conflict": "No",
            "Sources": "Start list import",
            "Signal Count": len(g),
        })
    return apply_gender_updates(pd.DataFrame(suggestions), include_medium=False)

# ============================================================
# CSV normalizers
# ============================================================

# ============================================================
# Permissioned athlete-profile gender backfill
# ============================================================
def canonical_athlete_url(url: Any) -> Optional[str]:
    """Normalize athlete profile URLs so imports merge instead of duplicating.

    PTN URLs can arrive as /athletes/slug, /en/athletes/slug, http vs https,
    or with trailing slashes/query strings. The database should store one stable
    key: https://protrinews.com/athletes/<slug>.
    """
    s = clean_str(url)
    if not s:
        return None
    s = s.strip()
    s = re.sub(r"[?#].*$", "", s).rstrip("/")
    if s.startswith("//"):
        s = "https:" + s
    if s.startswith("/"):
        s = "https://protrinews.com" + s
    if s.startswith("http://"):
        s = "https://" + s[len("http://"):]

    m = re.search(r"https://(?:www\.)?protrinews\.com/(?:en/)?athletes/([^/?#]+)", s, flags=re.I)
    if m:
        slug = m.group(1).strip().strip("/").lower()
        if slug:
            return f"https://protrinews.com/athletes/{slug}"
    return s


def canonicalize_athlete_url_column(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with athlete_url normalized when that column exists."""
    if df is None or df.empty or "athlete_url" not in df.columns:
        return df
    out = df.copy()
    out["athlete_url"] = out["athlete_url"].map(canonical_athlete_url)
    return out


def athlete_profile_url_candidates(url: Any) -> List[str]:
    """Return a small set of allowed URL variants for the same PTN athlete.

    Some imported rows use /athletes/slug and some use /en/athletes/slug. The
    profile payload is not always identical, so the backfill checks both variants
    before declaring that no explicit gender field was found.
    """
    base = canonical_athlete_url(url)
    if not base:
        return []
    variants = []

    def add(u: str) -> None:
        u = clean_str(u).rstrip("/")
        if u and u not in variants:
            variants.append(u)

    add(base)
    add(re.sub(r"https://protrinews\.com/athletes/", "https://protrinews.com/en/athletes/", base))
    add(re.sub(r"https://protrinews\.com/en/athletes/", "https://protrinews.com/athletes/", base))
    return variants[:3]


def _html_to_visible_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text, flags=re.I)
    text = re.sub(r"&amp;", "&", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_profile_gender_value(value: Any) -> Optional[str]:
    raw = clean_str(value).lower()
    raw = raw.strip(' "\'`:,;{}[]()')
    if raw in {"male", "men", "man", "m", "masculino", "hommes"}:
        return "Men"
    if raw in {"female", "women", "woman", "w", "f", "feminino", "femmes"}:
        return "Women"
    return normalize_gender(value)


def extract_gender_from_profile_html(html: str) -> Tuple[Optional[str], str]:
    """Extract Men/Women competition category from profile HTML when present.

    This version is still conservative: it looks for explicit profile fields or
    unambiguous page text, never from the athlete's name, country, image, or a
    guessed first-name database.
    """
    if not html:
        return None, "empty_html"

    # Common JSON / app-state shapes, including escaped JSON inside Next payloads.
    json_patterns = [
        r'"(?:gender|sex|category|division|raceGender|competitionGender|genderName|gender_name)"\s*:\s*"([^"\\]{1,30})"',
        r'\\"(?:gender|sex|category|division|raceGender|competitionGender|genderName|gender_name)\\"\s*:\s*\\"([^"\\]{1,30})\\"',
        r'"(?:gender|sex|category|division)"\s*:\s*\{[^\}]{0,160}"(?:name|label|value)"\s*:\s*"([^"\\]{1,30})"',
        r'\\"(?:gender|sex|category|division)\\"\s*:\s*\{[^\}]{0,200}\\"(?:name|label|value)\\"\s*:\s*\\"([^"\\]{1,30})\\"',
    ]
    for pat in json_patterns:
        for m in re.finditer(pat, html, flags=re.I):
            g = _normalize_profile_gender_value(m.group(1))
            if g in ["Men", "Women"]:
                return g, "profile_json_field"

    text = _html_to_visible_text(html)
    if not text:
        return None, "empty_text"

    # Explicit label/value patterns in rendered text.
    label_patterns = [
        r"\b(?:Gender|Sex|Category|Division|Competition Category)\b\s*[:\-]?\s*(Male|Female|Men|Women|M|F)\b",
        r"\b(Male|Female|Men|Women)\b\s*[:\-]?\s*\b(?:Gender|Sex|Category|Division)\b",
        r"\b(?:Elite|Pro)\s+(Men|Women)\b",
        r"\b(Men|Women)\s+(?:Elite|Pro)\b",
    ]
    for pat in label_patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            for group in m.groups():
                g = _normalize_profile_gender_value(group)
                if g in ["Men", "Women"]:
                    return g, "profile_visible_label"

    # Fallback: if one gender word is uniquely present and the opposite is not,
    # treat it as medium-strength explicit page text. Avoid matching men inside women.
    women_hits = len(re.findall(r"\b(?:women|woman|female)\b", text, flags=re.I))
    men_hits = len(re.findall(r"\b(?:men|man|male)\b", text, flags=re.I))
    if women_hits > 0 and men_hits == 0:
        return "Women", "profile_unique_gender_word"
    if men_hits > 0 and women_hits == 0:
        return "Men", "profile_unique_gender_word"

    return None, "not_found"


def fetch_profile_gender(athlete_url: str, timeout: int = 15) -> Tuple[Optional[str], str, Optional[str]]:
    """Fetch one permissioned athlete profile URL and return gender + source + notes/error."""
    candidates = athlete_profile_url_candidates(athlete_url)
    if not candidates:
        return None, "bad_url", "Missing athlete URL"

    attempts = []
    for url in candidates:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": "TriathlonPicksGenderBackfill/1.1 (permissioned; missing-gender cleanup only)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            size = len(resp.text or "")
            if resp.status_code != 200:
                attempts.append(f"{url} -> HTTP {resp.status_code}")
                continue
            gender, source = extract_gender_from_profile_html(resp.text)
            if gender in ["Men", "Women"]:
                return gender, f"{source} ({url})", None
            attempts.append(f"{url} -> {source}, {size:,} chars")
        except Exception as e:
            attempts.append(f"{url} -> request_error: {e}")

    return None, "not_found", " | ".join(attempts[:4])


def missing_gender_athletes(athletes: pd.DataFrame, results: pd.DataFrame, starts: pd.DataFrame, limit: int = 200) -> pd.DataFrame:
    """Build a priority list of athletes whose gender is still unknown."""
    rows = []
    frames = []
    for df in [athletes, results, starts]:
        if df is not None and not df.empty:
            keep_cols = [c for c in ["athlete_url", "athlete_name", "gender", "race_date", "race_name"] if c in df.columns]
            frames.append(df[keep_cols].copy())
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "athlete_url" not in combined.columns:
        return pd.DataFrame()
    combined["athlete_url"] = combined["athlete_url"].map(canonical_athlete_url)
    combined["athlete_name"] = combined.get("athlete_name", pd.Series(dtype=object)).map(clean_str)
    combined["gender_norm"] = combined.get("gender", pd.Series(dtype=object)).map(normalize_gender)
    combined = combined[combined["athlete_url"].notna() | combined["athlete_name"].notna()].copy()

    # Group by URL when possible, otherwise name. Prefer rows with URL because profile lookup needs it.
    key = combined["athlete_url"].fillna(combined["athlete_name"])
    for athlete_key, g in combined.groupby(key):
        known = set(x for x in g["gender_norm"].dropna().unique() if x in ["Men", "Women"])
        if known:
            continue
        url = clean_str(g["athlete_url"].dropna().iloc[0]) if g["athlete_url"].notna().any() else None
        if not url:
            continue
        race_dates = pd.to_datetime(g.get("race_date"), errors="coerce") if "race_date" in g.columns else pd.Series(dtype="datetime64[ns]")
        rows.append({
            "Athlete": clean_str(g["athlete_name"].dropna().iloc[0]) if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": url,
            "Rows": len(g),
            "Last Race Date": format_date(race_dates.max()) if len(race_dates) and pd.notna(race_dates.max()) else "",
            "Last Race": clean_str(g["race_name"].dropna().iloc[0]) if "race_name" in g.columns and g["race_name"].notna().any() else "",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["Rows", "Last Race Date"], ascending=[False, False], na_position="last")
    return out.head(limit)


def apply_profile_gender_backfill(candidates: pd.DataFrame, batch_size: int = 25, delay_seconds: float = 0.75) -> pd.DataFrame:
    """Rate-limited, missing-only gender backfill from permissioned PTN profile pages."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    work = candidates.head(batch_size).copy()
    logs = []
    progress = st.progress(0, text="Checking athlete profile pages...")
    for i, (_, r) in enumerate(work.iterrows(), start=1):
        url = clean_str(r.get("Athlete URL"))
        name = clean_str(r.get("Athlete"))
        gender, source, error = fetch_profile_gender(url)
        updated = False
        if gender in ["Men", "Women"]:
            suggestions = pd.DataFrame([{
                "Athlete URL": url,
                "Athlete": name,
                "Suggested Gender": gender,
                "Confidence": "High",
                "Conflict": "No",
                "Sources": f"Permissioned athlete profile ({source})",
                "Signal Count": 1,
            }])
            apply_gender_updates(suggestions, include_medium=False)
            updated = True
        logs.append({
            "Athlete": name,
            "Athlete URL": url,
            "Detected Gender": gender or "",
            "Source": source,
            "Updated": "Yes" if updated else "No",
            "Error": error or "",
        })
        progress.progress(i / max(len(work), 1), text=f"Checked {i:,} of {len(work):,} profile pages...")
        if i < len(work) and delay_seconds > 0:
            time.sleep(delay_seconds)
    progress.empty()
    clear_cache()
    return pd.DataFrame(logs)

def normalize_athlete_results(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = []
    athletes = {}
    for _, r in df.iterrows():
        athlete_url = canonical_athlete_url(first_col(r, ["Athlete URL", "athlete_url", "Source URL", "Profile URL"]))
        athlete_name = clean_str(first_col(r, ["Athlete", "Athlete Name", "athlete_name", "Name"]))
        race_name = clean_str(first_col(r, ["Race", "Race Name", "race_name"]))
        race_url = clean_str(first_col(r, ["Race URL", "race_url"]))
        distance = clean_str(first_col(r, ["Distance", "distance"]))
        raw_type = clean_str(first_col(r, ["Type", "Race Type", "race_type"]))
        race_type = normalize_race_type(race_name, raw_type, distance)
        race_date = parse_date_value(first_col(r, ["Date", "Race Date", "race_date"]))
        gender = normalize_gender(first_col(r, ["Gender", "gender"]))
        status = parse_status(r)
        place = parse_place(first_col(r, ["Place", "Rank", "Finish Place", "place"]))

        if not athlete_name and not athlete_url and not race_name:
            continue

        swim = first_col(r, ["Swim", "Swim Split", "swim", "swim_seconds"])
        bike = first_col(r, ["Bike", "Bike Split", "bike", "bike_seconds"])
        run = first_col(r, ["Run", "Run Split", "run", "run_seconds"])

        rec = {
            "athlete_url": athlete_url or f"missing-url::{athlete_name or 'unknown'}",
            "athlete_name": athlete_name,
            "gender": gender,
            "race_date": race_date,
            "race_name": race_name,
            "race_url": race_url,
            "race_type": race_type,
            "distance": distance,
            "place": place,
            "sof": parse_number(first_col(r, SOF_ALIASES)),
            "ors": parse_number(first_col(r, ORS_ALIASES)),
            "swim_seconds": parse_split_seconds(swim, "swim", race_type),
            "bike_seconds": parse_split_seconds(bike, "bike", race_type),
            "run_seconds": parse_split_seconds(run, "run", race_type),
            "status": status,
            "raw": json_safe_row(r),
        }
        rows.append(rec)
        if athlete_url and athlete_name:
            athletes[athlete_url] = {"athlete_url": athlete_url, "athlete_name": athlete_name, "gender": gender}
    return rows, list(athletes.values())




def normalize_race_field_results(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Normalize full race-field CSV rows.

    This intentionally uses the same column mapping as Athlete Results, but
    stores rows in race_field_results so split rankings can use the real field
    without polluting the athlete-history table used for overall form.
    """
    return normalize_athlete_results(df)


def normalize_start_lists(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = []
    athletes = {}
    for _, r in df.iterrows():
        athlete_url = canonical_athlete_url(first_col(r, ["Athlete URL", "athlete_url", "Profile URL"]))
        athlete_name = clean_str(first_col(r, ["Athlete", "Athlete Name", "athlete_name", "Name"]))
        race_name = clean_str(first_col(r, ["Race", "Race Name", "race_name"]))
        race_date = parse_date_value(first_col(r, ["Race Date", "Date", "race_date"]))
        gender = normalize_gender(first_col(r, ["Gender", "gender"])) or "Men"
        if not athlete_name and not athlete_url:
            continue
        rec = {
            "race_name": race_name or "Unknown Race",
            "race_date": race_date,
            "gender": gender,
            "athlete_url": athlete_url,
            "athlete_name": athlete_name,
            "open_rank": parse_int(first_col(r, ["OpenRank", "Open Rank", "open_rank", "Rank"])),
        }
        rows.append(rec)
        if athlete_url and athlete_name:
            athletes[athlete_url] = {"athlete_url": athlete_url, "athlete_name": athlete_name, "gender": gender}
    return rows, list(athletes.values())


def normalize_race_overrides(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    for _, r in df.iterrows():
        rec = {
            "athlete_url": canonical_athlete_url(first_col(r, ["Athlete URL", "athlete_url", "Profile URL"])),
            "race_date": parse_date_value(first_col(r, ["Date", "Race Date", "race_date"])),
            "race_name": clean_str(first_col(r, ["Race", "Race Name", "race_name"])),
            "applies_to": clean_str(first_col(r, ["Applies To", "applies_to"])),
            "action": clean_str(first_col(r, ["Action", "action"])),
            "weight_multiplier": parse_number(first_col(r, ["Weight Multiplier", "weight_multiplier", "Multiplier"])),
            "reason": clean_str(first_col(r, ["Reason", "Notes", "reason"])),
        }
        if any(v is not None for v in rec.values()):
            rows.append(rec)
    return rows


def normalize_scoring_settings(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    for _, r in df.iterrows():
        group = clean_str(first_col(r, ["Group", "Setting Group", "setting_group", "Category"]))
        key = clean_str(first_col(r, ["Key", "Setting", "Setting Key", "setting_key", "Name"]))
        if not group or not key:
            continue
        value_raw = first_col(r, ["Value", "Setting Value", "setting_value"])
        value_num = parse_number(value_raw)
        rows.append({
            "setting_group": group,
            "setting_key": key,
            "setting_value": value_num,
            "setting_text": None if value_num is not None else clean_str(value_raw),
            "notes": clean_str(first_col(r, ["Notes", "notes", "Description"])),
        })
    return rows



def normalized_race_identity_name(value: Any) -> str:
    """Normalize race names enough to group the same race across athletes."""
    txt = clean_str(value) or ""
    txt = txt.lower()
    txt = re.sub(r"[—–-]\\s*(men|mens|women|womens|male|female)('s)?\\b", "", txt)
    txt = re.sub(r"\\b(men|mens|women|womens|male|female)('s)?\\b", "", txt)
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    txt = re.sub(r"\\s+", " ", txt).strip()
    return txt


def build_race_sof_fill_key(row: pd.Series, include_gender: bool = True) -> str:
    """Create a stable key for race-level SOF backfill.

    PTN sometimes stores SOF on some athletes' rows for the same race but leaves
    it blank on other athletes' rows. SOF is race-level evidence, not athlete-
    level evidence, so we should copy the canonical race SOF to the missing rows.
    """
    race_url = clean_str(row.get("race_url"))
    date_part = "" if pd.isna(row.get("race_date")) else str(pd.to_datetime(row.get("race_date")).date())
    gender_part = normalize_gender(row.get("gender")) if include_gender else None
    gender_part = gender_part or "unknown"
    if race_url:
        return "|".join(["url", race_url, gender_part])
    name_part = normalized_race_identity_name(row.get("race_name"))
    distance_part = clean_str(row.get("distance")) or ""
    type_part = clean_str(row.get("race_type")) or ""
    return "|".join(["name", name_part, date_part, distance_part, type_part, gender_part])


def fill_missing_sof_from_same_race(results: pd.DataFrame) -> pd.DataFrame:
    """Fill missing SOF from other athletes in the same race.

    This fixes cases such as one athlete's IRONMAN 70.3 Aix-en-Provence row
    having blank SOF while other athletes from the same race have SOF 81.5.
    It also records the source so the audit can show whether SOF was original
    or filled from the race-level canonical value.
    """
    if results.empty or "sof" not in results.columns:
        return results

    out = results.copy()
    out["sof_original"] = out["sof"]
    out["sof_source"] = np.where(out["sof"].notna(), "original", "missing")

    valid_sof = pd.to_numeric(out["sof"], errors="coerce")
    valid_mask = valid_sof.between(1, 100, inclusive="both")
    out.loc[~valid_mask, "sof"] = np.nan

    # First try same race + same known gender. This avoids using women's SOF as
    # a men's race SOF when both share similar naming.
    out["_sof_fill_key_gender"] = out.apply(lambda r: build_race_sof_fill_key(r, include_gender=True), axis=1)
    med_by_gender = out.loc[out["sof"].notna()].groupby("_sof_fill_key_gender")["sof"].median()
    missing = out["sof"].isna()
    if missing.any():
        fill_vals = out.loc[missing, "_sof_fill_key_gender"].map(med_by_gender)
        fill_mask = fill_vals.notna()
        idx = fill_vals[fill_mask].index
        out.loc[idx, "sof"] = fill_vals.loc[idx].astype(float)
        out.loc[idx, "sof_source"] = "filled_same_race_gender"

    # If gender is unknown on some rows, fallback to same race ignoring gender.
    out["_sof_fill_key_all"] = out.apply(lambda r: build_race_sof_fill_key(r, include_gender=False), axis=1)
    med_all = out.loc[out["sof"].notna()].groupby("_sof_fill_key_all")["sof"].median()
    missing = out["sof"].isna()
    if missing.any():
        fill_vals = out.loc[missing, "_sof_fill_key_all"].map(med_all)
        fill_mask = fill_vals.notna()
        idx = fill_vals[fill_mask].index
        out.loc[idx, "sof"] = fill_vals.loc[idx].astype(float)
        out.loc[idx, "sof_source"] = "filled_same_race"

    out = out.drop(columns=["_sof_fill_key_gender", "_sof_fill_key_all"], errors="ignore")
    return out

# ============================================================
# Scoring helpers
# ============================================================
@st.cache_data(ttl=900, show_spinner="Loading and cleaning Supabase data...")
def prepare_dataframes() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    athlete_results = load_table("athlete_results")
    race_field_results = load_table("race_field_results")
    starts = load_table("start_lists")
    athletes = load_table("athletes")
    overrides = load_table("race_overrides")

    athlete_results = canonicalize_athlete_url_column(athlete_results)
    race_field_results = canonicalize_athlete_url_column(race_field_results)
    starts = canonicalize_athlete_url_column(starts)
    athletes = canonicalize_athlete_url_column(athletes)
    overrides = canonicalize_athlete_url_column(overrides)

    if not athlete_results.empty:
        athlete_results["data_source"] = "athlete_results"
    if not race_field_results.empty:
        race_field_results["data_source"] = "race_field_results"

    # Split scoring wants both the start-list athlete histories and the full
    # race-field cache. Overall scoring is protected later by de-duplicating
    # identical athlete/race rows and by filtering to start-list athletes.
    if not race_field_results.empty:
        results = pd.concat([athlete_results, race_field_results], ignore_index=True, sort=False)
        if not results.empty:
            results["_source_priority"] = results["data_source"].map({"athlete_results": 0, "race_field_results": 1}).fillna(2)
            # Prefer the most complete duplicate row. Previously, an athlete_results
            # row with blank ORS could win over a race_field_results row from the
            # same athlete/race that actually had ORS/SOF/splits. That made some
            # current-year athletes look like they had races but no ORS.
            ors_num = pd.to_numeric(results.get("ors", pd.Series(index=results.index, dtype=object)), errors="coerce")
            sof_num = pd.to_numeric(results.get("sof", pd.Series(index=results.index, dtype=object)), errors="coerce")
            split_score = pd.Series(0, index=results.index, dtype="int64")
            for split_col in ["swim_seconds", "bike_seconds", "run_seconds"]:
                if split_col in results.columns:
                    split_score = split_score + pd.to_numeric(results[split_col], errors="coerce").notna().astype(int)
            results["_row_completeness"] = ors_num.notna().astype(int) * 4 + sof_num.notna().astype(int) * 2 + split_score
            dedupe_cols = [c for c in ["athlete_url", "athlete_name", "race_date", "race_name", "race_type"] if c in results.columns]
            if dedupe_cols:
                results = (
                    results.sort_values(["_row_completeness", "_source_priority"], ascending=[False, True])
                    .drop_duplicates(subset=dedupe_cols, keep="first")
                )
            results = results.drop(columns=["_source_priority", "_row_completeness"], errors="ignore")
    else:
        results = athlete_results

    for df in [results, starts, athletes, overrides]:
        if not df.empty:
            df.columns = [str(c) for c in df.columns]

    if not starts.empty:
        starts["gender"] = starts["gender"].map(normalize_gender)
        starts["race_date"] = pd.to_datetime(starts["race_date"], errors="coerce")

    gender_map: Dict[str, str] = {}
    name_gender_map: Dict[str, str] = {}
    for df in [athletes, starts]:
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            g = normalize_gender(r.get("gender"))
            if not g:
                continue
            u = canonical_athlete_url(r.get("athlete_url"))
            n = clean_str(r.get("athlete_name"))
            if u:
                gender_map[u] = g
            if n:
                name_gender_map[n.lower()] = g

    if not results.empty:
        results["race_date"] = pd.to_datetime(results["race_date"], errors="coerce")
        results["gender"] = results.apply(
            lambda r: normalize_gender(r.get("gender"))
            or gender_map.get(canonical_athlete_url(r.get("athlete_url")) or "")
            or name_gender_map.get((clean_str(r.get("athlete_name")) or "").lower()),
            axis=1,
        )
        results["race_type"] = results.apply(
            lambda r: normalize_race_type(r.get("race_name"), r.get("race_type"), r.get("distance")),
            axis=1,
        )
        for col in ["sof", "ors"]:
            if col in results.columns:
                results[col] = pd.to_numeric(results[col], errors="coerce")

        # Recover ORS/SOF from raw jsonb if older imports used slightly different
        # CSV headers. This fixes rows that have a race in the selected year but
        # appeared blank in Current Year ORS.
        if "ors" not in results.columns:
            results["ors"] = np.nan
        if "sof" not in results.columns:
            results["sof"] = np.nan
        if "raw" in results.columns:
            ors_missing = results["ors"].isna()
            if ors_missing.any():
                recovered_ors = results.loc[ors_missing].apply(lambda r: recover_number_from_raw(r, ORS_ALIASES), axis=1)
                results.loc[ors_missing, "ors"] = pd.to_numeric(recovered_ors, errors="coerce").to_numpy()
            sof_missing = results["sof"].isna()
            if sof_missing.any():
                recovered_sof = results.loc[sof_missing].apply(lambda r: recover_number_from_raw(r, SOF_ALIASES), axis=1)
                results.loc[sof_missing, "sof"] = pd.to_numeric(recovered_sof, errors="coerce").to_numpy()
        results["ors"] = pd.to_numeric(results["ors"], errors="coerce")
        results["sof"] = pd.to_numeric(results["sof"], errors="coerce")

        # SOF is race-level evidence. PTN/imported CSV rows can have SOF blank
        # for one athlete while other athletes from the exact same race have it.
        # Fill missing SOF from the canonical same-race value before scoring.
        results = fill_missing_sof_from_same_race(results)

        # Guarantee split columns exist and recover missing values from raw CSV payloads.
        # Force float dtype before assignment. Pandas 3.x raises if object/NA
        # recovered values are assigned into an integer-backed column.
        for disc in ["swim", "bike", "run"]:
            col = f"{disc}_seconds"
            if col not in results.columns:
                results[col] = np.nan

            results[col] = pd.to_numeric(results[col], errors="coerce").astype("float64")
            missing = results[col].isna()

            if missing.any() and "raw" in results.columns:
                recovered = results.loc[missing].apply(lambda r, d=disc: recover_split_from_raw(r, d), axis=1)
                recovered = pd.to_numeric(recovered, errors="coerce").astype("float64")
                # Assign plain numpy values to avoid dtype/index alignment issues.
                results.loc[missing, col] = recovered.to_numpy()

            results[col] = pd.to_numeric(results[col], errors="coerce").astype("float64")

        results["bad_status"] = results.apply(lambda r: is_bad_status(r.get("status"), r.get("place")), axis=1)
        results["place_num"] = results["place"].map(parse_place_number)

    if not overrides.empty:
        overrides["race_date"] = pd.to_datetime(overrides["race_date"], errors="coerce")

    return results, starts, athletes, overrides


def filter_results_to_startlist_races(
    results_window: pd.DataFrame,
    start_athletes: pd.DataFrame,
    discipline: str,
) -> pd.DataFrame:
    """Keep only race rows needed to score one start list discipline.

    The slow path was building split audits across every race in the 2-year
    window. For a selected start list, we only need the races where one of the
    selected athletes has a valid split, plus the other imported/full-field rows
    from those same races so rank and % behind fastest can be calculated.

    This usually cuts the audit source from tens of thousands of rows to a few
    hundred/thousand rows and makes race switching much faster.
    """
    if results_window.empty or start_athletes.empty:
        return results_window.head(0).copy()

    split_col = f"{discipline}_seconds"
    if split_col not in results_window.columns:
        return results_window.head(0).copy()

    start_urls = set(start_athletes.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).tolist())
    start_names = set(start_athletes.get("athlete_name", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())

    url_mask = results_window.get("athlete_url", pd.Series(index=results_window.index, dtype=object)).astype(str).isin(start_urls)
    name_mask = results_window.get("athlete_name", pd.Series(index=results_window.index, dtype=object)).fillna("").astype(str).str.lower().isin(start_names)
    split_mask = results_window[split_col].notna()

    athlete_rows = results_window[(url_mask | name_mask) & split_mask].copy()
    if athlete_rows.empty:
        return results_window.head(0).copy()

    athlete_race_keys = set(athlete_rows.apply(race_key, axis=1).dropna().astype(str).tolist())
    if not athlete_race_keys:
        return results_window.head(0).copy()

    out = results_window.copy()
    out["_selected_race_key"] = out.apply(race_key, axis=1).astype(str)
    out = out[out["_selected_race_key"].isin(athlete_race_keys)].copy()
    out = out.drop(columns=["_selected_race_key"], errors="ignore")
    return out


def match_override(row: pd.Series, overrides: pd.DataFrame, applies_to: str) -> Tuple[bool, float, str]:
    if overrides.empty:
        return False, 1.0, ""
    athlete_url = clean_str(row.get("athlete_url"))
    race_name = clean_str(row.get("race_name"))
    race_date = row.get("race_date")

    mult = 1.0
    reasons = []
    excluded = False
    for _, o in overrides.iterrows():
        o_ath = clean_str(o.get("athlete_url"))
        o_race = clean_str(o.get("race_name"))
        o_apply = (clean_str(o.get("applies_to")) or "All").lower()
        o_action = (clean_str(o.get("action")) or "").lower()
        if o_apply not in {"all", applies_to.lower(), "splits" if applies_to.lower() in {"swim", "bike", "run"} else applies_to.lower()}:
            continue
        if o_ath and athlete_url and o_ath != athlete_url:
            continue
        if o_race and race_name and o_race.lower() not in race_name.lower() and race_name.lower() not in o_race.lower():
            continue
        if pd.notna(o.get("race_date")) and pd.notna(race_date):
            if pd.to_datetime(o.get("race_date")).date() != pd.to_datetime(race_date).date():
                continue
        if "exclude" in o_action:
            excluded = True
        if "down" in o_action:
            m = safe_float(o.get("weight_multiplier"))
            if m is not None:
                mult *= m
        reason = clean_str(o.get("reason"))
        if reason:
            reasons.append(reason)
    return excluded, mult, "; ".join(reasons)


def race_key(row: pd.Series) -> str:
    u = clean_str(row.get("race_url"))
    if u:
        return u
    d = "" if pd.isna(row.get("race_date")) else str(pd.to_datetime(row.get("race_date")).date())
    return "|".join([clean_str(row.get("race_name")) or "", d, clean_str(row.get("race_type")) or ""])


def sof_cap(sof: Optional[float], race_type: str, discipline: str) -> float:
    rt = (race_type or "").lower()
    if sof is None or pd.isna(sof):
        if rt == "wtcs":
            return 95 if discipline == "swim" else 70 if discipline == "run" else 0
        if "world triathlon cup" in rt:
            return 65 if discipline == "swim" else 50 if discipline == "run" else 0
        if "continental" in rt:
            return 55 if discipline == "swim" else 45 if discipline == "run" else 0
        if rt in {"t100", "70.3", "challenge middle"}:
            return 80
        return 60
    if sof < 50:
        return 55
    if sof < 60:
        return 65
    if sof < 70:
        return 75
    if sof < 80:
        return 88
    return 100


def field_cap(field_size: int) -> float:
    # Until we import full race fields, do not hard-exclude every small sample.
    # A 2-4 athlete overlap is low confidence, so it gets a low cap, but it can
    # still show in Included rows and contribute modestly. A field of 1 is not
    # race-relative evidence and remains excluded.
    if field_size < 2:
        return 0
    if field_size <= 4:
        return 45
    if field_size <= 7:
        return 55
    if field_size <= 14:
        return 70
    if field_size <= 24:
        return 85
    return 100


def race_type_cap(race_type: str, discipline: str) -> float:
    rt = (race_type or "").lower()
    if rt in {"70.3", "challenge middle", "t100"}:
        return 100
    if rt == "full":
        # Full-distance races transfer very well for swim/bike strength.
        # The run is a different fatigue profile, so keep it lower for 70.3.
        return 95 if discipline == "swim" else 92 if discipline == "bike" else 85
    if rt == "wtcs":
        return 95 if discipline == "swim" else 70 if discipline == "run" else 0
    if "world triathlon cup" in rt:
        return 65 if discipline == "swim" else 50 if discipline == "run" else 0
    if "continental" in rt:
        return 55 if discipline == "swim" else 45 if discipline == "run" else 0
    if rt == "olympic":
        return 65 if discipline == "swim" else 55 if discipline == "run" else 0
    if rt == "sprint":
        return 50 if discipline == "swim" else 45 if discipline == "run" else 0
    return 65


def race_type_weight(race_type: str, discipline: str) -> float:
    rt = (race_type or "").lower()
    if rt in {"70.3", "challenge middle", "t100"}:
        return 1.0
    if rt == "full":
        # Full IM swim/bike are high-value non-draft evidence for 70.3.
        # Full IM run transfers less directly to 70.3 run speed.
        return 0.95 if discipline == "swim" else 0.90 if discipline == "bike" else 0.75
    if rt == "wtcs":
        return 0.90 if discipline == "swim" else 0.65 if discipline == "run" else 0.0
    if "world triathlon cup" in rt:
        return 0.60 if discipline == "swim" else 0.45 if discipline == "run" else 0.0
    if "continental" in rt:
        return 0.45 if discipline == "swim" else 0.35 if discipline == "run" else 0.0
    if rt == "olympic":
        return 0.55 if discipline == "swim" else 0.45 if discipline == "run" else 0.0
    if rt == "sprint":
        return 0.40 if discipline == "swim" else 0.30 if discipline == "run" else 0.0
    return 0.55


def recency_weight(race_date: Any, target_date: pd.Timestamp) -> float:
    if pd.isna(race_date) or pd.isna(target_date):
        return 0.8
    days = max(0, (target_date - pd.to_datetime(race_date)).days)
    if days <= 120:
        return 1.25
    if days <= 365:
        return 1.1
    if days <= 730:
        return 0.9
    return 0.65


def is_premium_split_evidence(row: pd.Series, discipline: str, strong_sof_threshold: float = 70.0) -> bool:
    """Return whether this row is true top-tier evidence for a 70.3 split pick.

    This is deliberately stricter than strong evidence. The top of the split
    board should be driven by races that actually prove the athlete can split
    well against championship/T100/high-SOF fields, not just normal 70.3 races
    where our imported sample happens to show them 1st-3rd.
    """
    rt = (clean_str(row.get("race_type")) or "").lower()
    race_name = (clean_str(row.get("race_name")) or "").lower()
    sof = safe_float(row.get("sof"))

    championship_name = any(k in race_name for k in [
        "world championship",
        "world championships",
        "70.3 world",
        "ironman world championship",
        "olympic games",
    ])

    if rt == "t100" or "t100" in race_name or "pto" in race_name:
        return True

    if championship_name:
        # Championship swims are very predictive; championship bikes are also
        # useful when non-draft. Championship runs are useful but less of an
        # automatic 70.3-fastest-run signal.
        return discipline in {"swim", "bike"}

    if discipline == "swim" and rt == "wtcs":
        return True

    if rt == "full":
        if discipline in {"swim", "bike"}:
            return sof is not None and sof >= 80
        if discipline == "run":
            split_rank = safe_float(row.get("split_rank"))
            pct = safe_float(row.get("pct_behind_fastest"))
            return sof is not None and sof >= 85 and ((split_rank is not None and split_rank <= 3) or (pct is not None and pct <= 1.5))

    # Very high SOF normal 70.3/Challenge races are strong evidence,
    # not premium. Premium is reserved for T100/PTO, World Championship,
    # true WTCS swim, Olympic Games swim, and high-SOF full IM swim/bike.
    # This prevents normal-race wins from jumping above athletes with
    # repeated T100 / World Championship proof.
    return False


def is_strong_split_evidence(row: pd.Series, discipline: str, strong_sof_threshold: float = 70.0) -> bool:
    """Return whether this split row is usable strong evidence.

    Strong evidence can support the rating, but premium evidence is what should
    drive the very top of the rankings. Normal high-SOF 70.3 races are strong;
    T100/World Championship/very-high-SOF races are premium.
    """
    rt = (clean_str(row.get("race_type")) or "").lower()
    sof = safe_float(row.get("sof"))

    if is_premium_split_evidence(row, discipline, strong_sof_threshold):
        return True

    if rt == "full":
        if discipline in {"swim", "bike"}:
            return sof is not None and sof >= strong_sof_threshold
        if discipline == "run":
            split_rank = safe_float(row.get("split_rank"))
            pct = safe_float(row.get("pct_behind_fastest"))
            return sof is not None and sof >= 80 and ((split_rank is not None and split_rank <= 5) or (pct is not None and pct <= 2.5))

    if rt in {"70.3", "challenge middle"}:
        return sof is not None and sof >= max(strong_sof_threshold, 72)

    # WTCS run is useful, but not premium for a 70.3 half-marathon.
    if rt == "wtcs" and discipline == "run":
        return sof is not None and sof >= 75

    if sof is not None and sof >= max(strong_sof_threshold, 75):
        return True

    return False


def evidence_quality_label(row: pd.Series, discipline: str, strong_sof_threshold: float = 70.0) -> str:
    rt = (clean_str(row.get("race_type")) or "").lower()
    sof = safe_float(row.get("sof"))
    if is_premium_split_evidence(row, discipline, strong_sof_threshold):
        return "Premium"
    if is_strong_split_evidence(row, discipline, strong_sof_threshold):
        return "Strong"
    if rt == "full" and discipline == "run":
        return "Medium" if sof is not None and sof >= 70 else "Low/unknown"
    if sof is not None and sof >= 60:
        return "Medium"
    if rt in {"world triathlon cup", "continental cup", "sprint", "olympic"}:
        return "Development/short-course"
    return "Low/unknown"

def closeness_score(pct_behind: float, discipline: str) -> float:
    # Percent behind fastest is the core. A 1-min swim gap means very different things at 6 min vs 24 min.
    if pct_behind <= 0:
        return 100
    penalty = {"swim": 13.0, "bike": 9.0, "run": 10.5}.get(discipline, 10.0)
    return clamp(100 - pct_behind * penalty, 0, 100)


def rank_score(rank: int, field_size: int) -> float:
    if rank <= 1:
        return 100
    if rank == 2:
        return 90
    if rank == 3:
        return 82
    if rank <= 5:
        return 68
    if field_size <= 0:
        return 0
    percentile = 1 - ((rank - 1) / max(1, field_size - 1))
    return clamp(percentile * 75, 0, 75)


def dominance_score(gap_to_second_pct: Optional[float], discipline: str) -> float:
    if gap_to_second_pct is None or pd.isna(gap_to_second_pct) or gap_to_second_pct <= 0:
        return 0
    cap_gap = {"swim": 4.0, "bike": 3.0, "run": 5.0}.get(discipline, 4.0)
    return clamp((gap_to_second_pct / cap_gap) * 100, 0, 100)


def build_split_audit(
    results: pd.DataFrame,
    start_athletes: pd.DataFrame,
    overrides: pd.DataFrame,
    target_date: pd.Timestamp,
    gender: str,
    discipline: str,
    min_field_size: int,
) -> pd.DataFrame:
    """Build split audit rows.

    Important: this table is a scoring audit, not a full career-result list.
    It now keeps DNF/DNS/DSQ rows in the audit as excluded rows instead of
    silently dropping them, so the user can see why a recent result was not used.
    Rows with no valid split for the selected discipline still cannot be ranked,
    so use the raw career diagnostic in the Split Audit page to inspect those.
    """
    split_col = f"{discipline}_seconds"
    if results.empty or split_col not in results.columns:
        return pd.DataFrame()

    start_urls = set(start_athletes["athlete_url"].dropna().astype(str).tolist()) if "athlete_url" in start_athletes else set()
    df = results.copy()
    df = df[(df["race_date"].notna()) & (df["race_date"] <= target_date)]

    # Keep rows with a parsed split even if they are DNF/DNS/DSQ. They will be
    # marked excluded below. Previously we filtered them out before the audit,
    # which made it look like recent races were missing.
    df = df[df[split_col].notna()]

    gender_known_match = df["gender"].eq(gender)
    gender_unknown_ok = df["gender"].isna() & df["race_name"].map(lambda x: race_gender_compatible(x, gender))
    start_list_match = df["athlete_url"].isin(start_urls)
    df = df[gender_known_match | gender_unknown_ok | start_list_match]

    # Draft-legal bike rows should be visible in the audit, but excluded from scoring.
    draft_bike_mask = pd.Series(False, index=df.index)
    if discipline == "bike":
        draft_bike_mask = df["race_type"].fillna("").str.lower().str.contains("wtcs|world triathlon|continental|draft")
    df["draft_bike_excluded"] = draft_bike_mask
    df["split_status_excluded"] = df.apply(lambda r: is_excluded_for_split_status(r.get("status"), r.get("place"), discipline), axis=1)

    if df.empty:
        return pd.DataFrame()

    df["race_key"] = df.apply(race_key, axis=1)
    audit_rows = []

    for _, g in df.groupby("race_key"):
        g = g.copy()
        # Rank and fastest calculations use only rows that are eligible for scoring.
        # Bad-status rows and draft-legal bike rows remain visible, but they do not
        # create/alter the race-relative split ranking.
        scoring_g = g[(~g.get("split_status_excluded", False).astype(bool)) & (~g["draft_bike_excluded"].astype(bool))].copy()
        scoring_g = scoring_g.sort_values(split_col, ascending=True)

        fastest = safe_float(scoring_g[split_col].min()) if not scoring_g.empty else None
        field_size = len(scoring_g)
        sorted_splits = scoring_g[split_col].dropna().sort_values().tolist() if not scoring_g.empty else []
        second = sorted_splits[1] if len(sorted_splits) > 1 else None
        rank_map = {row_idx: rank for rank, row_idx in enumerate(scoring_g.index.tolist(), start=1)}

        for row_idx, r in g.iterrows():
            split_sec = safe_float(r.get(split_col))
            if split_sec is None:
                continue

            rt = clean_str(r.get("race_type")) or "Unknown"
            bad_status = bool(r.get("bad_status", False))
            split_status_excluded = bool(r.get("split_status_excluded", False))
            draft_bike = bool(r.get("draft_bike_excluded", False))
            excluded_override, override_mult, override_reason = match_override(r, overrides, discipline)

            idx = rank_map.get(row_idx)
            pct_behind = None
            gap_second = None
            rs = 0
            cs = 0
            ds = 0
            raw_score = 0
            s_cap = sof_cap(r.get("sof"), rt, discipline)
            f_cap = field_cap(field_size)
            t_cap = race_type_cap(rt, discipline)
            final_cap = min(s_cap, f_cap, t_cap)
            final_score = 0
            ew = 0
            included = False

            if idx is not None and fastest is not None and fastest > 0:
                pct_behind = ((split_sec - fastest) / fastest) * 100
                if idx == 1 and second:
                    gap_second = ((second - fastest) / fastest) * 100
                rs = rank_score(idx, field_size)
                cs = closeness_score(pct_behind, discipline)
                ds = dominance_score(gap_second, discipline)
                raw_score = 0.70 * cs + 0.20 * rs + 0.10 * ds
                included = field_size >= 2 and final_cap > 0
                if excluded_override:
                    included = False
                final_score = min(raw_score, final_cap)
                ew = race_type_weight(rt, discipline) * recency_weight(r.get("race_date"), target_date) * override_mult
                if field_size < 15:
                    ew *= 0.75
                sof_val = safe_float(r.get("sof"))
                if sof_val is not None and sof_val >= 80:
                    ew *= 1.15
                elif sof_val is not None and sof_val < 60:
                    ew *= 0.75
                elif sof_val is None:
                    ew *= 0.65

            reason = []
            if split_status_excluded:
                reason.append("status excluded for this split")
            elif bad_status:
                reason.append("DNF row allowed for completed split")
            if draft_bike:
                reason.append("draft-legal bike excluded")
            if field_size < 1:
                reason.append("no scoring field")
            elif field_size < 2:
                reason.append("field<2")
            elif field_size < min_field_size:
                reason.append(f"low sample field<{min_field_size}")
            if final_cap <= 0:
                reason.append("race type excluded")
            if excluded_override:
                reason.append("override excluded")
            if override_reason:
                reason.append(override_reason)
            if not reason:
                reason.append("included")

            audit_rows.append({
                "athlete_url": r.get("athlete_url"),
                "athlete_name": r.get("athlete_name"),
                "discipline": discipline,
                "race_date": r.get("race_date"),
                "race_name": r.get("race_name"),
                "race_type": rt,
                "gender": r.get("gender"),
                "place": r.get("place"),
                "status": r.get("status"),
                "bad_status": bad_status,
                "split_status_excluded": split_status_excluded,
                "sof": safe_float(r.get("sof")),
                "sof_source": r.get("sof_source"),
                "sof_original": safe_float(r.get("sof_original")),
                "field_size": field_size,
                "sample_size": field_size,
                "field_source": "imported_sample",
                "coverage_note": "Imported sample only; not full ProTriNews field",
                "quality_tier": evidence_quality_label(pd.Series(r), discipline, 70.0),
                "premium_evidence": bool(
                    is_premium_split_evidence(pd.Series(r), discipline, 70.0)
                    and not split_status_excluded
                    and not draft_bike
                    and field_size >= 2
                ),
                "strong_evidence": bool(
                    is_strong_split_evidence(pd.Series(r), discipline, 70.0)
                    and not split_status_excluded
                    and not draft_bike
                    and field_size >= 2
                ),
                "split_seconds": int(split_sec),
                "split": format_seconds(split_sec),
                "split_rank": idx,
                "rank_display": f"{idx}/{field_size}" if idx else "—",
                "sample_rank_display": f"{idx}/{field_size}" if idx else "—",
                "pct_behind_fastest": pct_behind,
                "gap_when_fastest_pct": gap_second,
                "closeness_score": cs,
                "rank_score": rs,
                "dominance_score": ds,
                "raw_score": raw_score,
                "sof_cap": s_cap,
                "field_cap": f_cap,
                "race_type_cap": t_cap,
                "final_cap": final_cap,
                "evidence_score": final_score,
                "evidence_weight": ew,
                "included": bool(included and not split_status_excluded and not draft_bike),
                "reason": "; ".join(reason),
            })

    return pd.DataFrame(audit_rows)

def score_splits_for_start_list(
    audit: pd.DataFrame,
    start_athletes: pd.DataFrame,
    target_date: pd.Timestamp,
    top_n: int,
    strong_sof_threshold: float,
) -> pd.DataFrame:
    if audit.empty:
        return pd.DataFrame()
    start_urls = set(start_athletes["athlete_url"].dropna().astype(str).tolist())
    start_names = set(start_athletes["athlete_name"].dropna().astype(str).str.lower().tolist())
    df = audit.copy()
    df = df[df["included"]]
    df = df[(df["athlete_url"].isin(start_urls)) | (df["athlete_name"].fillna("").str.lower().isin(start_names))]
    if df.empty:
        return pd.DataFrame()

    discipline = clean_str(df["discipline"].dropna().iloc[0]) if "discipline" in df.columns and df["discipline"].notna().any() else "swim"

    # Recompute quality flags using the current sidebar threshold. Premium =
    # T100 / championship / very-high-SOF / elite-relevant evidence. Strong =
    # useful evidence. The final score is anchored to premium first so normal
    # low/medium-field wins cannot outrank athletes who repeatedly prove it in
    # T100 / World Championship / very high SOF races.
    df["premium_evidence"] = df.apply(lambda r: is_premium_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["strong_evidence"] = df.apply(lambda r: is_strong_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["quality_tier"] = df.apply(lambda r: evidence_quality_label(r, discipline, strong_sof_threshold), axis=1)

    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        g = g.sort_values("race_date", ascending=False).copy()
        recent = g.head(top_n).copy()
        recent_scored = recent

        if recent_scored.empty:
            continue

        scores = recent_scored["evidence_score"].astype(float).tolist()
        weights = recent_scored["evidence_weight"].astype(float).tolist()
        recent_score = weighted_avg(scores, weights) or 0

        premium = recent_scored[recent_scored["premium_evidence"].astype(bool)].copy()
        strong = recent_scored[recent_scored["strong_evidence"].astype(bool)].copy()
        medium_or_better = recent_scored[recent_scored["quality_tier"].isin(["Premium", "Strong", "Medium"])].copy()

        premium_score = weighted_avg(premium["evidence_score"].astype(float).tolist(), premium["evidence_weight"].astype(float).tolist()) if not premium.empty else 0
        premium_weights = premium["evidence_weight"].astype(float).tolist() if not premium.empty else []
        premium_top3_rate = weighted_avg((premium["split_rank"] <= 3).astype(float).tolist(), premium_weights) if not premium.empty else 0
        premium_fastest_rate = weighted_avg((premium["split_rank"] == 1).astype(float).tolist(), premium_weights) if not premium.empty else 0
        premium_avg_behind = weighted_avg(premium["pct_behind_fastest"].astype(float).tolist(), premium_weights) if not premium.empty else None
        premium_count = len(premium)

        strong_score = weighted_avg(strong["evidence_score"].astype(float).tolist(), strong["evidence_weight"].astype(float).tolist()) if not strong.empty else 0
        strong_weights = strong["evidence_weight"].astype(float).tolist() if not strong.empty else []
        strong_top3_rate = weighted_avg((strong["split_rank"] <= 3).astype(float).tolist(), strong_weights) if not strong.empty else 0
        strong_fastest_rate = weighted_avg((strong["split_rank"] == 1).astype(float).tolist(), strong_weights) if not strong.empty else 0
        strong_avg_behind = weighted_avg(strong["pct_behind_fastest"].astype(float).tolist(), strong_weights) if not strong.empty else None
        strong_count = len(strong)

        all_top3_rate = weighted_avg((recent_scored["split_rank"] <= 3).astype(float).tolist(), weights) or 0
        all_fastest_rate = weighted_avg((recent_scored["split_rank"] == 1).astype(float).tolist(), weights) or 0
        avg_behind = weighted_avg(recent_scored["pct_behind_fastest"].astype(float).tolist(), weights)
        evidence_count = len(recent_scored)
        count_score = min(100, evidence_count / 5 * 100)

        if premium_count > 0:
            final = (
                0.70 * premium_score
                + 0.12 * strong_score
                + 0.08 * recent_score
                + 0.06 * (premium_top3_rate or 0) * 100
                + 0.04 * count_score
            )
        elif strong_count > 0:
            # Strong but not premium: can rank well, but should not outrank
            # repeated T100/World/very-high-SOF proof unless the strong rows are
            # exceptional and numerous.
            final = (
                0.55 * strong_score
                + 0.20 * recent_score
                + 0.12 * (strong_top3_rate or 0) * 100
                + 0.05 * (strong_fastest_rate or 0) * 100
                + 0.08 * count_score
            )
        else:
            # No strong rows: useful but capped. Low-SOF/development wins belong
            # here unless the athlete also has premium/strong proof.
            final = (
                0.45 * recent_score
                + 0.18 * all_top3_rate * 100
                + 0.07 * all_fastest_rate * 100
                + 0.05 * count_score
            )

        # Premium/strong-field closeness gates. Being close in a premium race
        # matters more than winning a normal/weak race. Repeatedly being far back
        # in premium/strong races should cap the athlete.
        gate_behind = premium_avg_behind if premium_avg_behind is not None else strong_avg_behind
        if gate_behind is not None:
            if gate_behind > 6:
                final = min(final, 55)
            elif gate_behind > 4:
                final = min(final, 68)
            elif gate_behind > 2.5:
                final = min(final, 78)
        elif avg_behind is not None:
            if avg_behind > 8:
                final = min(final, 45)
            elif avg_behind > 5:
                final = min(final, 58)
            elif avg_behind > 3.5:
                final = min(final, 68)

        # If no recent top-5 and not close by percentage, cap hard.
        if len(recent_scored) and not (recent_scored["split_rank"] <= 5).any() and (avg_behind is None or avg_behind > 2.5):
            final = min(final, 50)

        # Run-specific consistency gates. A single good run should not outrank
        # an athlete with repeated elite 70.3/T100/full-IM run proof if the rest
        # of the recent run profile is mediocre. Full IM runs can be strong when
        # they are top-3/top-5 in a high-SOF field, but the recent average gap
        # still matters more for run than for swim/bike.
        if discipline == "run":
            close_strong = recent_scored[
                recent_scored["strong_evidence"].astype(bool)
                & (
                    (recent_scored["pct_behind_fastest"].astype(float) <= 2.5)
                    | (recent_scored["split_rank"].astype(float) <= 3)
                )
            ]
            close_strong_count = len(close_strong)
            if avg_behind is not None:
                if avg_behind > 7:
                    final = min(final, 45)
                elif avg_behind > 5:
                    final = min(final, 55)
                elif avg_behind > 3.5:
                    final = min(final, 65)
            if close_strong_count == 0:
                final = min(final, 50)
            elif close_strong_count == 1 and evidence_count >= 4 and avg_behind is not None and avg_behind > 3:
                final = min(final, 60)

        # Quality confidence caps. This is the main fix for "three nobodies ahead
        # of Jamie". A normal high-SOF 70.3 win can support a profile, but the
        # very top should require premium proof unless the athlete has multiple
        # strong rows with excellent closeness.
        if premium_count == 0:
            if strong_count == 0:
                cap = 50 if len(medium_or_better) >= 3 else 45
                final = min(final, cap)
                confidence = "Low - no strong-field proof"
            elif strong_count == 1:
                final = min(final, 55)
                confidence = "Medium - 1 strong row, no premium"
            elif strong_count == 2:
                final = min(final, 60)
                confidence = "Medium - strong rows, no premium"
            else:
                final = min(final, 63)
                confidence = "Good - repeated strong rows, no premium"
        elif premium_count == 1:
            final = min(final, 72)
            confidence = "Good - 1 premium row"
        elif premium_count == 2:
            confidence = "High - 2 premium rows"
        else:
            confidence = "Elite - repeated premium proof"

        # Evidence-count confidence caps. A single validated split should not
        # rank beside athletes with several recent validated splits.
        if evidence_count <= 1:
            final = min(final, 45)
            confidence = "Low - 1 split"
        elif evidence_count == 2:
            final = min(final, 60)
            if premium_count < 2:
                confidence = "Low - 2 splits"
        elif evidence_count == 3 and premium_count == 0 and strong_count == 0:
            final = min(final, 56)
            confidence = "Low - 3 weak/medium splits"

        best_row = recent_scored.sort_values(["evidence_score", "race_date"], ascending=[False, False]).head(1)
        last_row = recent.head(1)
        rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None,
            "Score": round(final, 1),
            "Confidence": confidence,
            "Premium Evidence Count": premium_count,
            "Strong Evidence Count": strong_count,
            "Evidence Count": evidence_count,
            "Premium Field Score": round(premium_score, 1),
            "Strong Field Score": round(strong_score, 1),
            "Recent Score": round(recent_score, 1),
            "Premium Avg Behind %": None if premium_avg_behind is None else round(premium_avg_behind, 2),
            "Strong Avg Behind %": None if strong_avg_behind is None else round(strong_avg_behind, 2),
            "Recent Avg Behind %": None if avg_behind is None else round(avg_behind, 2),
            "Premium Top 3 %": round((premium_top3_rate or 0) * 100, 1),
            "Premium Fastest %": round((premium_fastest_rate or 0) * 100, 1),
            "Strong Top 3 %": round((strong_top3_rate or 0) * 100, 1),
            "Strong Fastest %": round((strong_fastest_rate or 0) * 100, 1),
            "Recent Top 3 %": round(all_top3_rate * 100, 1),
            "Recent Fastest %": round(all_fastest_rate * 100, 1),
            "Last Race": clean_str(last_row["race_name"].iloc[0]) if not last_row.empty else "",
            "Last Race Date": format_date(last_row["race_date"].iloc[0]) if not last_row.empty else "",
            "Last Rank": clean_str(last_row["rank_display"].iloc[0]) if not last_row.empty else "",
            "Best Recent Split": clean_str(best_row["split"].iloc[0]) if not best_row.empty else "",
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out
def score_overall(
    results: pd.DataFrame,
    start_athletes: pd.DataFrame,
    overrides: pd.DataFrame,
    target_date: pd.Timestamp,
    target_year: int,
    top_n: int,
) -> pd.DataFrame:
    if results.empty or start_athletes.empty:
        return pd.DataFrame()
    start_urls = set(start_athletes["athlete_url"].dropna().astype(str).tolist())
    start_names = set(start_athletes["athlete_name"].dropna().astype(str).str.lower().tolist())
    df = results.copy()
    df = df[(df["race_date"].notna()) & (df["race_date"] <= target_date) & (~df["bad_status"])]
    df = df[(df["athlete_url"].isin(start_urls)) | (df["athlete_name"].fillna("").str.lower().isin(start_names))]
    df = df[df["ors"].notna()]
    if df.empty:
        return pd.DataFrame()

    start_lookup, name_start_lookup = start_lookup_maps(start_athletes)
    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        g = g.sort_values("race_date", ascending=False).copy()
        scored_rows = []
        for _, r in g.iterrows():
            excluded, mult, reason = match_override(r, overrides, "Overall")
            if excluded:
                continue
            rr = r.copy()
            rr["overall_weight"] = recency_weight(r.get("race_date"), target_date) * mult
            rr["override_reason"] = reason
            scored_rows.append(rr)
        if not scored_rows:
            continue
        gg = pd.DataFrame(scored_rows).sort_values("race_date", ascending=False)
        recent = gg.head(top_n).copy()
        recent_scored = recent
        current_year = gg[gg["race_date"].dt.year == target_year]
        strong = recent_scored[(recent_scored["sof"].fillna(0) >= 70) | (recent_scored["race_type"].isin(["T100", "WTCS"]))]
        championship_score = 0.0
        if not recent_scored.empty:
            champ_scores = recent_scored.apply(championship_result_score, axis=1)
            championship_score = safe_float(champ_scores.max()) or 0.0

        weights = recent_scored["overall_weight"].astype(float).tolist()
        recent_score = weighted_avg(recent_scored["ors"].astype(float).tolist(), weights) or 0
        current_year_score = weighted_avg(current_year["ors"].astype(float).tolist(), current_year["overall_weight"].astype(float).tolist()) if not current_year.empty else recent_score
        best_recent = safe_float(recent_scored["ors"].max()) or 0
        strong_score = weighted_avg(strong["ors"].astype(float).tolist(), strong["overall_weight"].astype(float).tolist()) if not strong.empty else 0
        name = g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else str(athlete_key)
        url = g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None
        start_row = start_lookup.get(url) if url else name_start_lookup.get(name.lower())
        open_rank = parse_int(start_row.get("open_rank")) if isinstance(start_row, dict) else None
        open_rank_score = 0
        if open_rank:
            open_rank_score = clamp(105 - open_rank * 3.5, 0, 100)

        final = (
            0.38 * recent_score
            + 0.20 * current_year_score
            + 0.16 * best_recent
            + 0.14 * strong_score
            + 0.08 * championship_score
            + 0.04 * open_rank_score
        )
        rows.append({
            "Athlete": name,
            "Athlete URL": url,
            "Score": round(final, 1),
            "Recent Form ORS": round(recent_score, 1),
            "Current Year ORS": round(current_year_score, 1) if current_year_score is not None else None,
            "Best Recent ORS": round(best_recent, 1),
            "Strong Field ORS": round(strong_score, 1),
            "Championship Score": round(championship_score, 1),
            "Recent Races Used": len(recent_scored),
            "OpenRank": open_rank,
            "Last Race": clean_str(recent.iloc[0].get("race_name")) if len(recent) else "",
            "Last Race Date": format_date(recent.iloc[0].get("race_date")) if len(recent) else "",
        })
    out = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out



# ============================================================
# OpenRank-aligned scoring overrides
# ============================================================
def openrank_tier_for_row(row: pd.Series, discipline: Optional[str] = None) -> str:
    """Map our imported race row to the OpenRank-style tier model.

    This mirrors the public OpenRank idea: race quality is not just branding;
    championship status, race family, and SOF determine how much a result can
    move a ranking. The exact PTN tier labels are not always present in our CSV,
    so this is a deterministic local approximation.
    """
    race = (clean_str(row.get("race_name")) or "").lower()
    rt = (clean_str(row.get("race_type")) or "").lower()
    sof = safe_float(row.get("sof"))

    if "ironman world championship" in race and "70.3" not in race:
        return "Diamond"
    if any(x in race for x in ["70.3 world championship", "world championship", "championship final", "olympic games"]):
        return "Platinum"
    if rt == "t100" or "t100" in race or "pto" in race:
        return "Gold"
    if sof is not None and sof >= 85:
        return "Gold"
    if rt == "wtcs":
        # WTCS is elite for swim/run short-course predictions, but bike is excluded elsewhere.
        return "Gold" if discipline in {"swim", "run", None} else "Bronze"
    if rt in {"70.3", "challenge middle", "full"}:
        if sof is not None and sof >= 75:
            return "Silver"
        return "Bronze"
    if "world triathlon cup" in rt or "world triathlon cup" in race:
        return "Silver" if discipline == "swim" else "Bronze"
    if "continental" in rt or "continental" in race:
        return "Bronze"
    if rt in {"olympic", "sprint"}:
        return "Bronze"
    if sof is not None and sof >= 75:
        return "Silver"
    return "Bronze"


def openrank_tier_params(tier: str) -> Tuple[float, float]:
    t = (tier or "Bronze").title()
    params = {
        "Diamond": (100.0, 0.02),
        "Platinum": (95.0, 0.02),
        "Gold": (90.0, 0.05),
        "Silver": (80.0, 0.08),
        "Bronze": (70.0, 0.11),
    }
    return params.get(t, params["Bronze"])


def openrank_position_score(rank: Any, tier: str) -> float:
    r = parse_int(rank)
    if not r or r < 1:
        return 0.0
    base, drop = openrank_tier_params(tier)
    return float(base * ((1.0 - drop) ** (r - 1)))


def openrank_baseline_count(field_size: int) -> int:
    """OpenRank-style baseline group size by field/sample size."""
    n = int(field_size or 0)
    if n <= 0:
        return 0
    if n <= 4:
        return 1
    if n <= 8:
        return 2
    if n <= 12:
        return 3
    if n <= 16:
        return 4
    return 5


def openrank_sof_score(row: pd.Series, tier: str) -> float:
    """Use race SOF when available; otherwise use conservative tier seed."""
    sof = safe_float(row.get("sof"))
    if sof is not None:
        return clamp(sof, 0, 100)
    seeds = {
        "Diamond": 90.0,
        "Platinum": 85.0,
        "Gold": 75.0,
        "Silver": 60.0,
        "Bronze": 45.0,
    }
    return seeds.get((tier or "Bronze").title(), 45.0)


def openrank_time_score(split_seconds: Any, baseline_split_seconds: Any, tier: str, sof_score: float) -> float:
    """OpenRank-style split-time score.

    PTN OpenRank uses a race baseline score and then deducts/adds 6 points per
    1 percentage point slower/faster than baseline. We apply the same concept
    to swim/bike/run split times inside that same race/sample.
    """
    split = safe_float(split_seconds)
    baseline = safe_float(baseline_split_seconds)
    if split is None or baseline is None or baseline <= 0:
        return 0.0
    base, _ = openrank_tier_params(tier)
    baseline_score = (base + (safe_float(sof_score) or 0.0)) / 2.0
    pct_slower = ((split - baseline) / baseline) * 100.0
    return clamp(baseline_score - (pct_slower * 6.0), 0, 120)


def add_split_openrank_scores(audit: pd.DataFrame) -> pd.DataFrame:
    """Add OpenRank-like split score columns to the audit table.

    Split score = 35% position + 35% SOF + 30% split-time quality.
    Athlete ranking then uses best 4 split scores in a rolling 52-week window,
    padding missing scores with zero exactly like OpenRank's best-4 model.
    """
    if audit is None or audit.empty:
        return pd.DataFrame() if audit is None else audit
    out = audit.copy()

    # Pandas/Arrow can infer an all-empty column as float64.  The tier column
    # later receives text values such as Gold/Silver/Bronze, so force it to an
    # object/string-safe dtype before row assignment.
    if "openrank_tier" not in out.columns:
        out["openrank_tier"] = ""
    else:
        out["openrank_tier"] = out["openrank_tier"].fillna("").astype("object")

    for c in [
        "openrank_position_score", "openrank_sof_score",
        "openrank_time_score", "split_openrank_score", "baseline_split"
    ]:
        if c not in out.columns:
            out[c] = np.nan
        else:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "race_key_calc" not in out.columns:
        out["race_key_calc"] = (
            out.get("race_name", pd.Series("", index=out.index)).fillna("").astype(str)
            + "|" + out.get("race_date", pd.Series("", index=out.index)).astype(str)
            + "|" + out.get("race_type", pd.Series("", index=out.index)).fillna("").astype(str)
        )
    discipline = clean_str(out["discipline"].dropna().iloc[0]) if "discipline" in out.columns and out["discipline"].notna().any() else None

    for _, g in out.groupby("race_key_calc"):
        scoring = g[g.get("included", False).astype(bool)].copy()
        scoring["split_seconds_num"] = pd.to_numeric(scoring.get("split_seconds"), errors="coerce")
        scoring = scoring[scoring["split_seconds_num"].notna()].sort_values("split_seconds_num", ascending=True)
        field_size = len(scoring)
        n = openrank_baseline_count(field_size)
        baseline = float(scoring["split_seconds_num"].head(n).mean()) if n and not scoring.empty else None
        for row_idx, r in g.iterrows():
            split_rank = parse_int(r.get("split_rank"))
            tier = openrank_tier_for_row(r, discipline)
            sof_score = openrank_sof_score(r, tier)
            pos_score = openrank_position_score(split_rank, tier)
            time_score = openrank_time_score(r.get("split_seconds"), baseline, tier, sof_score)
            score = 0.35 * pos_score + 0.35 * sof_score + 0.30 * time_score
            # Keep the confidence/cap logic from the audit so small imported samples
            # or low-quality race types cannot overstate the proof.
            cap = safe_float(r.get("final_cap"))
            if cap is not None:
                score = min(score, cap)
            if not bool(r.get("included", False)):
                score = 0.0
            out.at[row_idx, "openrank_tier"] = tier
            out.at[row_idx, "openrank_position_score"] = round(pos_score, 3)
            out.at[row_idx, "openrank_sof_score"] = round(sof_score, 3)
            out.at[row_idx, "openrank_time_score"] = round(time_score, 3)
            out.at[row_idx, "split_openrank_score"] = round(score, 3)
            out.at[row_idx, "baseline_split"] = baseline
    return out.drop(columns=["race_key_calc"], errors="ignore")


def best4_openrank_average(values: Iterable[Any], divisor: int = 4) -> Tuple[float, List[float]]:
    vals = [float(v) for v in values if safe_float(v) is not None]
    vals = sorted(vals, reverse=True)[:divisor]
    padded = vals + [0.0] * max(0, divisor - len(vals))
    return (sum(padded) / divisor if divisor else 0.0), padded


# Override previous split scoring with OpenRank-aligned split scoring.
def score_splits_for_start_list(
    audit: pd.DataFrame,
    start_athletes: pd.DataFrame,
    target_date: pd.Timestamp,
    top_n: int,
    strong_sof_threshold: float,
) -> pd.DataFrame:
    if audit is None or audit.empty:
        return pd.DataFrame()
    start_urls = set(start_athletes.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).tolist())
    start_names = set(start_athletes.get("athlete_name", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())
    df = add_split_openrank_scores(audit)
    df = df[df.get("included", False).astype(bool)].copy()
    df = df[(df["athlete_url"].isin(start_urls)) | (df["athlete_name"].fillna("").str.lower().isin(start_names))]
    if df.empty:
        return pd.DataFrame()

    discipline = clean_str(df["discipline"].dropna().iloc[0]) if "discipline" in df.columns and df["discipline"].notna().any() else "swim"
    window_start = pd.to_datetime(target_date) - pd.Timedelta(days=365)
    df = df[(df["race_date"].notna()) & (df["race_date"] >= window_start) & (df["race_date"] <= target_date)].copy()
    if df.empty:
        return pd.DataFrame()

    # Recompute quality flags using the current sidebar threshold.
    df["premium_evidence"] = df.apply(lambda r: is_premium_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["strong_evidence"] = df.apply(lambda r: is_strong_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["quality_tier"] = df.apply(lambda r: evidence_quality_label(r, discipline, strong_sof_threshold), axis=1)

    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        g = g.sort_values("race_date", ascending=False).copy()
        score_values = pd.to_numeric(g.get("split_openrank_score"), errors="coerce").dropna().tolist()
        openrank_score, best_scores = best4_openrank_average(score_values, top_n)
        recent = g.head(max(5, top_n)).copy()
        premium = g[g["premium_evidence"].astype(bool)]
        strong = g[g["strong_evidence"].astype(bool)]
        recent_weights = g.get("evidence_weight", pd.Series(1.0, index=g.index)).astype(float).tolist()
        avg_behind = weighted_avg(pd.to_numeric(g.get("pct_behind_fastest"), errors="coerce").dropna().tolist(), None)
        premium_avg_behind = weighted_avg(pd.to_numeric(premium.get("pct_behind_fastest", pd.Series(dtype=float)), errors="coerce").dropna().tolist(), None) if not premium.empty else None
        strong_avg_behind = weighted_avg(pd.to_numeric(strong.get("pct_behind_fastest", pd.Series(dtype=float)), errors="coerce").dropna().tolist(), None) if not strong.empty else None
        premium_count = len(premium)
        strong_count = len(strong)
        evidence_count = len(g)
        # Confidence caps: OpenRank best-4 already pads missing races with zero,
        # but keep a light cap for one-off samples so a single perfect split does
        # not dominate a board.
        final = float(openrank_score)
        if evidence_count <= 1:
            final = min(final, 45)
            confidence = "Low - 1 split"
        elif evidence_count == 2:
            final = min(final, 62)
            confidence = "Medium - 2 splits"
        elif premium_count >= 2:
            confidence = "High - repeated premium proof"
        elif premium_count == 1:
            confidence = "Good - 1 premium row"
        elif strong_count >= 2:
            confidence = "Good - repeated strong proof"
        elif strong_count == 1:
            confidence = "Medium - 1 strong row"
        else:
            final = min(final, 50)
            confidence = "Low - weak/medium evidence"

        best_row = g.sort_values(["split_openrank_score", "race_date"], ascending=[False, False]).head(1)
        last_row = g.sort_values("race_date", ascending=False).head(1)
        rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None,
            "Score": round(final, 1),
            "OpenRank Split Score": round(openrank_score, 1),
            "Best Split Scores Used": ", ".join([f"{x:.1f}" for x in best_scores]),
            "Confidence": confidence,
            "Premium Evidence Count": premium_count,
            "Strong Evidence Count": strong_count,
            "Evidence Count": evidence_count,
            "Premium Field Score": round(pd.to_numeric(premium.get("split_openrank_score", pd.Series(dtype=float)), errors="coerce").mean(), 1) if not premium.empty else 0,
            "Strong Field Score": round(pd.to_numeric(strong.get("split_openrank_score", pd.Series(dtype=float)), errors="coerce").mean(), 1) if not strong.empty else 0,
            "Recent Score": round(pd.to_numeric(recent.get("split_openrank_score", pd.Series(dtype=float)), errors="coerce").mean(), 1) if not recent.empty else 0,
            "Premium Avg Behind %": None if premium_avg_behind is None else round(premium_avg_behind, 2),
            "Strong Avg Behind %": None if strong_avg_behind is None else round(strong_avg_behind, 2),
            "Recent Avg Behind %": None if avg_behind is None else round(avg_behind, 2),
            "Premium Top 3 %": round(((premium["split_rank"] <= 3).mean() * 100), 1) if not premium.empty else 0,
            "Premium Fastest %": round(((premium["split_rank"] == 1).mean() * 100), 1) if not premium.empty else 0,
            "Strong Top 3 %": round(((strong["split_rank"] <= 3).mean() * 100), 1) if not strong.empty else 0,
            "Strong Fastest %": round(((strong["split_rank"] == 1).mean() * 100), 1) if not strong.empty else 0,
            "Recent Top 3 %": round(((g["split_rank"] <= 3).mean() * 100), 1),
            "Recent Fastest %": round(((g["split_rank"] == 1).mean() * 100), 1),
            "Last Race": clean_str(last_row["race_name"].iloc[0]) if not last_row.empty else "",
            "Last Race Date": format_date(last_row["race_date"].iloc[0]) if not last_row.empty else "",
            "Last Rank": clean_str(last_row["rank_display"].iloc[0]) if not last_row.empty else "",
            "Best Recent Split": clean_str(best_row["split"].iloc[0]) if not best_row.empty else "",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out


# Override previous overall scoring with OpenRank's best-4-in-52-weeks model.
def score_overall(
    results: pd.DataFrame,
    start_athletes: pd.DataFrame,
    overrides: pd.DataFrame,
    target_date: pd.Timestamp,
    target_year: int,
    top_n: int,
) -> pd.DataFrame:
    if results is None or results.empty or start_athletes is None or start_athletes.empty:
        return pd.DataFrame()
    start_urls = set(start_athletes.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).tolist())
    start_names = set(start_athletes.get("athlete_name", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())
    df = results.copy()
    window_start = pd.to_datetime(target_date) - pd.Timedelta(days=365)
    df = df[(df["race_date"].notna()) & (df["race_date"] >= window_start) & (df["race_date"] <= target_date) & (~df["bad_status"])]
    df = df[(df["athlete_url"].isin(start_urls)) | (df["athlete_name"].fillna("").str.lower().isin(start_names))]
    df = df[df["ors"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    start_lookup, name_start_lookup = start_lookup_maps(start_athletes)
    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        scored_rows = []
        for _, r in g.sort_values("race_date", ascending=False).iterrows():
            excluded, mult, reason = match_override(r, overrides, "Overall")
            if excluded:
                continue
            rr = r.copy()
            rr["ors_for_rank"] = (safe_float(r.get("ors")) or 0.0) * mult
            scored_rows.append(rr)
        if not scored_rows:
            continue
        gg = pd.DataFrame(scored_rows).sort_values("race_date", ascending=False)
        rank_score_val, best_scores = best4_openrank_average(gg["ors_for_rank"].tolist(), top_n)
        current_year = gg[gg["race_date"].dt.year == target_year].copy()
        current_year_values = pd.to_numeric(current_year.get("ors_for_rank", pd.Series(dtype=float)), errors="coerce").dropna().tolist() if not current_year.empty else []
        # Display a real current-year ORS average from scored current-year races.
        # Do not pad this display value with zeros; padding is only for the main
        # OpenRank-style ranking score. This makes it obvious when an athlete has
        # races this year but none of those rows carried an ORS value.
        current_year_score = float(np.mean(sorted(current_year_values, reverse=True)[:top_n])) if current_year_values else None
        current_year_races = int(len(current_year))
        current_year_scored = int(len(current_year_values))
        strong = gg[(gg["sof"].fillna(0) >= 70) | (gg["race_type"].isin(["T100", "WTCS"]))]
        strong_score = pd.to_numeric(strong.get("ors_for_rank", pd.Series(dtype=float)), errors="coerce").mean() if not strong.empty else 0
        name = g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else str(athlete_key)
        url = g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None
        start_row = start_lookup.get(url) if url else name_start_lookup.get(name.lower())
        open_rank = parse_int(start_row.get("open_rank")) if isinstance(start_row, dict) else None
        rows.append({
            "Athlete": name,
            "Athlete URL": url,
            "Score": round(rank_score_val, 1),
            "OpenRank Score": round(rank_score_val, 1),
            "Best Scores Used": ", ".join([f"{x:.1f}" for x in best_scores]),
            "Recent Form ORS": round(rank_score_val, 1),
            "Current Year ORS": round(float(current_year_score), 1) if current_year_score is not None and not pd.isna(current_year_score) else None,
            "Current Year Races": current_year_races,
            "Current Year Scored": current_year_scored,
            "Best Recent ORS": round(max(best_scores), 1) if best_scores else 0,
            "Strong Field ORS": round(float(strong_score), 1) if strong_score is not None and not pd.isna(strong_score) else 0,
            "Championship Score": round(championship_result_score(gg.sort_values("race_date", ascending=False).iloc[0]), 1) if not gg.empty else 0,
            "Recent Races Used": len([x for x in best_scores if x > 0]),
            "OpenRank": open_rank,
            "Last Race": clean_str(gg.iloc[0].get("race_name")) if len(gg) else "",
            "Last Race Date": format_date(gg.iloc[0].get("race_date")) if len(gg) else "",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out



DISPLAY_LABELS = {
    "athlete_name": "Athlete",
    "athlete_url": "Athlete URL",
    "race_date": "Date",
    "race_name": "Race",
    "race_type": "Race Type",
    "distance": "Distance",
    "quality_tier": "Quality Tier",
    "premium_evidence": "Premium Evidence",
    "strong_evidence": "Strong Evidence",
    "place": "Place",
    "status": "Status",
    "bad_status": "Bad Status",
    "split_status_excluded": "Status Excluded",
    "draft_bike_excluded": "Draft Bike Excluded",
    "sof": "SOF",
    "sof_source": "SOF Source",
    "sof_original": "Original SOF",
    "ors": "ORS",
    "sample_size": "Sample Size",
    "field_size": "Sample Size",
    "field_source": "Field Source",
    "coverage_note": "Coverage Note",
    "split": "Split",
    "swim_split": "Swim",
    "bike_split": "Bike",
    "run_split": "Run",
    "swim_seconds": "Swim Seconds",
    "bike_seconds": "Bike Seconds",
    "run_seconds": "Run Seconds",
    "split_seconds": "Split Seconds",
    "split_rank": "Split Rank",
    "rank_display": "Split Rank",
    "sample_rank_display": "Split Rank",
    "pct_behind_fastest": "% Behind Fastest",
    "gap_when_fastest_pct": "Gap When Fastest %",
    "closeness_score": "Closeness Score",
    "rank_score": "Rank Score",
    "dominance_score": "Dominance Score",
    "raw_score": "Raw Score",
    "sof_cap": "SOF Cap",
    "field_cap": "Sample Cap",
    "race_type_cap": "Race Type Cap",
    "final_cap": "Final Cap",
    "evidence_score": "Evidence Score",
    "evidence_weight": "Evidence Weight",
    "included": "Included",
    "reason": "Reason",
    "gender": "Gender",
    "openrank_tier": "ORS Tier",
    "openrank_position_score": "ORS Position",
    "openrank_sof_score": "ORS SOF",
    "openrank_time_score": "ORS Time",
    "split_openrank_score": "Split ORS",
    "baseline_split": "Baseline Split",
}


def humanize_dataframe_for_display(show: pd.DataFrame) -> pd.DataFrame:
    """Make internal dataframe columns readable before displaying them."""
    show = show.copy()

    for date_col in ["race_date", "Last Race Date", "Date"]:
        if date_col in show.columns:
            show[date_col] = show[date_col].map(format_date)

    percent_cols = [
        "pct_behind_fastest",
        "gap_when_fastest_pct",
        "% Behind Fastest",
        "Gap When Fastest %",
    ]
    for col in percent_cols:
        if col in show.columns:
            show[col] = show[col].map(lambda x: "" if safe_float(x) is None else round(float(x), 2))

    numeric_cols = [
        "evidence_score", "evidence_weight", "closeness_score", "rank_score",
        "dominance_score", "raw_score", "sof_cap", "field_cap", "race_type_cap",
        "final_cap", "SOF", "ORS", "Score", "OpenRank Score",
        "OpenRank Split Score", "Current Year Races", "Current Year Scored", "split_openrank_score", "openrank_position_score",
        "openrank_sof_score", "openrank_time_score", "baseline_split"
    ]
    for col in numeric_cols:
        if col in show.columns:
            show[col] = show[col].map(lambda x: "" if safe_float(x) is None else round(float(x), 2))

    bool_cols = [
        "strong_evidence", "bad_status", "split_status_excluded",
        "draft_bike_excluded", "included"
    ]
    for col in bool_cols:
        if col in show.columns:
            show[col] = show[col].map(lambda x: "Yes" if bool(x) else "No")

    show = show.rename(columns={c: DISPLAY_LABELS.get(c, c) for c in show.columns})

    # Streamlit/pyarrow is strict about mixed object columns. Display tables can
    # safely be rendered as strings after humanizing so blanks, floats, and text
    # do not crash pages like Athlete Rankings.
    for col in show.columns:
        show[col] = show[col].map(lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) or pd.isna(x) else str(x))
    return show

def display_table(df: pd.DataFrame, columns: List[str], height: Optional[int] = None):
    if df is None or df.empty:
        st.info("No data to show.")
        return

    show = df[[c for c in columns if c in df.columns]].copy()
    show = humanize_dataframe_for_display(show)

    # Streamlit 1.58+ rejects height=None. Only pass height when it is a
    # positive integer, otherwise let Streamlit choose its default height.
    kwargs = {
        "width": "stretch",
        "hide_index": True,
    }
    if isinstance(height, int) and height > 0:
        kwargs["height"] = height

    st.dataframe(show, **kwargs)


def selectable_table(df: pd.DataFrame, columns: List[str], key: str, height: Optional[int] = None) -> Optional[pd.Series]:
    """Display a Streamlit dataframe and return the clicked/selected source row.

    Streamlit row selection lets us click an athlete row in a split pick table
    and immediately show that athlete's recent evidence without using a separate
    dropdown first. If selection is unavailable for any reason, the function
    gracefully falls back to a normal dataframe and returns None.
    """
    if df is None or df.empty:
        st.info("No data to show.")
        return None

    source = df.reset_index(drop=True).copy()
    show = source[[c for c in columns if c in source.columns]].copy()
    show = humanize_dataframe_for_display(show)

    kwargs = {
        "width": "stretch",
        "hide_index": True,
        "key": key,
    }
    if isinstance(height, int) and height > 0:
        kwargs["height"] = height

    try:
        event = st.dataframe(
            show,
            on_select="rerun",
            selection_mode="single-row",
            **kwargs,
        )
        selected_rows = []
        try:
            selected_rows = list(event.selection.rows)
        except Exception:
            if isinstance(event, dict):
                selected_rows = event.get("selection", {}).get("rows", []) or []
        if selected_rows:
            row_idx = int(selected_rows[0])
            if 0 <= row_idx < len(source):
                return source.iloc[row_idx]
    except TypeError:
        # Older Streamlit fallback. Current Cloud version should support row
        # selection, but this keeps the dashboard from crashing if API changes.
        st.dataframe(show, width="stretch", hide_index=True)
    return None

# ============================================================
# UI
# ============================================================
apply_dashboard_theme()

NAV_GROUPS = [
    ("Predictions", [
        ("🏆 Race Dashboard", "Race Dashboard"),
        ("🥇 Athlete Rankings", "Athlete Rankings"),
    ]),
    ("Athlete Data", [
        ("👤 Athletes", "Athletes"),
        ("🔎 Split Audit", "Split Audit"),
    ]),
    ("Tools & Admin", [
        ("🧬 Gender Tools", "Gender Tools"),
        ("📥 Import CSVs", "Import CSVs"),
        ("🗄️ Database Viewer", "Database Viewer"),
        ("🔌 Connection", "Connection"),
    ]),
]
PAGE_OPTIONS = {label: page_name for _, items in NAV_GROUPS for label, page_name in items}

if "page_label" not in st.session_state or st.session_state["page_label"] not in PAGE_OPTIONS:
    st.session_state["page_label"] = "🏆 Race Dashboard"

with st.sidebar:
    st.markdown(
        """
        <div class="ptn-sidebar-brand">
            <div><span class="logo">🏁</span><span class="title">Triathlon Picks</span></div>
            <div class="subtitle">Supabase scoring engine · Streamlit dashboard</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for section, items in NAV_GROUPS:
        st.markdown(f'<div class="ptn-sidebar-section">{section}</div>', unsafe_allow_html=True)
        for label, page_name in items:
            active = st.session_state["page_label"] == label
            if st.button(label, key=f"nav_{page_name}", type="primary" if active else "secondary", width="stretch"):
                st.session_state["page_label"] = label
                st.rerun()

    page_label = st.session_state["page_label"]
    page = PAGE_OPTIONS[page_label]
    st.markdown("---")
    if st.button("🔄 Refresh database cache", width="stretch"):
        clear_cache()
        st.rerun()

render_app_hero(page)

if page == "Connection":
    st.header("🔌 Connection")
    try:
        result = supabase.table("athletes").select("id", count="exact").limit(1).execute()
        st.success("Connected to Supabase.")
        st.metric("Athletes", result.count or 0)

        st.subheader("Table counts")
        count_rows_data = []
        for table_name in ["athletes", "athlete_results", "race_field_results", "start_lists", "race_overrides", "scoring_settings", "model_runs", "split_audit"]:
            count_rows_data.append({"Table": table_name, "Rows in Supabase": count_rows(table_name)})
        st.dataframe(pd.DataFrame(count_rows_data), width="stretch", hide_index=True)
    except Exception as e:
        st.error("Could not read from Supabase. Make sure tables exist and secrets are correct.")
        st.exception(e)

elif page == "Import CSVs":
    st.header("📥 Import Google Sheet CSV exports")
    st.write("Export each Google Sheet tab as CSV, then upload it here. Use replace mode for the first import.")
    replace = st.checkbox("Replace existing rows in selected table before importing", value=True)

    table_choice = st.selectbox("CSV type", ["Athlete Results", "Race Field Results", "Start Lists", "Race Overrides", "Scoring Settings"])
    uploaded = st.file_uploader(f"Upload {table_choice} CSV", type=["csv"])

    if uploaded:
        df = read_uploaded_csv(uploaded)
        st.subheader("Preview")
        st.dataframe(df.head(20), width="stretch")
        st.write(f"Rows detected: {len(df):,}")

        if st.button(f"Import {table_choice}", type="primary"):
            try:
                if table_choice == "Athlete Results":
                    rows, athlete_rows = normalize_athlete_results(df)
                    before_count = count_rows("athlete_results")
                    if replace:
                        delete_all("athlete_results")
                    insert_chunks("athlete_results", rows)
                    athlete_inserted, athlete_updated = upsert_athletes_preserve_gender(athlete_rows)
                    clear_cache()
                    after_count = count_rows("athlete_results")
                    st.success(f"Imported {len(rows):,} athlete result rows. Athletes merged: {athlete_inserted:,} new, {athlete_updated:,} updated.")
                    st.info(f"Supabase athlete_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")

                elif table_choice == "Race Field Results":
                    rows, athlete_rows = normalize_race_field_results(df)
                    before_count = count_rows("race_field_results")
                    if replace:
                        delete_all("race_field_results")
                    insert_chunks("race_field_results", rows)
                    athlete_inserted, athlete_updated = upsert_athletes_preserve_gender(athlete_rows)
                    clear_cache()
                    after_count = count_rows("race_field_results")
                    st.success(f"Imported {len(rows):,} race-field result rows. Athletes merged: {athlete_inserted:,} new, {athlete_updated:,} updated.")
                    st.info(f"Supabase race_field_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")

                elif table_choice == "Start Lists":
                    rows, athlete_rows = normalize_start_lists(df)
                    rows = dedupe_start_list_rows(rows)
                    inserted = len(rows)
                    skipped = 0
                    replaced_groups = 0
                    if replace:
                        replaced_groups = delete_matching_start_lists(rows)
                        insert_chunks("start_lists", rows)
                    else:
                        inserted, skipped = merge_start_list_rows(rows)
                    athlete_inserted, athlete_updated = upsert_athletes_preserve_gender(athlete_rows)
                    propagated = apply_gender_updates_from_rows(rows)
                    clear_cache()
                    st.success(f"Imported {inserted:,} new start-list rows and skipped {skipped:,} duplicate rows.")
                    if replace:
                        st.info(f"Replace mode deleted existing rows for {replaced_groups:,} matching race/date/gender group(s), not the entire start_lists table.")
                    st.info(f"Merged athletes by canonical URL: {athlete_inserted:,} new, {athlete_updated:,} updated. Auto-propagated gender for {propagated:,} athletes from this start list import.")

                elif table_choice == "Race Overrides":
                    rows = normalize_race_overrides(df)
                    if replace:
                        delete_all("race_overrides")
                    insert_chunks("race_overrides", rows)
                    clear_cache()
                    st.success(f"Imported {len(rows):,} override rows.")

                elif table_choice == "Scoring Settings":
                    rows = normalize_scoring_settings(df)
                    if replace:
                        delete_all("scoring_settings")
                    upsert_chunks("scoring_settings", rows, on_conflict="setting_group,setting_key")
                    clear_cache()
                    st.success(f"Imported/upserted {len(rows):,} scoring settings.")
            except Exception as e:
                st.error("Import failed.")
                st.exception(e)

elif page == "Athletes":
    st.header("👤 Athletes")
    results, starts, athletes, overrides = prepare_dataframes()
    if results.empty:
        st.warning("No athlete results found. Import Athlete Results first.")
        st.stop()

    view = results.copy()
    search = st.text_input("Search athlete", "")
    gender_filter = st.selectbox("Gender", ["All", "Men", "Women"])
    if search:
        view = view[view["athlete_name"].fillna("").str.contains(search, case=False, na=False)]
    if gender_filter != "All":
        view = view[view["gender"].eq(gender_filter)]

    agg_rows = []
    for key, g in view.groupby(view["athlete_url"].fillna(view["athlete_name"])):
        g = g.sort_values("race_date", ascending=False)
        valid = g[~g.get("bad_status", False).astype(bool)] if "bad_status" in g.columns else g
        recent3 = valid.head(3)
        agg_rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else key,
            "Gender": g["gender"].dropna().iloc[0] if "gender" in g and g["gender"].notna().any() else None,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if "athlete_url" in g and g["athlete_url"].notna().any() else None,
            "Races Imported": len(g),
            "Valid Results": len(valid),
            "Last Race": clean_str(g["race_name"].iloc[0]) if "race_name" in g and not g.empty else "",
            "Last Race Date": format_date(g["race_date"].iloc[0]) if "race_date" in g and not g.empty else "",
            "Best ORS": round(pd.to_numeric(valid.get("ors", pd.Series(dtype=float)), errors="coerce").max(), 1) if not valid.empty else None,
            "Recent 3 ORS": round(pd.to_numeric(recent3.get("ors", pd.Series(dtype=float)), errors="coerce").mean(), 1) if not recent3.empty else None,
        })
    athlete_summary = pd.DataFrame(agg_rows).sort_values(["Recent 3 ORS", "Best ORS"], ascending=[False, False], na_position="last") if agg_rows else pd.DataFrame()
    display_table(athlete_summary.head(200), ["Athlete", "Gender", "Races Imported", "Valid Results", "Last Race", "Last Race Date", "Best ORS", "Recent 3 ORS", "Athlete URL"], height=520)

    if not athlete_summary.empty:
        names = athlete_summary["Athlete"].dropna().tolist()
        selected = st.selectbox("Open athlete career results", names)
        raw = results[results["athlete_name"].fillna("").eq(selected)].sort_values("race_date", ascending=False)
        st.subheader(f"Recent career rows for {selected}")
        display_table(raw.head(25), ["race_date", "race_name", "race_type", "distance", "place", "status", "sof", "sof_source", "ors", "swim_split", "bike_split", "run_split", "data_source"], height=420)


elif page == "Gender Tools":
    st.header("🧬 Gender Tools")
    st.caption("Fill Men/Women competition category from start lists, existing gender values, explicit race-name hints, manual overrides, and permissioned missing-only profile checks. It never guesses from names/photos.")

    raw_athletes = load_table("athletes")
    raw_results = load_table("athlete_results")
    raw_race_fields = load_table("race_field_results")
    raw_starts = load_table("start_lists")

    combined_results = pd.concat(
        [df for df in [raw_results, raw_race_fields] if df is not None and not df.empty],
        ignore_index=True,
        sort=False,
    ) if (raw_results is not None and not raw_results.empty) or (raw_race_fields is not None and not raw_race_fields.empty) else pd.DataFrame()

    def gender_count_row(label: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or df.empty:
            return {"Table": label, "Rows": 0, "Men": 0, "Women": 0, "Missing/Other": 0, "Missing %": ""}
        g = df["gender"].map(normalize_gender) if "gender" in df.columns else pd.Series([None] * len(df))
        missing = int((~g.isin(["Men", "Women"])).sum())
        return {
            "Table": label,
            "Rows": len(df),
            "Men": int(g.eq("Men").sum()),
            "Women": int(g.eq("Women").sum()),
            "Missing/Other": missing,
            "Missing %": f"{(missing / max(len(df), 1)) * 100:.1f}%",
        }

    coverage = pd.DataFrame([
        gender_count_row("athletes", raw_athletes),
        gender_count_row("athlete_results", raw_results),
        gender_count_row("race_field_results", raw_race_fields),
        gender_count_row("start_lists", raw_starts),
    ])
    st.subheader("Gender coverage")
    display_table(coverage, list(coverage.columns), height=180)

    st.markdown("---")
    st.subheader("Athlete URL merge / duplicate cleanup")
    st.caption("Use this after importing start lists/results if the same athlete exists as both /en/athletes/slug and /athletes/slug, or if old imports created duplicate athlete rows.")
    if st.button("Merge duplicate athlete URLs and update related tables"):
        merge_log = merge_duplicate_athlete_urls()
        if merge_log.empty:
            st.success("No duplicate/canonical athlete URL problems found.")
        else:
            st.success(f"Merged/canonicalized {len(merge_log):,} athlete URL groups.")
            display_table(merge_log.head(1000), list(merge_log.columns), height=360)
            st.download_button(
                "Download athlete merge log CSV",
                data=merge_log.to_csv(index=False).encode("utf-8"),
                file_name="athlete_url_merge_log.csv",
                mime="text/csv",
            )

    st.markdown("---")
    suggestions = build_gender_suggestions(raw_athletes, raw_starts, combined_results)
    if suggestions.empty:
        st.warning("No gender suggestions found yet. Import start lists with Gender = Men/Women first.")
    else:
        high = suggestions[(suggestions["Confidence"].eq("High")) & (suggestions["Conflict"].ne("Yes")) & (suggestions["Suggested Gender"].isin(["Men", "Women"]))]
        med = suggestions[(suggestions["Confidence"].eq("Medium")) & (suggestions["Conflict"].ne("Yes")) & (suggestions["Suggested Gender"].isin(["Men", "Women"]))]
        conflict = suggestions[suggestions["Conflict"].eq("Yes")]
        c1, c2, c3 = st.columns(3)
        c1.metric("High-confidence suggestions", f"{len(high):,}")
        c2.metric("Medium suggestions", f"{len(med):,}")
        c3.metric("Conflicts", f"{len(conflict):,}")

        st.subheader("Suggested updates")
        show_conf = st.selectbox("Show confidence", ["High only", "High + Medium", "Conflicts", "All"], index=0)
        view = suggestions.copy()
        if show_conf == "High only":
            view = view[view["Confidence"].eq("High") & view["Conflict"].ne("Yes")]
        elif show_conf == "High + Medium":
            view = view[view["Confidence"].isin(["High", "Medium"]) & view["Conflict"].ne("Yes")]
        elif show_conf == "Conflicts":
            view = view[view["Conflict"].eq("Yes")]
        display_table(view.head(1000), ["Athlete", "Athlete URL", "Suggested Gender", "Confidence", "Conflict", "Sources", "Signal Count"], height=420)

        st.download_button(
            "Download gender suggestions CSV",
            data=suggestions.to_csv(index=False).encode("utf-8"),
            file_name="gender_suggestions.csv",
            mime="text/csv",
        )

        st.markdown("---")
        st.subheader("Apply updates")
        st.warning("Recommended: apply High-confidence suggestions first. Medium suggestions are mostly race-name hints and should be reviewed before applying.")
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Apply High-confidence gender updates", type="primary"):
                applied = apply_gender_updates(suggestions, include_medium=False)
                st.success(f"Applied gender updates for {applied:,} athletes. Refreshing cache...")
                st.rerun()
        with a2:
            if st.button("Apply High + Medium suggestions"):
                applied = apply_gender_updates(suggestions, include_medium=True)
                st.success(f"Applied gender updates for {applied:,} athletes. Refreshing cache...")
                st.rerun()

    st.markdown("---")
    st.subheader("Permissioned profile gender backfill")
    st.caption("Use this only for missing-gender athletes and only in small batches. It checks both /athletes/ and /en/athletes/ profile variants, rate-limited, then propagates any explicit gender/category field found.")

    max_candidates = st.number_input("Missing-gender candidates to preview", min_value=25, max_value=2000, value=250, step=25)
    candidates = missing_gender_athletes(raw_athletes, combined_results, raw_starts, limit=int(max_candidates))
    if candidates.empty:
        st.success("No missing-gender athlete URLs found from the loaded tables.")
    else:
        st.write(f"Missing-gender athlete URL candidates found: {len(candidates):,}")
        display_table(candidates.head(250), ["Athlete", "Athlete URL", "Rows", "Last Race Date", "Last Race"], height=360)
        st.download_button(
            "Download missing-gender candidates CSV",
            data=candidates.to_csv(index=False).encode("utf-8"),
            file_name="missing_gender_athletes.csv",
            mime="text/csv",
        )
        b1, b2 = st.columns(2)
        with b1:
            batch_size = st.number_input("Profile lookup batch size", min_value=1, max_value=200, value=25, step=5)
        with b2:
            delay = st.number_input(
                "Delay between profile checks, seconds",
                min_value=0.0,
                max_value=5.0,
                value=0.25,
                step=0.25,
                help="Optional throttle so the cleanup tool does not hit PTN too fast. Use 0 for no pause on small permissioned batches; 0.25–0.75 is safer for larger batches.",
            )
        st.caption("Delay is optional. It is just a throttle between profile requests so this stays a controlled missing-only cleanup instead of hammering PTN.")
        st.warning("This should be a permissioned, missing-only cleanup tool. Do not schedule it to crawl the whole database daily.")
        if st.button("Run permissioned profile gender backfill", type="primary"):
            log_df = apply_profile_gender_backfill(candidates, batch_size=int(batch_size), delay_seconds=float(delay))
            if log_df.empty:
                st.warning("No rows checked.")
            else:
                found = int((log_df["Detected Gender"].isin(["Men", "Women"])).sum())
                st.success(f"Checked {len(log_df):,} profiles. Found and applied {found:,} genders.")
                if found == 0:
                    st.info("If Source shows not_found, the profile HTML did not expose an explicit gender/category field in the places we checked. The Error column now shows which URL variants were checked and the response size so we can tune the parser if needed.")
                display_table(log_df, ["Athlete", "Detected Gender", "Source", "Updated", "Error", "Athlete URL"], height=420)
                st.download_button(
                    "Download profile backfill log CSV",
                    data=log_df.to_csv(index=False).encode("utf-8"),
                    file_name="profile_gender_backfill_log.csv",
                    mime="text/csv",
                )

    st.markdown("---")
    st.subheader("Manual gender override upload")
    st.caption("Upload a CSV with columns: athlete_url, athlete_name, gender. Use this for athletes that have no reliable start-list/race-name source.")
    override_file = st.file_uploader("Manual gender CSV", type=["csv"], key="manual_gender_csv")
    if override_file is not None:
        manual = pd.read_csv(override_file)
        manual_rows = []
        for _, r in manual.iterrows():
            g = normalize_gender(first_col(r, ["gender", "Gender", "sex", "Sex"]))
            url = canonical_athlete_url(first_col(r, ["athlete_url", "Athlete URL", "url", "URL"]))
            name = clean_str(first_col(r, ["athlete_name", "Athlete", "Name", "athlete"]))
            if g in ["Men", "Women"] and (url or name):
                manual_rows.append({
                    "Athlete URL": url,
                    "Athlete": name,
                    "Suggested Gender": g,
                    "Confidence": "High",
                    "Conflict": "No",
                    "Sources": "Manual override CSV",
                    "Signal Count": 1,
                })
        manual_df = pd.DataFrame(manual_rows)
        st.write(f"Valid manual override rows: {len(manual_df):,}")
        if not manual_df.empty:
            display_table(manual_df.head(250), ["Athlete", "Athlete URL", "Suggested Gender", "Sources"], height=300)
            if st.button("Apply manual gender overrides", type="primary"):
                applied = apply_gender_updates(manual_df, include_medium=False)
                st.success(f"Applied manual gender overrides for {applied:,} athletes.")
                st.rerun()

elif page == "Athlete Rankings":
    st.header("🥇 Athlete Rankings")
    st.caption("Global rankings are now gender-strict and can be filtered by race family, so Men/Women and 70.3/T100 profiles do not get blended together.")
    results, starts, athletes, overrides = prepare_dataframes()
    if results.empty:
        st.warning("No athlete results found. Import Athlete Results first.")
        st.stop()

    c1, c2, c3, c4 = st.columns([1.1, 1.3, 1.1, 1.1])
    ranking_gender = c1.selectbox("Gender", ["Men", "Women"], index=0)
    ranking_scope = c2.selectbox(
        "Race family",
        ["All", "IRONMAN 70.3 / Middle", "T100 / PTO", "Full IRONMAN", "Short Course / WTCS"],
        index=1,
        help="Use 70.3/Middle for normal 70.3-style rankings, or T100/PTO for that race family only.",
    )
    as_of = c3.date_input("As of date", value=date.today())
    top_n_rank = c4.slider("Top scores used", 3, 8, 4, key="rank_top_n", help="OpenRank-style scoring uses the best X valid scores in the trailing 52 weeks. Missing scores are padded as zero.")
    as_of_ts = pd.Timestamp(as_of)
    year = int(as_of_ts.year)
    window_start_rank = pd.Timestamp(date(year - 2, 1, 1))

    ranking_results = results[(results["race_date"].notna()) & (results["race_date"] >= window_start_rank) & (results["race_date"] <= as_of_ts)].copy()
    pre_gender_count = len(ranking_results)
    ranking_results = filter_rankings_by_gender(ranking_results, ranking_gender)
    post_gender_count = len(ranking_results)
    ranking_results = ranking_results[ranking_scope_mask(ranking_results, ranking_scope)].copy()

    if ranking_results.empty:
        st.warning("No rows match this gender/race-family filter. Check imported genders or choose a different race family.")
        st.stop()

    # Build an all-athlete candidate list from gender-clean imported rows for this window/family.
    candidate_cols = ["athlete_url", "athlete_name", "gender"]
    start_all = ranking_results[candidate_cols].drop_duplicates().dropna(subset=["athlete_name"]).copy()
    start_all["race_name"] = f"Global Rankings — {ranking_scope}"
    start_all["race_date"] = as_of_ts
    start_all["open_rank"] = None

    m1, m2, m3 = st.columns(3)
    m1.metric("Rows after gender filter", f"{post_gender_count:,}", help=f"Started with {pre_gender_count:,} rows in the date window. Known opposite-gender rows are excluded; unknown-gender rows are kept if the race name is compatible so older imports do not hide athletes with missing gender.")
    m2.metric("Rows after race-family filter", f"{len(ranking_results):,}")
    m3.metric("Athletes ranked", f"{start_all['athlete_name'].nunique():,}")

    # Streamlit tabs eagerly execute every tab on every rerun. That made a simple
    # filter change calculate Overall + Swim + Bike + Run every time. Use a
    # segmented/radio selector so only the selected ranking view is computed.
    ranking_view = st.radio(
        "Ranking view",
        ["🏆 Overall", "🏊 Swim", "🚴 Bike", "🏃 Run"],
        horizontal=True,
        key="athlete_rankings_view",
    )

    if ranking_view == "🏆 Overall":
        with st.spinner("Calculating overall rankings..."):
            overall_all = score_overall(ranking_results, start_all, overrides, as_of_ts, year, top_n_rank)
        display_table(
            overall_all.head(75),
            ["Rank", "Athlete", "Score", "OpenRank Score", "Best Scores Used", "Current Year ORS", "Current Year Races", "Current Year Scored", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "Last Race", "Last Race Date", "Athlete URL"],
            height=620,
        )
    else:
        disc = {"🏊 Swim": "swim", "🚴 Bike": "bike", "🏃 Run": "run"}[ranking_view]
        with st.spinner(f"Calculating {disc} rankings..."):
            aud = build_split_audit(ranking_results, start_all, overrides, as_of_ts, ranking_gender, disc, min_field_size=5)
            scored = score_splits_for_start_list(aud, start_all, as_of_ts, top_n_rank, strong_sof_threshold=70)
        display_table(
            scored.head(75),
            ["Rank", "Athlete", "Score", "OpenRank Split Score", "Best Split Scores Used", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Premium Field Score", "Strong Field Score", "Premium Avg Behind %", "Strong Avg Behind %", "Recent Avg Behind %", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split", "Athlete URL"],
            height=620,
        )

elif page == "Database Viewer":
    st.header("🗄️ Database Viewer")
    table = st.selectbox("Table", ["athletes", "athlete_results", "race_field_results", "start_lists", "race_overrides", "scoring_settings", "model_runs", "split_audit"])
    exact_count = count_rows(table)
    if exact_count is not None:
        st.metric("Rows in Supabase", f"{exact_count:,}")
    limit_max = max(5000, min(100000, int(exact_count or 50000)))
    limit = st.slider("Rows to display", 10, limit_max, min(5000, limit_max))
    try:
        all_rows = fetch_all(table, page_size=1000)
        df_all = pd.DataFrame(all_rows)
        st.write(f"Fetched {len(df_all):,} rows from Supabase. Showing first {min(limit, len(df_all)):,}.")
        st.dataframe(df_all.head(limit), width="stretch")
        if not df_all.empty:
            st.download_button(
                label=f"Download all {table} rows as CSV",
                data=df_all.to_csv(index=False).encode("utf-8"),
                file_name=f"{table}.csv",
                mime="text/csv",
            )
    except Exception as e:
        st.error("Could not load table.")
        st.exception(e)

elif page in {"Race Dashboard", "Split Audit"}:
    results, starts, athletes, overrides = prepare_dataframes()
    if starts.empty:
        st.warning("No start lists found. Import Start Lists first.")
        st.stop()
    if results.empty:
        st.warning("No athlete results found. Import Athlete Results first.")
        st.stop()

    race_options_df = starts.dropna(subset=["race_name"]).copy()
    race_options_df["race_date_label"] = race_options_df["race_date"].map(format_date)
    race_options_df["label"] = race_options_df["race_date_label"].fillna("") + " | " + race_options_df["gender"].fillna("") + " | " + race_options_df["race_name"].fillna("")
    race_options_df = race_options_df.drop_duplicates(subset=["race_name", "race_date", "gender", "label"]).sort_values(["race_date", "race_name", "gender"], na_position="last")
    labels = race_options_df["label"].tolist()
    if not labels:
        st.warning("No usable start list races found.")
        st.stop()

    with st.sidebar:
        selected_label = st.selectbox("Race / Gender", labels, index=max(0, len(labels) - 1))
        top_n = st.slider("Top scores used", 3, 8, 4, help="OpenRank-style scoring uses the best X valid scores in the trailing 52 weeks. Missing scores are padded as zero.")
        min_field_size = st.slider("Low-sample warning threshold", 3, 15, 5)
        strong_sof_threshold = st.slider("Strong-field SOF threshold", 55, 90, 70)

    selected_meta = race_options_df[race_options_df["label"] == selected_label].iloc[0]
    selected_race = selected_meta["race_name"]
    selected_gender = selected_meta["gender"]
    selected_date = selected_meta["race_date"]
    if pd.isna(selected_date):
        selected_date = pd.Timestamp.today().normalize()
    target_year = int(pd.to_datetime(selected_date).year)
    window_start = pd.Timestamp(date(target_year - 2, 1, 1))

    start_athletes = starts[
        (starts["race_name"] == selected_race)
        & (starts["gender"] == selected_gender)
    ].copy()
    if pd.notna(selected_meta["race_date"]):
        start_athletes = start_athletes[start_athletes["race_date"] == selected_meta["race_date"]]

    imported_start_rows = len(start_athletes)
    start_athletes = dedupe_start_athletes(start_athletes)
    duplicate_start_rows = imported_start_rows - len(start_athletes)

    # Use two full calendar years back through race day.
    results_window_all = results[(results["race_date"].notna()) & (results["race_date"] >= window_start) & (results["race_date"] <= selected_date)].copy()
    prediction_scope = prediction_scope_from_race(selected_race, None, None)
    results_window = apply_prediction_scope(results_window_all, prediction_scope)

    render_race_card(selected_race, selected_gender, selected_date, window_start)

    # Performance: build each split audit only from races relevant to the
    # selected start-list athletes, not from every result row in the 2-year
    # window. This is the main speed fix for switching start lists.
    audit_source_by_disc = {
        disc: filter_results_to_startlist_races(results_window, start_athletes, disc)
        for disc in ["swim", "bike", "run"]
    }
    audit_by_disc = {
        disc: build_split_audit(audit_source_by_disc[disc], start_athletes, overrides, selected_date, selected_gender, disc, min_field_size)
        for disc in ["swim", "bike", "run"]
    }

    if page == "Race Dashboard":
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Start list athletes", len(start_athletes), delta=(f"{duplicate_start_rows} duplicate rows ignored" if duplicate_start_rows else None))
        c2.metric("Prediction profile", prediction_scope)
        c3.metric("Rows used", len(results_window), delta=(f"from {len(results_window_all):,}" if len(results_window_all) != len(results_window) else None))
        c4.metric("Overrides", len(overrides) if not overrides.empty else 0)
        c5.metric("Low-sample warning", min_field_size)
        if prediction_scope == "Short Course / WTCS":
            st.info("Short-course / WTCS predictor is restricted to Olympic, Sprint, WTCS, World Triathlon Cup, and Continental Cup evidence. 70.3 and full-distance rows are not used for this selected start list.")

        with st.expander("Split data health", expanded=False):
            health = []
            for disc in ["swim", "bike", "run"]:
                split_col = f"{disc}_seconds"
                valid_rows = int(results_window[split_col].notna().sum()) if split_col in results_window.columns else 0
                audit_rows = len(audit_by_disc.get(disc, pd.DataFrame()))
                included_rows = int(audit_by_disc[disc]["included"].sum()) if not audit_by_disc.get(disc, pd.DataFrame()).empty and "included" in audit_by_disc[disc].columns else 0
                start_included = 0
                if not audit_by_disc.get(disc, pd.DataFrame()).empty:
                    aud_tmp = audit_by_disc[disc]
                    start_urls_tmp = set(start_athletes["athlete_url"].dropna().astype(str).tolist()) if "athlete_url" in start_athletes else set()
                    start_names_tmp = set(start_athletes["athlete_name"].dropna().astype(str).str.lower().tolist()) if "athlete_name" in start_athletes else set()
                    start_mask = (aud_tmp["athlete_url"].isin(start_urls_tmp)) | (aud_tmp["athlete_name"].fillna("").str.lower().isin(start_names_tmp))
                    start_included = int((start_mask & aud_tmp["included"]).sum())
                source_rows = len(audit_source_by_disc.get(disc, pd.DataFrame()))
                health.append({
                    "Discipline": disc,
                    "Valid result rows in window": valid_rows,
                    "Rows scanned for selected race": source_rows,
                    "Audit rows": audit_rows,
                    "Included audit rows": included_rows,
                    "Included start-list rows": start_included,
                })
            st.dataframe(pd.DataFrame(health), width="stretch", hide_index=True)
            st.caption("Important: sample size is the number of imported rows we currently have for that race, not the full ProTriNews field. Small imported samples are included but capped/weighted down until full race-field caching is added.")
            with st.expander("Why sample size may not match ProTriNews field size", expanded=False):
                st.write(
                    "The dashboard currently scores split ranks using the rows imported into Supabase. "
                    "So if IRONMAN 70.3 Warsaw 2025 has ~20 athletes on ProTriNews but only 3 of those athletes "
                    "exist in our imported `athlete_results`, the audit will show sample size 3. "
                    "That is not the true field size yet. The next data upgrade is to import/cache full race fields "
                    "from every race URL so ranks and % behind fastest are computed against the actual field."
                )

        section_title("🏆", "Overall Picks")
        overall = score_overall(results_window, start_athletes, overrides, selected_date, target_year, top_n)
        display_table(
            overall.head(15),
            ["Rank", "Athlete", "Score", "OpenRank Score", "Best Scores Used", "Current Year ORS", "Current Year Races", "Current Year Scored", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "OpenRank", "Last Race", "Last Race Date"],
        )

        if not overall.empty:
            st.markdown("#### 🔽 Open an athlete to see recent overall evidence")
            for _, pick in overall.head(10).iterrows():
                athlete_name = clean_str(pick.get("Athlete"))
                athlete_url = clean_str(pick.get("Athlete URL"))
                title_text = f"#{int(pick.get('Rank'))} {athlete_name} — Score {pick.get('Score')}"
                with st.expander(title_text, expanded=False):
                    if results_window.empty:
                        st.info("No result rows loaded.")
                    else:
                        name_mask = results_window["athlete_name"].fillna("").str.lower().eq(str(athlete_name).lower())
                        url_mask = results_window["athlete_url"].astype(str).eq(athlete_url) if athlete_url else pd.Series(False, index=results_window.index)
                        ev = results_window[(url_mask | name_mask) & (~results_window["bad_status"])].sort_values("race_date", ascending=False).head(5)
                        if ev.empty:
                            st.warning("No recent valid overall rows found for this athlete.")
                        else:
                            display_table(
                                ev,
                                ["race_date", "race_name", "race_type", "distance", "place", "sof", "sof_source", "ors", "swim_split", "bike_split", "run_split", "status"],
                            )

        st.divider()
        st.info("Split ranks use each discipline's own best valid split scores from the trailing 52 weeks — not the athlete's top overall races. Swim uses recent swim evidence, bike uses recent bike evidence, and run uses recent run evidence. Full-distance swim/bike now count as high-value non-draft evidence; full-distance run is weighted lower because it transfers less directly to 70.3 speed. Imported sample coverage is still not the full ProTriNews field yet.")
        tabs = st.tabs(["🏊 Fastest Swim", "🚴 Fastest Bike", "🏃 Fastest Run"])
        for tab, disc, title in zip(tabs, ["swim", "bike", "run"], ["Fastest Swim", "Fastest Bike", "Fastest Run"]):
            with tab:
                section_title("🏊" if disc == "swim" else "🚴" if disc == "bike" else "🏃", title)
                scored = score_splits_for_start_list(audit_by_disc[disc], start_athletes, selected_date, top_n, strong_sof_threshold)
                scored_top = scored.head(12).copy()
                display_table(
                    scored_top,
                    ["Rank", "Athlete", "Score", "OpenRank Split Score", "Best Split Scores Used", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Premium Field Score", "Strong Field Score", "Premium Avg Behind %", "Strong Avg Behind %", "Premium Top 3 %", "Strong Top 3 %", "Recent Avg Behind %", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split"],
                    height=360,
                )
                st.caption("Open an athlete below to see the exact split rows considered for this discipline. These are not the athlete's best overall races; each split is scored from its own swim/bike/run evidence.")

                if not scored_top.empty:
                    aud = audit_by_disc[disc]
                    st.markdown("#### 🔽 Athlete split evidence")
                    for _, pick in scored_top.head(10).iterrows():
                        selected_athlete = clean_str(pick.get("Athlete"))
                        selected_url = clean_str(pick.get("Athlete URL"))
                        expander_label = f"#{int(pick.get('Rank'))} {selected_athlete} — Score {pick.get('Score')} — {pick.get('Confidence')}"
                        with st.expander(expander_label, expanded=False):
                            if aud.empty:
                                st.info("No audit rows for this discipline.")
                                continue
                            name_mask = aud["athlete_name"].fillna("").str.lower().eq(str(selected_athlete).lower())
                            url_mask = aud["athlete_url"].astype(str).eq(selected_url) if selected_url else pd.Series(False, index=aud.index)
                            athlete_audit = aud[url_mask | name_mask].sort_values("race_date", ascending=False)
                            used = athlete_audit[athlete_audit["included"]].head(5)
                            if used.empty:
                                st.warning("No split rows were used in the score for this athlete. Showing the most recent evaluated rows instead.")
                                used = athlete_audit.head(5)
                            display_table(
                                used,
                                ["race_date", "race_name", "race_type", "quality_tier", "premium_evidence", "strong_evidence", "place", "status", "sof", "sof_source", "sample_size", "split", "sample_rank_display", "pct_behind_fastest", "evidence_score", "final_cap", "included", "coverage_note", "reason"],
                            )
                            with st.expander("Show all evaluated rows for this athlete", expanded=False):
                                display_table(
                                    athlete_audit.head(12),
                                    ["race_date", "race_name", "race_type", "quality_tier", "premium_evidence", "strong_evidence", "place", "status", "bad_status", "split_status_excluded", "sof", "sof_source", "sample_size", "split", "sample_rank_display", "pct_behind_fastest", "evidence_score", "final_cap", "included", "coverage_note", "reason"],
                                )

    else:
        section_title("🔎", "Split Audit")
        disc = st.selectbox("Discipline", ["swim", "bike", "run"])
        aud = audit_by_disc[disc]
        if aud.empty:
            st.info("No audit rows for this discipline.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Audit rows", len(aud))
            c2.metric("Included rows", int(aud["included"].sum()))
            c3.metric("Excluded rows", int((~aud["included"]).sum()))
            athletes_list = ["All"] + sorted([x for x in aud["athlete_name"].dropna().unique().tolist()])
            athlete_filter = st.selectbox("Athlete", athletes_list)
            show_included = st.radio("Rows", ["Included only", "Excluded only", "All"], horizontal=True)
            view = aud.copy()
            if athlete_filter != "All":
                view = view[view["athlete_name"] == athlete_filter]
            if show_included == "Included only":
                view = view[view["included"]]
            elif show_included == "Excluded only":
                view = view[~view["included"]]
            view = view.sort_values(["athlete_name", "race_date"], ascending=[True, False])
            display_table(
                view,
                ["athlete_name", "race_date", "race_name", "race_type", "quality_tier", "premium_evidence", "strong_evidence", "place", "status", "bad_status", "split_status_excluded", "sof", "sof_source", "sof_original", "sample_size", "field_source", "split", "sample_rank_display", "pct_behind_fastest", "gap_when_fastest_pct", "closeness_score", "rank_score", "raw_score", "sof_cap", "field_cap", "race_type_cap", "final_cap", "evidence_score", "evidence_weight", "included", "coverage_note", "reason"],
                height=650,
            )

            if athlete_filter != "All":
                with st.expander(f"Raw imported career rows for {athlete_filter}", expanded=False):
                    raw = results_window[results_window["athlete_name"].fillna("").eq(athlete_filter)].copy()
                    if raw.empty:
                        st.info("No raw imported result rows found for this athlete in the current analysis window.")
                    else:
                        split_col = f"{disc}_seconds"
                        raw[f"{disc}_split"] = raw[split_col].map(format_seconds) if split_col in raw.columns else "—"
                        raw = raw.sort_values("race_date", ascending=False)
                        st.caption("This is the full imported career data in the analysis window. It explains why rows may not appear as included scoring rows: DNF/DNS/DSQ, missing split, draft-legal bike, or invalid split parsing.")
                        display_table(
                            raw,
                            ["race_date", "race_name", "race_type", "distance", "place", "status", "bad_status", "sof", "sof_source", "sof_original", "ors", f"{disc}_split", "swim_seconds", "bike_seconds", "run_seconds"],
                            height=400,
                        )

