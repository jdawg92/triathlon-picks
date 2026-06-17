import hashlib
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

try:
    from score_engine import build_all_scorecards as build_all_scorecards_fast
except Exception as _score_engine_import_error:
    build_all_scorecards_fast = None
    SCORE_ENGINE_IMPORT_ERROR = _score_engine_import_error
else:
    SCORE_ENGINE_IMPORT_ERROR = None

try:
    from trinews_api_refresh import build_clean_results_refresh
except Exception as _trinews_api_import_error:
    build_clean_results_refresh = None
    TRINEWS_API_IMPORT_ERROR = _trinews_api_import_error
else:
    TRINEWS_API_IMPORT_ERROR = None

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
# Fixed model settings
# ============================================================
MODEL_CACHE_VERSION = "score_engine_v3_fast_clear"
TOP_SCORES_USED = 5
LOW_SAMPLE_WARNING_THRESHOLD = 5
STRONG_SOF_THRESHOLD = 65.0
DEFAULT_SCORECARD_LOOKBACK_DAYS = 365
FULL_IM_SCORECARD_LOOKBACK_DAYS = 730
ALL_PROFILE_SCORECARD_LOOKBACK_DAYS = 730


# ============================================================
# Visual styling
# ============================================================
def apply_dashboard_theme() -> None:
    """Dark, Stripe-inspired dashboard styling."""
    st.markdown(
        """
        <style>
        :root {
            --tri-bg: #070B16;
            --tri-bg-2: #0B1020;
            --tri-panel: rgba(15, 23, 42, 0.88);
            --tri-panel-solid: #111827;
            --tri-panel-2: #151E33;
            --tri-border: rgba(148, 163, 184, 0.18);
            --tri-border-strong: rgba(99, 91, 255, 0.38);
            --tri-text: #F7FAFF;
            --tri-muted: #9AA8C7;
            --tri-subtle: #64748B;
            --tri-primary: #7C5CFF;
            --tri-primary-2: #635BFF;
            --tri-cyan: #00D4FF;
            --tri-green: #19D3A2;
            --tri-warn: #F5A524;
            --tri-danger: #FF5C8A;
            --tri-shadow: rgba(0, 0, 0, 0.38);
            --tri-shadow-soft: rgba(2, 6, 23, 0.42);
        }

        .stApp {
            background:
                radial-gradient(circle at 4% -8%, rgba(99, 91, 255, 0.34), transparent 28rem),
                radial-gradient(circle at 100% 0%, rgba(0, 212, 255, 0.20), transparent 30rem),
                radial-gradient(circle at 62% 18%, rgba(124, 92, 255, 0.12), transparent 25rem),
                linear-gradient(180deg, #050816 0%, #070B16 46%, #0B1020 100%);
            color: var(--tri-text);
        }

        .block-container {
            padding-top: 1.3rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(8, 13, 28, 0.98), rgba(11, 16, 32, 0.96));
            border-right: 1px solid var(--tri-border);
            box-shadow: 18px 0 55px rgba(0, 0, 0, 0.25);
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div {
            color: var(--tri-text);
        }

        .tri-sidebar-brand {
            padding: 0.9rem 0.3rem 1rem 0.3rem;
            margin-bottom: 0.45rem;
            border-bottom: 1px solid var(--tri-border);
        }

        .tri-sidebar-brand .logo {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2.2rem;
            height: 2.2rem;
            border-radius: 0.8rem;
            margin-right: 0.55rem;
            color: white;
            background: linear-gradient(135deg, #7C5CFF 0%, #00D4FF 100%);
            box-shadow: 0 14px 34px rgba(99, 91, 255, 0.32);
        }

        .tri-sidebar-brand .title {
            font-weight: 850;
            font-size: 1.02rem;
            color: var(--tri-text);
            letter-spacing: -0.025em;
        }

        .tri-sidebar-brand .subtitle {
            color: var(--tri-muted);
            font-size: 0.76rem;
            margin-top: 0.18rem;
        }

        .tri-sidebar-section {
            color: var(--tri-subtle);
            font-size: 0.67rem;
            font-weight: 850;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            margin: 1rem 0 0.35rem 0;
            padding-top: 0.58rem;
            border-top: 1px solid var(--tri-border);
        }

        .tri-hero {
            position: relative;
            overflow: hidden;
            padding: 1.45rem 1.6rem;
            border: 1px solid rgba(124, 92, 255, 0.26);
            border-radius: 1.35rem;
            background:
                linear-gradient(135deg, rgba(124, 92, 255, 0.22), rgba(0, 212, 255, 0.08)),
                rgba(15, 23, 42, 0.86);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
            backdrop-filter: blur(14px);
            margin: 0.25rem 0 1.2rem 0;
        }

        .tri-hero:after {
            content: "";
            position: absolute;
            width: 20rem;
            height: 20rem;
            right: -8rem;
            top: -9rem;
            background: radial-gradient(circle, rgba(0, 212, 255, 0.18), transparent 65%);
            pointer-events: none;
        }

        .tri-hero .eyebrow,
        .tri-race-card .eyebrow {
            color: var(--tri-cyan);
            font-size: 0.72rem;
            font-weight: 900;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .tri-hero h1 {
            color: var(--tri-text);
            font-size: 2.12rem;
            line-height: 1.05;
            margin: 0;
            letter-spacing: -0.045em;
        }

        .tri-hero p {
            color: var(--tri-muted);
            margin: 0.55rem 0 0 0;
            font-size: 0.98rem;
        }

        .tri-race-card,
        [data-testid="stMetric"],
        div[data-testid="stExpander"] {
            background: var(--tri-panel);
            border: 1px solid var(--tri-border);
            box-shadow: 0 18px 48px var(--tri-shadow-soft);
            backdrop-filter: blur(12px);
        }

        .tri-race-card {
            padding: 1.15rem 1.25rem;
            border-radius: 1.15rem;
            margin: 0.35rem 0 1rem 0;
        }

        .tri-race-card h2 {
            margin: 0;
            color: var(--tri-text);
            font-size: 1.52rem;
            letter-spacing: -0.035em;
        }

        .tri-race-card .meta {
            color: var(--tri-muted);
            margin-top: 0.4rem;
            font-size: 0.92rem;
        }

        .tri-section-title {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: var(--tri-text);
            font-weight: 850;
            font-size: 1.28rem;
            letter-spacing: -0.03em;
            margin: 1.25rem 0 0.7rem 0;
        }

        .tri-pill {
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 760;
            color: #DDE7FF;
            background: rgba(124, 92, 255, 0.18);
            border: 1px solid rgba(124, 92, 255, 0.34);
        }

        [data-testid="stMetric"] {
            border-radius: 1rem;
            padding: 0.9rem 1rem;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--tri-muted) !important;
            font-weight: 760;
        }

        [data-testid="stMetricValue"] {
            color: var(--tri-text);
            font-weight: 900;
        }

        .stDataFrame,
        [data-testid="stDataFrame"] {
            border-radius: 1rem;
            overflow: hidden;
            border: 1px solid var(--tri-border);
            box-shadow: 0 14px 38px rgba(0, 0, 0, 0.24);
            background: var(--tri-panel-solid);
        }

        div[data-testid="stExpander"] {
            border-radius: 1rem;
            overflow: hidden;
        }

        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] p,
        div[data-testid="stExpander"] span {
            color: var(--tri-text) !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }

        .stTabs [data-baseweb="tab"] {
            height: 2.65rem;
            border-radius: 999px;
            padding: 0 1rem;
            background: rgba(15, 23, 42, 0.78);
            color: var(--tri-muted);
            border: 1px solid var(--tri-border);
        }

        .stTabs [aria-selected="true"] {
            background: rgba(124, 92, 255, 0.20);
            border-color: rgba(124, 92, 255, 0.42);
            color: var(--tri-text);
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 0.78rem;
            border: 1px solid var(--tri-border);
            background: rgba(15, 23, 42, 0.84);
            color: var(--tri-text);
            font-weight: 760;
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.16);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: rgba(0, 212, 255, 0.44);
            background: rgba(25, 35, 60, 0.96);
            color: white;
        }

        [data-testid="stSidebar"] .stButton > button {
            justify-content: flex-start;
            text-align: left;
            padding-left: 0.85rem;
            background: rgba(15, 23, 42, 0.42) !important;
            border-color: rgba(148, 163, 184, 0.16) !important;
            color: #CBD5E1 !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(30, 41, 59, 0.82) !important;
            border-color: rgba(0, 212, 255, 0.32) !important;
            color: #FFFFFF !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] .stButton button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, rgba(124, 92, 255, 0.34), rgba(0, 212, 255, 0.16)) !important;
            border-color: rgba(124, 92, 255, 0.56) !important;
            color: #FFFFFF !important;
            box-shadow: 0 12px 28px rgba(99, 91, 255, 0.20) !important;
        }

        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        textarea,
        input {
            background-color: rgba(15, 23, 42, 0.86) !important;
            color: var(--tri-text) !important;
            border-color: var(--tri-border) !important;
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
            border: 1px solid var(--tri-border);
            background: rgba(15, 23, 42, 0.90);
            color: var(--tri-text);
        }

        code,
        pre {
            background: rgba(2, 6, 23, 0.72) !important;
            color: #DDE7FF !important;
            border: 1px solid var(--tri-border) !important;
            border-radius: 0.75rem !important;
        }

        h1,
        h2,
        h3 {
            color: var(--tri-text);
            letter-spacing: -0.035em;
        }


        .tri-import-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 0.75rem 0 1.1rem 0;
        }

        .tri-import-card {
            min-height: 7.2rem;
            padding: 1rem 1.05rem;
            border-radius: 1.05rem;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background:
                radial-gradient(circle at 100% 0%, rgba(0, 212, 255, 0.09), transparent 46%),
                rgba(15, 23, 42, 0.72);
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.20);
        }

        .tri-import-card .kicker {
            color: var(--tri-cyan);
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-bottom: 0.34rem;
        }

        .tri-import-card .title {
            color: var(--tri-text);
            font-size: 1.05rem;
            font-weight: 850;
            letter-spacing: -0.025em;
            margin-bottom: 0.25rem;
        }

        .tri-import-card .body {
            color: var(--tri-muted);
            font-size: 0.84rem;
            line-height: 1.35;
        }

        .tri-help-strip {
            padding: 0.85rem 0.95rem;
            border-radius: 0.95rem;
            border: 1px solid rgba(0, 212, 255, 0.18);
            background: rgba(0, 212, 255, 0.06);
            color: #BEEBFF;
            margin: 0.65rem 0 1rem 0;
            font-size: 0.9rem;
        }

        @media (max-width: 1100px) {
            .tri-import-grid { grid-template-columns: 1fr; }
        }

        .tri-loader-card {
            display: flex;
            align-items: center;
            gap: 0.9rem;
            padding: 1rem 1.1rem;
            margin: 0.65rem 0 1rem 0;
            border-radius: 1.05rem;
            border: 1px solid rgba(99, 91, 255, 0.36);
            background:
                radial-gradient(circle at 15% 20%, rgba(0, 212, 255, 0.16), transparent 28%),
                linear-gradient(135deg, rgba(124, 92, 255, 0.18), rgba(15, 23, 42, 0.88));
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28);
        }

        .tri-loader-orb {
            width: 2.1rem;
            height: 2.1rem;
            border-radius: 999px;
            background: conic-gradient(from 0deg, var(--tri-cyan), var(--tri-primary), transparent 72%);
            position: relative;
            animation: tri-spin 0.9s linear infinite;
            box-shadow: 0 0 28px rgba(0, 212, 255, 0.28);
            flex: 0 0 auto;
        }

        .tri-loader-orb:after {
            content: "";
            position: absolute;
            inset: 0.32rem;
            border-radius: 999px;
            background: #0B1020;
            border: 1px solid rgba(148, 163, 184, 0.16);
        }

        .tri-loader-title {
            color: var(--tri-text);
            font-weight: 850;
            letter-spacing: -0.02em;
            line-height: 1.15;
        }

        .tri-loader-detail {
            color: var(--tri-muted);
            font-size: 0.86rem;
            margin-top: 0.2rem;
        }

        @keyframes tri-spin {
            to { transform: rotate(360deg); }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_hero(page_name: str) -> None:
    st.markdown(
        f"""
        <div class="tri-hero">
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
        <div class="tri-race-card">
            <div class="eyebrow">Selected Race</div>
            <h2>{race_name}</h2>
            <div class="meta">{gender} · Race date {format_date(race_date)} · Analysis window {format_date(window_start)} to {format_date(race_date)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(icon: str, title: str) -> None:
    st.markdown(f'<div class="tri-section-title"><span>{icon}</span><span>{title}</span></div>', unsafe_allow_html=True)

# ============================================================
# Loading UI helpers
# ============================================================
def loading_card(message: str = "Working...", detail: str = ""):
    """Render a branded temporary loading panel and return its placeholder."""
    placeholder = st.empty()
    safe_message = str(message).replace("<", "&lt;").replace(">", "&gt;")
    safe_detail = str(detail or "").replace("<", "&lt;").replace(">", "&gt;")
    detail_html = f'<div class="tri-loader-detail">{safe_detail}</div>' if safe_detail else ""
    html = f"""
        <div class="tri-loader-card">
            <div class="tri-loader-orb"></div>
            <div>
                <div class="tri-loader-title">{safe_message}</div>
                {detail_html}
            </div>
        </div>
    """
    placeholder.markdown(html, unsafe_allow_html=True)
    return placeholder


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


def iso_date(value: Any) -> str:
    """Return a stable YYYY-MM-DD key for SQL date columns and cache matching."""
    if value is None or value == "":
        return ""
    try:
        d = pd.to_datetime(value, errors="coerce")
        if pd.isna(d):
            return str(value)[:10]
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


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


def short_course_predictor_mask(df: pd.DataFrame) -> pd.Series:
    """Evidence scope for WTCS / short-course predictions and rankings.

    Keep true elite short-course evidence: WTCS, World Triathlon Cup,
    Olympic Games, and Olympic-distance continental/development races only when
    they have enough SOF to be useful. Exclude development-cup Sprint /
    Super Sprint rows, because tiny low-SOF samples can otherwise incorrectly
    push athletes to the top of fastest-split boards.
    """
    if df is None or df.empty:
        return pd.Series([], dtype=bool)

    rt = df.get("race_type", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    race = df.get("race_name", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    dist = df.get("distance", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    txt = (rt + " " + race + " " + dist)
    sof = pd.to_numeric(df.get("sof", pd.Series([np.nan] * len(df), index=df.index)), errors="coerce")

    long_course = txt.str.contains("70.3|middle|challenge|t100|pto|full|140.6|ironman", regex=True, na=False)

    wtcs = txt.str.contains("wtcs|world triathlon championship series", regex=True, na=False)
    world_cup = txt.str.contains("world triathlon cup", regex=True, na=False)
    olympic_games = txt.str.contains("olympic games|tokyo 2020|paris 2024", regex=True, na=False)

    development_cup = txt.str.contains(
        "continental cup|europe triathlon cup|europe cup|americas triathlon cup|africa triathlon cup|asia triathlon cup|oceania triathlon cup",
        regex=True,
        na=False,
    )
    olympic_distance = dist.str.contains("olympic", regex=True, na=False) | rt.eq("olympic")
    sprint_distance = dist.str.contains("sprint|super sprint", regex=True, na=False) | rt.eq("sprint")

    # Allow continental/development races only when they are Olympic-distance
    # and have meaningful SOF. Do not use their Sprint / Super Sprint rows for
    # WTCS fastest-split predictions.
    continental_olympic_quality = development_cup & olympic_distance & (sof >= STRONG_SOF_THRESHOLD)

    major_short_course = wtcs | world_cup | olympic_games
    standalone_olympic = olympic_distance & ~development_cup

    return (major_short_course | continental_olympic_quality | standalone_olympic) & ~long_course & ~(development_cup & sprint_distance)


def long_course_predictor_mask(df: pd.DataFrame) -> pd.Series:
    """Evidence scope for 70.3 / middle-distance predictions.

    The 70.3 predictor should be driven by long-course proof first: 70.3,
    T100/PTO, Challenge middle, and full-distance swim/bike evidence. Elite
    Olympic-distance WTCS/Olympic/World Cup rows can still help for swim/run,
    but development-cup Sprint/Super Sprint rows should not be used. Those tiny
    low-SOF samples were pushing weak swimmers to the top of the fastest-split
    boards.
    """
    if df is None or df.empty:
        return pd.Series([], dtype=bool)

    rt = df.get("race_type", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    race = df.get("race_name", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    dist = df.get("distance", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    txt = (rt + " " + race + " " + dist)
    sof = pd.to_numeric(df.get("sof", pd.Series([np.nan] * len(df), index=df.index)), errors="coerce")

    long_course = txt.str.contains("70.3|middle|challenge|t100|pto|full|140.6", regex=True, na=False)
    full_ironman = (txt.str.contains("ironman", regex=True, na=False) & ~txt.str.contains("70.3", regex=True, na=False))

    wtcs = txt.str.contains("wtcs|world triathlon championship series", regex=True, na=False)
    olympic_games = txt.str.contains("olympic games|tokyo 2020|paris 2024", regex=True, na=False)
    world_cup = txt.str.contains("world triathlon cup", regex=True, na=False)

    development_cup = txt.str.contains(
        "continental cup|europe triathlon cup|europe cup|americas triathlon cup|africa triathlon cup|asia triathlon cup|oceania triathlon cup",
        regex=True,
        na=False,
    )
    olympic_distance = dist.str.contains("olympic", regex=True, na=False) | rt.eq("olympic")
    sprint_distance = dist.str.contains("sprint|super sprint", regex=True, na=False) | rt.eq("sprint")

    # Keep elite short-course rows only when they are not development sprint rows.
    elite_olympic_evidence = (wtcs | olympic_games | (world_cup & olympic_distance & (sof >= STRONG_SOF_THRESHOLD))) & ~sprint_distance

    return (long_course | full_ironman | elite_olympic_evidence) & ~development_cup


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
        return short_course_predictor_mask(df)
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

    Short-course/WTCS prediction uses true elite short-course evidence:
    WTCS, World Triathlon Cup, Olympic Games, and only high-SOF Olympic-distance
    continental/development races. Development Sprint / Super Sprint cup rows
    are excluded so tiny low-SOF samples do not distort fastest-split picks.
    For 70.3, use long-course proof plus elite Olympic-distance evidence only.
    Do not let development Sprint / Super Sprint cup rows drive 70.3 split picks.
    T100/full keep their current broader evidence filters.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if scope == "Short Course / WTCS":
        return df[ranking_scope_mask(df, "Short Course / WTCS")].copy()
    if scope == "IRONMAN 70.3 / Middle":
        return df[long_course_predictor_mask(df)].copy()
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

def json_safe_value(v: Any) -> Any:
    """Convert Python/Pandas/Numpy values into JSON-safe Supabase values."""
    if isinstance(v, dict):
        return {str(k): json_safe_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [json_safe_value(x) for x in v]
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (int, float, str)):
        if isinstance(v, float) and math.isnan(v):
            return None
        return v
    return str(v)


def json_safe_row(row: Any) -> Dict[str, Any]:
    """Convert a Series or dict into a JSON-safe dict for model_cache.rows."""
    if isinstance(row, pd.Series):
        items = row.to_dict().items()
    elif isinstance(row, dict):
        items = row.items()
    else:
        try:
            items = dict(row).items()
        except Exception:
            return {}
    return {str(k): json_safe_value(v) for k, v in items}


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


def fetch_all_filtered(table_name: str, filters: Tuple[Tuple[str, Any], ...], select: str = "*", page_size: int = 1000) -> List[Dict[str, Any]]:
    """Fetch rows with simple equality filters using pagination.

    This keeps fast pages from loading huge raw result tables when they only
    need one saved scorecard slice.
    """
    all_rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        q = supabase.table(table_name).select(select)
        for col, val in filters:
            q = q.eq(col, val)
        res = q.range(start, end).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size
    return all_rows


@st.cache_data(ttl=300, show_spinner=False)
def load_start_lists_light() -> pd.DataFrame:
    """Load only start lists for fast Race Dashboard navigation.

    The dashboard now reads saved athlete_scorecards, so it should not load
    38k+ raw result rows just to open a race.
    """
    starts = load_table("start_lists")
    starts = canonicalize_athlete_url_column(starts)
    if not starts.empty:
        starts.columns = [str(c) for c in starts.columns]
        starts["gender"] = starts["gender"].map(normalize_gender)
        starts["race_date"] = pd.to_datetime(starts.get("race_date"), errors="coerce")
    return starts


def clear_cache():
    st.cache_data.clear()


def delete_rows_in_batches(table_name: str, filters: Optional[List[Tuple[str, Any]]] = None, chunk_size: int = 500) -> int:
    """Delete rows in small batches so Supabase/Postgres does not time out.

    Large scorecard/evidence tables can exceed the PostgREST statement timeout
    when deleted with one broad request. This helper repeatedly selects a small
    batch of ids and deletes only those ids.
    """
    filters = filters or []
    deleted = 0
    while True:
        q = supabase.table(table_name).select("id").limit(chunk_size)
        for col, val in filters:
            q = q.eq(col, val)
        res = q.execute()
        rows = res.data or []
        ids = [r.get("id") for r in rows if r.get("id") is not None]
        if not ids:
            break
        supabase.table(table_name).delete().in_("id", ids).execute()
        deleted += len(ids)
        if len(ids) < chunk_size:
            break
    return deleted


def delete_all(table_name: str):
    return delete_rows_in_batches(table_name)


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


def load_gender_override_map() -> Dict[str, Dict[str, Any]]:
    """Manual gender overrides are the highest-priority gender source.

    If this optional table does not exist yet, return an empty map so the rest
    of the app keeps working. Once created, imports, sync tools, and display
    logic should never overwrite these rows with inferred/start-list gender.
    """
    try:
        df = load_table("athlete_gender_overrides")
    except Exception:
        return {}
    if df is None or df.empty or "athlete_url" not in df.columns:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        url = canonical_athlete_url(r.get("athlete_url"))
        g = normalize_gender(r.get("gender"))
        if url and g in ["Men", "Women"]:
            out[url] = {
                "athlete_url": url,
                "athlete_name": clean_str(r.get("athlete_name")),
                "gender": g,
                "source": clean_str(r.get("source")) or "manual",
            }
    return out


def gender_override_for(athlete_url: Any) -> Optional[str]:
    url = canonical_athlete_url(athlete_url)
    if not url:
        return None
    rec = load_gender_override_map().get(url)
    return normalize_gender(rec.get("gender")) if rec else None


def upsert_gender_override_rows(rows: List[Dict[str, Any]]) -> int:
    """Persist manual gender overrides so future imports cannot undo them."""
    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        url = canonical_athlete_url(row.get("athlete_url") or row.get("Athlete URL"))
        g = normalize_gender(row.get("gender") or row.get("Suggested Gender"))
        name = clean_str(row.get("athlete_name") or row.get("Athlete"))
        if not url or g not in ["Men", "Women"]:
            continue
        if url in seen:
            continue
        seen.add(url)
        cleaned.append({
            "athlete_url": url,
            "athlete_name": name,
            "gender": g,
            "source": "manual_csv",
            "notes": clean_str(row.get("notes") or row.get("Notes")),
            "updated_at": datetime.utcnow().isoformat(),
        })
    if not cleaned:
        return 0
    try:
        upsert_chunks("athlete_gender_overrides", cleaned, on_conflict="athlete_url")
    except Exception as e:
        st.error("Could not save athlete_gender_overrides. Run the gender override SQL table script first.")
        st.exception(e)
        return 0
    clear_cache()
    return len(cleaned)


def athlete_upsert_rows_preserve_gender(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prepare athlete upserts without overwriting known gender with blank/null.

    Supabase upserts can update provided columns on conflict. Imported Athlete
    Results often have gender blank, so sending {gender: None} can erase a
    gender that was already learned from a start list. This helper omits the
    gender key when it is missing.
    """
    cleaned: List[Dict[str, Any]] = []
    seen = set()
    override_map = load_gender_override_map()
    for row in rows or []:
        athlete_url = canonical_athlete_url(row.get("athlete_url"))
        athlete_name = clean_str(row.get("athlete_name"))
        if not athlete_url:
            continue
        out = {"athlete_url": athlete_url, "athlete_name": athlete_name}
        override_gender = normalize_gender((override_map.get(athlete_url) or {}).get("gender"))
        g = override_gender or normalize_gender(row.get("gender"))
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

    override_map = load_gender_override_map()
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
            override_gender = normalize_gender((override_map.get(url) or {}).get("gender"))
            existing_gender = normalize_gender(existing_row.get("gender"))
            final_gender = override_gender or incoming_gender
            if incoming_name and not existing_name:
                payload["athlete_name"] = incoming_name
            if final_gender in ["Men", "Women"] and (existing_gender not in ["Men", "Women"] or override_gender):
                if existing_gender != final_gender:
                    payload["gender"] = final_gender
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



def build_athlete_master_maps() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Return athlete-master lookup maps by canonical URL and unique lower-name.

    The athletes table is treated as the master identity table. Result rows and
    start-list rows should point back to this table by canonical athlete_url.
    Name matching is only used when a name is unique in the athletes table.
    """
    athletes_df = load_table("athletes")
    url_map: Dict[str, Dict[str, Any]] = {}
    name_buckets: Dict[str, List[Dict[str, Any]]] = {}
    if athletes_df is None or athletes_df.empty:
        return url_map, {}
    for _, r in athletes_df.iterrows():
        rec = r.to_dict()
        url = canonical_athlete_url(rec.get("athlete_url"))
        name = clean_str(rec.get("athlete_name"))
        if url:
            rec["athlete_url"] = url
            if url not in url_map:
                url_map[url] = rec
        if name:
            name_buckets.setdefault(name.lower(), []).append(rec)
    unique_name_map = {name: vals[0] for name, vals in name_buckets.items() if len(vals) == 1}
    return url_map, unique_name_map


def fill_row_from_athlete_master(row: Dict[str, Any], default_gender: Any = None) -> Dict[str, Any]:
    """Fill an import row from the athletes master record when possible.

    Priority:
    1. Canonical athlete_url match.
    2. Unique athlete_name match when URL is blank.
    3. Imported row values.
    4. Default gender from selected start list, when provided.
    """
    url_map, name_map = build_athlete_master_maps()
    out = dict(row or {})
    url = canonical_athlete_url(out.get("athlete_url"))
    name = clean_str(out.get("athlete_name"))
    master = url_map.get(url) if url else None
    if master is None and not url and name:
        master = name_map.get(name.lower())
        if master:
            url = canonical_athlete_url(master.get("athlete_url"))

    if url:
        out["athlete_url"] = url
    override_gender = gender_override_for(url) if url else None
    if master:
        if not clean_str(out.get("athlete_name")):
            out["athlete_name"] = clean_str(master.get("athlete_name"))
    if override_gender in ["Men", "Women"]:
        out["gender"] = override_gender
    elif master:
        master_gender = normalize_gender(master.get("gender"))
        if master_gender in ["Men", "Women"] and normalize_gender(out.get("gender")) not in ["Men", "Women"]:
            out["gender"] = master_gender
    default_g = normalize_gender(default_gender)
    if default_g in ["Men", "Women"] and normalize_gender(out.get("gender")) not in ["Men", "Women"]:
        out["gender"] = default_g
    return out


def fill_rows_from_athlete_master(rows: List[Dict[str, Any]], default_gender: Any = None) -> List[Dict[str, Any]]:
    return [fill_row_from_athlete_master(row, default_gender=default_gender) for row in (rows or [])]


def athlete_rows_from_import_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build athlete master rows from any imported rows that contain athlete data."""
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        url = canonical_athlete_url(row.get("athlete_url"))
        name = clean_str(row.get("athlete_name"))
        gender = normalize_gender(row.get("gender"))
        if not url:
            continue
        current = best.get(url, {"athlete_url": url})
        if name and not clean_str(current.get("athlete_name")):
            current["athlete_name"] = name
        override_gender = gender_override_for(url)
        final_gender = override_gender or gender
        if final_gender in ["Men", "Women"] and (normalize_gender(current.get("gender")) not in ["Men", "Women"] or override_gender):
            current["gender"] = final_gender
        best[url] = current
    return list(best.values())


def sync_athlete_master_import(rows: List[Dict[str, Any]], athlete_rows: List[Dict[str, Any]] = None, default_gender: Any = None) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """Treat athletes as the master table for every import.

    This does four things:
    - canonicalizes athlete URLs before anything is inserted;
    - fills row gender/name from an existing athletes master record;
    - creates missing athletes when a new URL is imported;
    - propagates known Men/Women gender to related result/start-list rows.

    Returns: enriched_rows, athlete_inserted, athlete_updated, gender_propagated
    """
    enriched_rows = fill_rows_from_athlete_master(rows or [], default_gender=default_gender)
    master_rows = []
    if athlete_rows:
        master_rows.extend(fill_rows_from_athlete_master(athlete_rows, default_gender=default_gender))
    master_rows.extend(athlete_rows_from_import_rows(enriched_rows))
    athlete_inserted, athlete_updated = upsert_athletes_preserve_gender(master_rows)
    # Reload master after insert/update so newly learned gender can be applied back to rows.
    clear_cache()
    enriched_rows = fill_rows_from_athlete_master(enriched_rows, default_gender=default_gender)
    gender_propagated = apply_gender_updates_from_rows(enriched_rows)
    return enriched_rows, athlete_inserted, athlete_updated, gender_propagated


def repair_related_rows_from_athlete_master() -> pd.DataFrame:
    """Backfill related tables from the athletes master table.

    This is a maintenance tool for older imports. It fills missing related-table
    gender from athletes.gender and canonicalizes related athlete URLs.
    """
    athletes_df = load_table("athletes")
    if athletes_df is None or athletes_df.empty or "athlete_url" not in athletes_df.columns:
        return pd.DataFrame()
    url_map: Dict[str, Dict[str, Any]] = {}
    override_map = load_gender_override_map()
    for _, r in athletes_df.iterrows():
        url = canonical_athlete_url(r.get("athlete_url"))
        if not url:
            continue
        override_gender = normalize_gender((override_map.get(url) or {}).get("gender"))
        url_map[url] = {
            "athlete_url": url,
            "athlete_name": clean_str(r.get("athlete_name")),
            "gender": override_gender or normalize_gender(r.get("gender")),
            "has_override": bool(override_gender),
        }

    for url, rec in override_map.items():
        if url not in url_map:
            url_map[url] = {
                "athlete_url": url,
                "athlete_name": clean_str(rec.get("athlete_name")),
                "gender": normalize_gender(rec.get("gender")),
                "has_override": True,
            }

    logs = []
    for table in ["athlete_results", "race_field_results", "start_lists"]:
        df = load_table(table)
        if df is None or df.empty or "athlete_url" not in df.columns:
            logs.append({"Table": table, "Rows Checked": 0, "Rows Updated": 0})
            continue
        updated = 0
        checked = 0
        for _, r in df.iterrows():
            checked += 1
            row_id = r.get("id")
            old_url = clean_str(r.get("athlete_url"))
            url = canonical_athlete_url(old_url)
            if not url:
                continue
            master = url_map.get(url)
            payload: Dict[str, Any] = {}
            if old_url and old_url != url:
                payload["athlete_url"] = url
            if master:
                current_gender = normalize_gender(r.get("gender"))
                master_gender = normalize_gender(master.get("gender"))
                if master_gender in ["Men", "Women"] and (current_gender not in ["Men", "Women"] or master.get("has_override")):
                    if current_gender != master_gender:
                        payload["gender"] = master_gender
                if not clean_str(r.get("athlete_name")) and master.get("athlete_name"):
                    payload["athlete_name"] = master.get("athlete_name")
            if payload:
                try:
                    if row_id is not None and not (isinstance(row_id, float) and math.isnan(row_id)):
                        supabase.table(table).update(payload).eq("id", int(row_id)).execute()
                    else:
                        q = supabase.table(table).update(payload).eq("athlete_url", old_url)
                        q.execute()
                    updated += 1
                except Exception:
                    pass
        logs.append({"Table": table, "Rows Checked": checked, "Rows Updated": updated})
    clear_cache()
    return pd.DataFrame(logs)


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


def result_import_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Stable key for one athlete race-result row.

    Imports should merge on this key instead of appending another duplicate row.
    It intentionally matches the database guard we tried to create earlier:
    athlete_url + race_date + race_name + race_type.
    """
    athlete_key = canonical_athlete_url(row.get("athlete_url")) or (clean_str(row.get("athlete_name")) or "").strip().lower()
    race_date = iso_date(row.get("race_date"))
    race_name = (clean_str(row.get("race_name")) or "").strip().lower()
    race_type = (clean_str(row.get("race_type")) or clean_str(row.get("distance")) or "").strip().lower()
    return athlete_key, race_date, race_name, race_type


def row_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, (np.floating,)) and math.isnan(float(value)):
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def result_row_quality(row: Dict[str, Any]) -> float:
    """Score how complete a normalized result row is so duplicates keep the best copy."""
    score = 0.0
    for col in [
        "athlete_url", "athlete_name", "gender", "race_date", "race_name", "race_url",
        "race_type", "distance", "place", "sof", "ors", "status",
        "swim_seconds", "bike_seconds", "run_seconds",
    ]:
        if row_has_value(row.get(col)):
            score += 1.0
    # ORS/SOF/splits matter more than descriptive fields.
    for col in ["ors", "sof", "swim_seconds", "bike_seconds", "run_seconds"]:
        if row_has_value(row.get(col)):
            score += 2.0
    return score


def dedupe_result_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate result rows inside one uploaded CSV, keeping the best row."""
    best: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for row in rows or []:
        row = dict(row)
        row["athlete_url"] = canonical_athlete_url(row.get("athlete_url")) or row.get("athlete_url")
        key = result_import_key(row)
        # If we cannot identify athlete + race, leave the row in by making a unique fallback key.
        if not key[0] or not key[1] or not key[2]:
            key = (key[0] or f"missing-athlete-{len(best)}", key[1] or "missing-date", key[2] or f"missing-race-{len(best)}", key[3])
        current = best.get(key)
        if current is None or result_row_quality(row) > result_row_quality(current):
            best[key] = row
    return list(best.values())


def build_existing_result_map(table_name: str) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """Map existing DB result rows by the same key used for imports."""
    existing = load_table(table_name)
    existing_map: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    if existing is None or existing.empty:
        return existing_map
    existing = canonicalize_athlete_url_column(existing)
    for _, r in existing.iterrows():
        rec = r.to_dict()
        key = result_import_key(rec)
        if not key[0] or not key[1] or not key[2]:
            continue
        current = existing_map.get(key)
        if current is None or result_row_quality(rec) > result_row_quality(current):
            existing_map[key] = rec
    return existing_map


def result_update_payload(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Create a safe update payload for an existing duplicate result row.

    We update missing/weak fields from the imported row rather than inserting a
    new duplicate. This lets imports repair missing ORS/SOF/gender/splits without
    increasing row counts.
    """
    payload: Dict[str, Any] = {}
    old_url = clean_str(existing.get("athlete_url"))
    new_url = canonical_athlete_url(incoming.get("athlete_url"))
    if new_url and old_url != new_url:
        payload["athlete_url"] = new_url

    text_cols = ["athlete_name", "race_url", "race_type", "distance", "place", "status"]
    numeric_cols = ["sof", "ors", "swim_seconds", "bike_seconds", "run_seconds"]

    for col in text_cols:
        v = incoming.get(col)
        if row_has_value(v) and clean_str(existing.get(col)) != clean_str(v):
            # Do not replace a useful existing value with generic/blank-like values.
            if not row_has_value(existing.get(col)) or col in ["status", "place", "race_type", "distance"]:
                payload[col] = v

    incoming_gender = normalize_gender(incoming.get("gender"))
    existing_gender = normalize_gender(existing.get("gender"))
    if incoming_gender in ["Men", "Women"] and existing_gender != incoming_gender:
        payload["gender"] = incoming_gender

    for col in numeric_cols:
        v = incoming.get(col)
        if row_has_value(v):
            existing_missing = not row_has_value(existing.get(col))
            should_replace = existing_missing
            # Clean API refreshes should be allowed to repair corrupted split seconds
            # from old spreadsheet imports, for example 0:32 saved as 32 seconds.
            if col in ["swim_seconds", "bike_seconds", "run_seconds"]:
                discipline = col.replace("_seconds", "")
                incoming_valid = validate_split_seconds(parse_int(v), discipline, incoming.get("race_type") or existing.get("race_type"))
                existing_valid = validate_split_seconds(parse_int(existing.get(col)), discipline, existing.get("race_type") or incoming.get("race_type"))
                if incoming_valid is not None and existing_valid is None:
                    should_replace = True
            if should_replace:
                payload[col] = v

    # Keep raw payload if the existing row does not have it; do not constantly rewrite JSON.
    if row_has_value(incoming.get("raw")) and not row_has_value(existing.get("raw")):
        payload["raw"] = incoming.get("raw")
    return payload


def update_existing_result_row(table_name: str, existing: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    try:
        row_id = existing.get("id")
        if row_id is not None and not (isinstance(row_id, float) and math.isnan(row_id)):
            supabase.table(table_name).update(payload).eq("id", int(row_id)).execute()
        else:
            supabase.table(table_name).update(payload) \
                .eq("athlete_url", existing.get("athlete_url")) \
                .eq("race_date", iso_date(existing.get("race_date"))) \
                .eq("race_name", existing.get("race_name")) \
                .eq("race_type", existing.get("race_type")) \
                .execute()
        return True
    except Exception:
        return False


def merge_result_rows(table_name: str, rows: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """Merge result imports instead of appending duplicates.

    Returns: inserted, skipped_duplicate, updated_existing.
    """
    rows = dedupe_result_rows(rows)
    if not rows:
        return 0, 0, 0

    existing_map = build_existing_result_map(table_name)
    to_insert: List[Dict[str, Any]] = []
    skipped = 0
    updated = 0
    for row in rows:
        row = dict(row)
        row["athlete_url"] = canonical_athlete_url(row.get("athlete_url")) or row.get("athlete_url")
        key = result_import_key(row)
        existing = existing_map.get(key)
        if existing:
            payload = result_update_payload(existing, row)
            if update_existing_result_row(table_name, existing, payload):
                updated += 1
            else:
                skipped += 1
            # Pretend the existing row now has the better fields for any later duplicate in this same upload.
            existing_map[key] = {**existing, **payload}
            continue
        to_insert.append(row)
        existing_map[key] = row

    if to_insert:
        insert_chunks(table_name, to_insert)
    return len(to_insert), skipped, updated


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
    override_map = load_gender_override_map()
    # Manual CSV rows become locked overrides. Inferred rows never override a locked manual value.
    manual_work = work[work.get("Sources", pd.Series(index=work.index, dtype=object)).astype(str).str.contains("Manual override", case=False, na=False)].copy()
    if not manual_work.empty:
        upsert_gender_override_rows([
            {
                "athlete_url": canonical_athlete_url(r.get("Athlete URL")),
                "athlete_name": clean_str(r.get("Athlete")),
                "gender": normalize_gender(r.get("Suggested Gender")),
            }
            for _, r in manual_work.iterrows()
        ])
        override_map = load_gender_override_map()

    applied = 0
    progress = st.progress(0, text="Applying gender updates...") if len(work) else None
    for idx, (_, r) in enumerate(work.iterrows(), start=1):
        g = normalize_gender(r.get("Suggested Gender"))
        url = canonical_athlete_url(r.get("Athlete URL"))
        name = clean_str(r.get("Athlete"))
        if not g or (not url and not name):
            continue
        locked_gender = normalize_gender((override_map.get(url) or {}).get("gender")) if url else None
        if locked_gender in ["Men", "Women"]:
            g = locked_gender
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

    Source athlete URLs can arrive as /athletes/slug, /en/athletes/slug, http vs https,
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
    """Return a small set of allowed URL variants for the same athlete.

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
    """Rate-limited, missing-only gender backfill from permissioned profile pages."""
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

    Imported rows sometimes store SOF on some athletes' rows for the same race but leave
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
@st.cache_data(ttl=900, show_spinner="⚡ Syncing and normalizing Supabase data...")
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
    override_map = load_gender_override_map()
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
    # Manual overrides are the final source of truth. They win over athlete rows,
    # result rows, and start-list imports.
    for url, rec in override_map.items():
        g = normalize_gender(rec.get("gender"))
        if g in ["Men", "Women"]:
            gender_map[url] = g
            nm = clean_str(rec.get("athlete_name"))
            if nm:
                name_gender_map[nm.lower()] = g

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

        # SOF is race-level evidence. Imported CSV rows can have SOF blank
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


def is_premium_split_evidence(row: pd.Series, discipline: str, strong_sof_threshold: float = STRONG_SOF_THRESHOLD) -> bool:
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


def is_strong_split_evidence(row: pd.Series, discipline: str, strong_sof_threshold: float = STRONG_SOF_THRESHOLD) -> bool:
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


def evidence_quality_label(row: pd.Series, discipline: str, strong_sof_threshold: float = STRONG_SOF_THRESHOLD) -> str:
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




# ============================================================
# OpenRank-aligned scoring overrides
# ============================================================
def openrank_tier_for_row(row: pd.Series, discipline: Optional[str] = None) -> str:
    """Map our imported race row to the OpenRank-style tier model.

    This mirrors the public OpenRank idea: race quality is not just branding;
    championship status, race family, and SOF determine how much a result can
    move a ranking. The exact source tier labels are not always present in our CSV,
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

    OpenRank uses a race baseline score and then deducts/adds 6 points per
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
    Athlete ranking uses up to the top configured split scores in the rolling 52-week window.
    Missing evidence is not padded with zero; confidence/evidence_count carries the sample-size warning.
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
    """Return the average of the available top scores, without padding missing slots.

    `divisor` is now a max-count, not a forced denominator. If an athlete has
    only 3 eligible races, we average those 3 and carry the lower sample size in
    Evidence Count / Confidence instead of inserting 0.0 placeholder races.
    """
    vals = [float(v) for v in values if safe_float(v) is not None and float(v) > 0]
    vals = sorted(vals, reverse=True)[:divisor]
    if not vals:
        return 0.0, []
    return sum(vals) / len(vals), vals


# Override previous split scoring with OpenRank-aligned split scoring.



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



def dynamic_table_height(df: pd.DataFrame, requested: Optional[int] = None, row_height: int = 34, header_height: int = 42, max_height: int = 650) -> Optional[int]:
    """Choose a compact dataframe height so small result sets do not show a big empty grid."""
    if df is None or df.empty:
        return None
    rows = int(len(df))
    calc = min(max_height, header_height + max(rows, 1) * row_height)
    if isinstance(requested, int) and requested > 0:
        return min(requested, calc)
    if rows <= 15:
        return calc
    return requested

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
    compact_height = dynamic_table_height(show, height)
    if isinstance(compact_height, int) and compact_height > 0:
        kwargs["height"] = compact_height

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
    compact_height = dynamic_table_height(show, height)
    if isinstance(compact_height, int) and compact_height > 0:
        kwargs["height"] = compact_height

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
# Model cache helpers
# ============================================================
MODEL_CACHE_VERSION = "score_engine_v3_fast_clear"
TOP_SCORES_USED = 5
LOW_SAMPLE_WARNING_THRESHOLD = 5
STRONG_SOF_THRESHOLD = 65.0
RANKING_FAMILIES = ["Long Course / 70.3 + T100", "Short Course / WTCS", "Full IRONMAN", "All"]
RANKING_VIEW_LABELS = ["🏆 Overall", "🏊 Swim", "🚴 Bike", "🏃 Run"]


def cache_safe_rows(df: pd.DataFrame, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Convert a dataframe to JSON-safe rows for storage in model_cache.rows."""
    if df is None or df.empty:
        return []
    out = df.copy()
    if isinstance(limit, int) and limit > 0:
        out = out.head(limit).copy()
    return [json_safe_row(row) for _, row in out.iterrows()]


def cache_rows_to_df(rows: Any) -> pd.DataFrame:
    if rows is None:
        return pd.DataFrame()
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except Exception:
            return pd.DataFrame()
    if isinstance(rows, dict):
        rows = rows.get("rows", [])
    if not isinstance(rows, list):
        return pd.DataFrame()
    return pd.DataFrame(rows)






def ranking_view_to_kind(view_label: str) -> str:
    return {
        "🏆 Overall": "overall",
        "🏊 Swim": "swim",
        "🚴 Bike": "bike",
        "🏃 Run": "run",
    }.get(view_label, str(view_label).lower().strip())




def cached_section(cached_df: pd.DataFrame, section: str) -> pd.DataFrame:
    """Return rows for a cached race-prediction section.

    Older cache rows may have a different section-column name. This keeps a
    saved cache from displaying empty tables just because the section marker was
    named slightly differently in a previous version.
    """
    if cached_df is None or cached_df.empty:
        return pd.DataFrame()
    for col in ["_section", "section", "Section", "cache_section"]:
        if col in cached_df.columns:
            vals = cached_df[col].astype(str).str.strip().str.lower()
            return cached_df[vals == str(section).strip().lower()].copy()
    return pd.DataFrame()





# ============================================================
# Race lookup and start-list management helpers
# ============================================================
def _race_group_key(row: pd.Series) -> str:
    """Stable display key for a race/date/gender/source group."""
    race_name = clean_str(row.get("race_name")) or "Unknown Race"
    race_date = format_date(row.get("race_date"))
    gender = normalize_gender(row.get("gender")) or clean_str(row.get("gender")) or "Unknown"
    race_type = clean_str(row.get("race_type")) or clean_str(row.get("distance")) or "Unknown"
    source = clean_str(row.get("data_source")) or clean_str(row.get("source")) or "results"
    return f"{race_date} · {gender} · {race_name} · {race_type} · {source}"


def race_lookup_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Build a searchable race index from imported athlete/race-field results."""
    if results is None or results.empty:
        return pd.DataFrame()
    df = results.copy()
    for col in ["race_name", "race_date", "gender", "race_type", "distance", "data_source"]:
        if col not in df.columns:
            df[col] = None
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")
    df["athlete_key"] = df.apply(
        lambda r: canonical_athlete_url(r.get("athlete_url")) or (clean_str(r.get("athlete_name")) or "").lower(),
        axis=1,
    )
    group_cols = ["race_name", "race_date", "gender", "race_type", "distance", "data_source"]
    grouped = df.groupby(group_cols, dropna=False)
    rows = []
    for key, g in grouped:
        race_name, race_date, gender, race_type, distance, source = key
        sof_vals = pd.to_numeric(g.get("sof", pd.Series(dtype=float)), errors="coerce")
        ors_vals = pd.to_numeric(g.get("ors", pd.Series(dtype=float)), errors="coerce")
        rows.append({
            "Race Date": race_date,
            "Race": clean_str(race_name) or "Unknown Race",
            "Gender": normalize_gender(gender) or clean_str(gender) or "Unknown",
            "Race Type": clean_str(race_type) or clean_str(distance) or "Unknown",
            "Source": clean_str(source) or "results",
            "Athletes": int(g["athlete_key"].replace("", np.nan).dropna().nunique()),
            "Rows": int(len(g)),
            "SOF": None if sof_vals.dropna().empty else round(float(sof_vals.dropna().median()), 2),
            "Max ORS": None if ors_vals.dropna().empty else round(float(ors_vals.dropna().max()), 2),
            "_race_name": clean_str(race_name) or "Unknown Race",
            "_race_date": race_date,
            "_gender": normalize_gender(gender) or clean_str(gender) or "Unknown",
            "_race_type": clean_str(race_type) or clean_str(distance) or "Unknown",
            "_source": clean_str(source) or "results",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_select_key"] = out.apply(lambda r: f"{format_date(r['_race_date'])} · {r['_gender']} · {r['_race_name']} · {r['_race_type']} · {r['_source']}", axis=1)
    return out.sort_values(["Race Date", "Race", "Gender"], ascending=[False, True, True]).reset_index(drop=True)


def filter_race_lookup(summary: pd.DataFrame, search: str, gender: str, race_family: str, source_filter: str) -> pd.DataFrame:
    if summary is None or summary.empty:
        return pd.DataFrame()
    out = summary.copy()
    q = (search or "").strip().lower()
    if q:
        hay = (
            out["Race"].fillna("").astype(str) + " " +
            out["Race Type"].fillna("").astype(str) + " " +
            out["Gender"].fillna("").astype(str) + " " +
            out["Source"].fillna("").astype(str)
        ).str.lower()
        out = out[hay.str.contains(re.escape(q), na=False)]
    if gender and gender != "All":
        out = out[out["Gender"].eq(gender)]
    if race_family and race_family != "All":
        # Reuse the ranking family mask against a dataframe with race_type/race_name.
        temp = pd.DataFrame({"race_name": out["Race"], "race_type": out["Race Type"]})
        mask = ranking_scope_mask(temp, race_family)
        out = out[mask.to_numpy()]
    if source_filter and source_filter != "All":
        out = out[out["Source"].eq(source_filter)]
    return out.reset_index(drop=True)


def race_participants(results: pd.DataFrame, selected: pd.Series) -> pd.DataFrame:
    if results is None or results.empty or selected is None:
        return pd.DataFrame()
    df = results.copy()
    for col in ["race_name", "race_date", "gender", "race_type", "distance", "data_source"]:
        if col not in df.columns:
            df[col] = None
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")
    selected_date = pd.to_datetime(selected.get("_race_date"), errors="coerce")
    mask = df["race_name"].fillna("Unknown Race").astype(str).eq(str(selected.get("_race_name")))
    if not pd.isna(selected_date):
        mask &= df["race_date"].dt.date.eq(selected_date.date())
    selected_gender = clean_str(selected.get("_gender"))
    if selected_gender and selected_gender != "Unknown":
        mask &= df["gender"].map(lambda x: normalize_gender(x) or clean_str(x) or "Unknown").eq(selected_gender)
    selected_type = clean_str(selected.get("_race_type"))
    if selected_type and selected_type != "Unknown":
        type_ser = df.apply(lambda r: clean_str(r.get("race_type")) or clean_str(r.get("distance")) or "Unknown", axis=1)
        mask &= type_ser.eq(selected_type)
    selected_source = clean_str(selected.get("_source"))
    if selected_source and selected_source != "results":
        mask &= df["data_source"].fillna("results").astype(str).eq(selected_source)
    out = df[mask].copy()
    if out.empty:
        return out
    out["Athlete"] = out.get("athlete_name", pd.Series(index=out.index, dtype=object))
    out["Gender"] = out.get("gender", pd.Series(index=out.index, dtype=object))
    out["Race Date"] = out.get("race_date", pd.Series(index=out.index, dtype=object))
    out["Race Type"] = out.apply(lambda r: clean_str(r.get("race_type")) or clean_str(r.get("distance")) or "", axis=1)
    out["Place"] = out.get("place", pd.Series(index=out.index, dtype=object))
    out["ORS"] = out.get("ors", pd.Series(index=out.index, dtype=object))
    out["SOF"] = out.get("sof", pd.Series(index=out.index, dtype=object))
    out["Swim"] = out.get("swim_seconds", pd.Series(index=out.index, dtype=object))
    out["Bike"] = out.get("bike_seconds", pd.Series(index=out.index, dtype=object))
    out["Run"] = out.get("run_seconds", pd.Series(index=out.index, dtype=object))
    out["Status"] = out.get("status", pd.Series(index=out.index, dtype=object))
    out["Athlete URL"] = out.get("athlete_url", pd.Series(index=out.index, dtype=object))
    out["Source"] = out.get("data_source", pd.Series(index=out.index, dtype=object))
    if "place_num" not in out.columns:
        out["place_num"] = out["Place"].map(parse_place_number)
    return out.sort_values(["place_num", "ORS", "Athlete"], ascending=[True, False, True], na_position="last").reset_index(drop=True)


def start_list_group_summary(starts: pd.DataFrame) -> pd.DataFrame:
    """Return one row per imported start-list race/date/gender group."""
    if starts is None or starts.empty:
        return pd.DataFrame()
    df = starts.copy()
    for col in ["race_name", "race_date", "gender", "athlete_url", "athlete_name", "open_rank"]:
        if col not in df.columns:
            df[col] = None
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")
    df["athlete_key"] = df.apply(lambda r: canonical_athlete_url(r.get("athlete_url")) or (clean_str(r.get("athlete_name")) or "").lower(), axis=1)
    rows = []
    for (race_name, race_date, gender), g in df.groupby(["race_name", "race_date", "gender"], dropna=False):
        athletes_count = int(g["athlete_key"].replace("", np.nan).dropna().nunique())
        duplicate_rows = int(len(g) - athletes_count)
        rows.append({
            "Race Date": race_date,
            "Race": clean_str(race_name) or "Unknown Race",
            "Gender": normalize_gender(gender) or clean_str(gender) or "Unknown",
            "Athletes": athletes_count,
            "Rows": int(len(g)),
            "Duplicate Rows": max(duplicate_rows, 0),
            "_race_name": clean_str(race_name) or "Unknown Race",
            "_race_date": race_date,
            "_gender": normalize_gender(gender) or clean_str(gender) or "Unknown",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_select_key"] = out.apply(lambda r: f"{format_date(r['_race_date'])} · {r['_gender']} · {r['_race_name']} · {int(r['Athletes'])} athletes", axis=1)
    return out.sort_values(["Race Date", "Race", "Gender"], ascending=[False, True, True]).reset_index(drop=True)


def start_list_rows_for_group(starts: pd.DataFrame, race_name: str, race_date: Any, gender: str) -> pd.DataFrame:
    if starts is None or starts.empty:
        return pd.DataFrame()
    df = starts.copy()
    df["race_date"] = pd.to_datetime(df.get("race_date"), errors="coerce")
    selected_date = pd.to_datetime(race_date, errors="coerce")
    mask = df.get("race_name", pd.Series(index=df.index, dtype=object)).fillna("Unknown Race").astype(str).eq(str(race_name))
    if not pd.isna(selected_date):
        mask &= df["race_date"].dt.date.eq(selected_date.date())
    if gender and gender != "Unknown":
        mask &= df.get("gender", pd.Series(index=df.index, dtype=object)).map(lambda x: normalize_gender(x) or clean_str(x) or "Unknown").eq(gender)
    out = df[mask].copy()
    if out.empty:
        return out
    out["Athlete"] = out.get("athlete_name", pd.Series(index=out.index, dtype=object))
    out["Athlete URL"] = out.get("athlete_url", pd.Series(index=out.index, dtype=object)).map(canonical_athlete_url)
    out["OpenRank"] = out.get("open_rank", pd.Series(index=out.index, dtype=object))
    out["Gender"] = out.get("gender", pd.Series(index=out.index, dtype=object))
    out["Race Date"] = out.get("race_date", pd.Series(index=out.index, dtype=object))
    out["Race"] = out.get("race_name", pd.Series(index=out.index, dtype=object))
    return out.sort_values(["OpenRank", "Athlete"], ascending=[True, True], na_position="last").reset_index(drop=True)


def delete_start_list_row(row: pd.Series) -> bool:
    """Delete one start-list row, preferring its database id when present."""
    try:
        row_id = row.get("id")
        if row_id is not None and not (isinstance(row_id, float) and math.isnan(row_id)):
            supabase.table("start_lists").delete().eq("id", int(row_id)).execute()
            return True
    except Exception:
        pass
    race_name = clean_str(row.get("race_name") or row.get("Race"))
    race_date = format_date(row.get("race_date") or row.get("Race Date"))
    gender = normalize_gender(row.get("gender") or row.get("Gender"))
    athlete_url = canonical_athlete_url(row.get("athlete_url") or row.get("Athlete URL"))
    athlete_name = clean_str(row.get("athlete_name") or row.get("Athlete"))
    try:
        q = supabase.table("start_lists").delete().eq("race_name", race_name).eq("race_date", race_date).eq("gender", gender)
        if athlete_url:
            q = q.eq("athlete_url", athlete_url)
        elif athlete_name:
            q = q.eq("athlete_name", athlete_name)
        else:
            return False
        q.execute()
        return True
    except Exception:
        return False


def add_start_list_athlete(race_name: str, race_date: Any, gender: str, athlete_name: str, athlete_url: str, open_rank: Any) -> Tuple[bool, str]:
    """Add one athlete to a start list if that athlete is not already in it."""
    race_name = clean_str(race_name)
    race_date_str = format_date(race_date)
    gender = normalize_gender(gender) or clean_str(gender)
    athlete_name = clean_str(athlete_name)
    athlete_url = canonical_athlete_url(athlete_url)
    if not race_name or not race_date_str or not gender:
        return False, "Missing race, date, or gender."
    if not athlete_name and not athlete_url:
        return False, "Enter an athlete name or athlete URL."
    row = {
        "race_name": race_name,
        "race_date": race_date_str,
        "gender": gender,
        "athlete_url": athlete_url,
        "athlete_name": athlete_name,
        "open_rank": parse_int(open_rank),
    }
    rows, athlete_inserted, athlete_updated, propagated = sync_athlete_master_import(
        [row],
        [{"athlete_url": athlete_url, "athlete_name": athlete_name, "gender": gender}],
        default_gender=gender,
    )
    row = rows[0] if rows else row
    inserted, skipped = merge_start_list_rows([row])
    clear_cache()
    if inserted:
        return True, "Athlete added to start list."
    return False, "That athlete already appears on this start list."



def normalize_start_list_upload_for_group(upload_df: pd.DataFrame, race_name: str, race_date: Any, gender: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Normalize an uploaded start-list CSV and fill blank race/date/gender from selected group."""
    rows, athlete_rows = normalize_start_lists(upload_df)
    race_name = clean_str(race_name)
    race_date_str = format_date(race_date)
    gender = normalize_gender(gender) or clean_str(gender)
    fixed = []
    for row in rows:
        row = dict(row)
        if not clean_str(row.get("race_name")) or clean_str(row.get("race_name")) == "Unknown Race":
            row["race_name"] = race_name
        if not clean_str(row.get("race_date")):
            row["race_date"] = race_date_str
        if not normalize_gender(row.get("gender")):
            row["gender"] = gender
        row["athlete_url"] = canonical_athlete_url(row.get("athlete_url"))
        fixed.append(row)
    fixed = dedupe_start_list_rows(fixed)
    # Make sure athlete upsert rows inherit the selected gender when omitted.
    fixed_athletes = []
    for row in fixed:
        fixed_athletes.append({
            "athlete_url": row.get("athlete_url"),
            "athlete_name": row.get("athlete_name"),
            "gender": row.get("gender"),
        })
    return fixed, fixed_athletes


def render_import_overview() -> None:
    st.markdown(
        """
        <div class="tri-import-grid">
          <div class="tri-import-card"><div class="kicker">Results</div><div class="title">Race history</div><div class="body">Import athlete result rows or full race-field result rows. These feed scorecards and evidence.</div></div>
          <div class="tri-import-card"><div class="kicker">Start lists</div><div class="title">Changing race rosters</div><div class="body">Replace a selected start list, merge new athletes only, or import start lists with race/date/gender columns.</div></div>
          <div class="tri-import-card"><div class="kicker">Cleanup</div><div class="title">Gender overrides</div><div class="body">Fix Men/Women from one CSV by athlete name or athlete URL, then propagate to linked rows.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_csv_preview(df: pd.DataFrame, title: str = "CSV preview", limit: int = 20) -> None:
    st.subheader(title)
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows detected", f"{len(df):,}")
    c2.metric("Columns", f"{len(df.columns):,}")
    c3.metric("Blank cells", f"{int(df.isna().sum().sum()):,}")
    st.dataframe(df.head(limit), width="stretch")


def import_results_csv(df: pd.DataFrame, table_choice: str, replace: bool) -> None:
    if table_choice == "Athlete Results":
        rows, athlete_rows = normalize_athlete_results(df)
        rows, athlete_inserted, athlete_updated, propagated = sync_athlete_master_import(rows, athlete_rows)
        rows = dedupe_result_rows(rows)
        before_count = count_rows("athlete_results")
        if replace:
            delete_all("athlete_results")
            insert_chunks("athlete_results", rows)
            inserted, skipped, updated_existing = len(rows), 0, 0
        else:
            inserted, skipped, updated_existing = merge_result_rows("athlete_results", rows)
        clear_cache()
        after_count = count_rows("athlete_results")
        st.success(
            f"Processed {len(rows):,} athlete result rows: {inserted:,} inserted, "
            f"{updated_existing:,} existing rows updated, {skipped:,} duplicates skipped. "
            f"Athlete master: {athlete_inserted:,} new, {athlete_updated:,} updated. "
            f"Gender propagated for {propagated:,} athletes."
        )
        st.info(f"Supabase athlete_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")
    elif table_choice == "Race Field Results":
        rows, athlete_rows = normalize_race_field_results(df)
        rows, athlete_inserted, athlete_updated, propagated = sync_athlete_master_import(rows, athlete_rows)
        rows = dedupe_result_rows(rows)
        before_count = count_rows("race_field_results")
        if replace:
            delete_all("race_field_results")
            insert_chunks("race_field_results", rows)
            inserted, skipped, updated_existing = len(rows), 0, 0
        else:
            inserted, skipped, updated_existing = merge_result_rows("race_field_results", rows)
        clear_cache()
        after_count = count_rows("race_field_results")
        st.success(
            f"Processed {len(rows):,} race-field result rows: {inserted:,} inserted, "
            f"{updated_existing:,} existing rows updated, {skipped:,} duplicates skipped. "
            f"Athlete master: {athlete_inserted:,} new, {athlete_updated:,} updated. "
            f"Gender propagated for {propagated:,} athletes."
        )
        st.info(f"Supabase race_field_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")


def import_general_start_list_csv(df: pd.DataFrame, replace_matching_groups: bool) -> None:
    rows, athlete_rows = normalize_start_lists(df)
    rows = dedupe_start_list_rows(rows)
    default_gender = None
    start_genders = {normalize_gender(r.get("gender")) for r in rows if normalize_gender(r.get("gender")) in ["Men", "Women"]}
    if len(start_genders) == 1:
        default_gender = next(iter(start_genders))
    rows, athlete_inserted, athlete_updated, propagated = sync_athlete_master_import(rows, athlete_rows, default_gender=default_gender)
    rows = dedupe_start_list_rows(rows)
    inserted = len(rows)
    skipped = 0
    replaced_groups = 0
    if replace_matching_groups:
        replaced_groups = delete_matching_start_lists(rows)
        insert_chunks("start_lists", rows)
    else:
        inserted, skipped = merge_start_list_rows(rows)
    clear_cache()
    st.success(f"Imported {inserted:,} new start-list rows and skipped {skipped:,} duplicate rows.")
    if replace_matching_groups:
        st.info(f"Replace mode deleted existing rows for {replaced_groups:,} matching race/date/gender group(s), not the entire start_lists table.")
    st.info(f"Athlete master: {athlete_inserted:,} new, {athlete_updated:,} updated. Auto-propagated gender for {propagated:,} athletes from this start list import. Manual gender locks are preserved.")


def render_manual_gender_override_import(raw_athletes: pd.DataFrame, key_prefix: str = "manual_gender") -> None:
    st.caption("Upload athlete_url + gender, or just athlete_name + gender. Name-only rows are applied only when the name matches exactly one athlete in the master athletes table.")
    st.code("athlete_name,gender\nTaylor Knibb,Women\nHayden Wilde,Men", language="csv")
    override_map = load_gender_override_map()
    if override_map:
        st.caption(f"Manual gender locks active: {len(override_map):,}. These override start-list and result-row gender during imports and scoring.")
    else:
        st.caption("No manual gender locks saved yet.")
    override_file = st.file_uploader("Manual gender CSV", type=["csv"], key=f"{key_prefix}_csv")
    if override_file is None:
        return

    manual = read_uploaded_csv(override_file)
    render_csv_preview(manual, "Manual gender CSV preview", limit=12)

    athlete_name_buckets: Dict[str, List[Dict[str, Any]]] = {}
    if raw_athletes is not None and not raw_athletes.empty:
        for _, ar in raw_athletes.iterrows():
            nm = clean_str(ar.get("athlete_name"))
            au = canonical_athlete_url(ar.get("athlete_url"))
            if nm:
                athlete_name_buckets.setdefault(nm.lower(), []).append({
                    "athlete_name": nm,
                    "athlete_url": au,
                    "current_gender": normalize_gender(ar.get("gender")),
                })

    manual_rows = []
    skipped_rows = []
    for _, r in manual.iterrows():
        g = normalize_gender(first_col(r, ["gender", "Gender", "sex", "Sex", "category", "Category"]))
        url = canonical_athlete_url(first_col(r, ["athlete_url", "Athlete URL", "url", "URL", "profile", "Profile"]))
        name = clean_str(first_col(r, ["athlete_name", "Athlete Name", "Athlete", "Name", "athlete", "name"]))

        if g not in ["Men", "Women"]:
            skipped_rows.append({"Athlete": name, "Athlete URL": url, "Gender": first_col(r, ["gender", "Gender"]), "Reason": "Invalid/missing gender"})
            continue

        if not url and name:
            matches = athlete_name_buckets.get(name.lower(), [])
            unique_urls = sorted({canonical_athlete_url(m.get("athlete_url")) for m in matches if canonical_athlete_url(m.get("athlete_url"))})
            if len(unique_urls) == 1:
                url = unique_urls[0]
                name = matches[0].get("athlete_name") or name
            elif len(unique_urls) > 1:
                skipped_rows.append({"Athlete": name, "Athlete URL": ", ".join(unique_urls[:3]), "Gender": g, "Reason": "Name matches multiple athlete URLs — use athlete_url"})
                continue
            else:
                skipped_rows.append({"Athlete": name, "Athlete URL": "", "Gender": g, "Reason": "Name not found in athletes table — use athlete_url"})
                continue

        if url or name:
            manual_rows.append({
                "Athlete URL": url,
                "Athlete": name,
                "Suggested Gender": g,
                "Confidence": "High",
                "Conflict": "No",
                "Sources": "Manual override CSV",
                "Signal Count": 1,
            })
        else:
            skipped_rows.append({"Athlete": name, "Athlete URL": url, "Gender": g, "Reason": "Missing athlete_url and athlete_name"})

    manual_df = pd.DataFrame(manual_rows)
    skipped_df = pd.DataFrame(skipped_rows)
    c1, c2 = st.columns(2)
    c1.metric("Valid override rows", f"{len(manual_df):,}")
    c2.metric("Skipped rows", f"{len(skipped_df):,}")
    if not manual_df.empty:
        display_table(manual_df.head(250), ["Athlete", "Athlete URL", "Suggested Gender", "Sources"], height=300)
        if st.button("Apply manual gender overrides", type="primary", key=f"{key_prefix}_apply"):
            applied = apply_gender_updates(manual_df, include_medium=False)
            st.success(f"Applied and locked manual gender overrides for {applied:,} athletes. These will now win over future start-list/result imports.")
            st.info("Next: click Refresh database cache, then rebuild athlete scorecards.")
            st.rerun()
    if not skipped_df.empty:
        st.warning(f"Skipped {len(skipped_df):,} manual rows that were ambiguous or incomplete.")
        display_table(skipped_df.head(250), ["Athlete", "Athlete URL", "Gender", "Reason"], height=260)

# ============================================================
# UI
# ============================================================
apply_dashboard_theme()

NAV_GROUPS = [
    ("Main", [
        ("📊 Command Center", "Command Center"),
        ("🏆 Race Dashboard", "Race Dashboard"),
        ("🥇 Athlete Rankings", "Athlete Rankings"),
    ]),
    ("Explore", [
        ("🏁 Race Lookup", "Race Lookup"),
        ("📋 Start Lists", "Start Lists"),
        ("👤 Athletes", "Athletes"),
        ("🔎 Split Audit", "Split Audit"),
    ]),
    ("Data", [
        ("⚡ Model Cache", "Model Cache"),
        ("🧬 Gender Tools", "Gender Tools"),
        ("📥 Import CSVs", "Import CSVs"),
        ("🧹 Data Quality", "Data Quality"),
        ("🗄️ Database Viewer", "Database Viewer"),
        ("🔌 Connection", "Connection"),
    ]),
]
PAGE_OPTIONS = {label: page_name for _, items in NAV_GROUPS for label, page_name in items}

if "page_label" not in st.session_state or st.session_state["page_label"] not in PAGE_OPTIONS:
    st.session_state["page_label"] = "📊 Command Center"

# ============================================================
# Simplified scorecard predictor overrides
# ============================================================
# The predictor now works from durable athlete scorecards:
#   profile + athlete + view(overall/swim/bike/run) -> score + top evidence rows.
# A selected start list simply joins to those scorecards and displays them.
MODEL_CACHE_VERSION = "score_engine_v3_fast_clear"
TOP_SCORES_USED = 5
LOW_SAMPLE_WARNING_THRESHOLD = 5
STRONG_SOF_THRESHOLD = 65.0
# Full-distance athletes race less often, so Full IRONMAN scorecards use a longer
# evidence window than 70.3/T100 or short course. Top scores used still means
# "up to 5 best eligible scores"; missing slots are never padded with 0.0.
DEFAULT_SCORECARD_LOOKBACK_DAYS = 365
FULL_IM_SCORECARD_LOOKBACK_DAYS = 730
ALL_PROFILE_SCORECARD_LOOKBACK_DAYS = 730
RANKING_FAMILIES = ["Long Course / 70.3 + T100", "Short Course / WTCS", "Full IRONMAN", "All"]


def scorecard_lookback_days(profile: str) -> int:
    profile = clean_str(profile) or ""
    if profile == "Full IRONMAN":
        return FULL_IM_SCORECARD_LOOKBACK_DAYS
    if profile == "All":
        return ALL_PROFILE_SCORECARD_LOOKBACK_DAYS
    return DEFAULT_SCORECARD_LOOKBACK_DAYS


def scorecard_profile_from_race(race_name: Any, race_type: Any = None, distance: Any = None) -> str:
    """Map a selected race to the scorecard profile that should feed predictions."""
    rt = normalize_race_type(race_name, race_type, distance)
    txt = " ".join([clean_str(race_name) or "", clean_str(race_type) or "", clean_str(distance) or ""]).lower()
    if rt in {"WTCS", "World Triathlon Cup", "Continental Cup", "Olympic", "Sprint"}:
        return "Short Course / WTCS"
    if any(x in txt for x in ["wtcs", "world triathlon", "olympic", "sprint", "triathlon cup"]):
        return "Short Course / WTCS"
    if rt == "Full" or ("ironman" in txt and "70.3" not in txt and "t100" not in txt and "pto" not in txt):
        return "Full IRONMAN"
    # Treat 70.3 and T100 as the same long-course race-speed problem.
    return "Long Course / 70.3 + T100"


def prediction_scope_from_race(race_name: Any, race_type: Any = None, distance: Any = None) -> str:
    return scorecard_profile_from_race(race_name, race_type, distance)


def ranking_scope_mask(df: pd.DataFrame, scope: str) -> pd.Series:
    """Return a boolean mask for the selected scorecard profile."""
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    rt = df.get("race_type", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    race = df.get("race_name", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    dist = df.get("distance", pd.Series([None] * len(df), index=df.index)).map(lambda x: (clean_str(x) or "").lower())
    txt = (rt + " " + race + " " + dist)

    if scope == "Long Course / 70.3 + T100":
        # One long-course profile for 70.3 / middle / Challenge / T100 / PTO.
        # Exclude full IM and short-course development rows.
        long_middle = txt.str.contains("70.3|middle|challenge|t100|pto", regex=True, na=False)
        full_only = (txt.str.contains("full|140.6", regex=True, na=False) | (txt.str.contains("ironman", na=False) & ~txt.str.contains("70.3", na=False)))
        return long_middle & ~full_only
    if scope == "Full IRONMAN":
        return txt.str.contains("full|140.6", regex=True, na=False) | ((txt.str.contains("ironman", na=False)) & ~txt.str.contains("70.3", na=False))
    if scope == "Short Course / WTCS":
        return short_course_predictor_mask(df)
    if scope == "All":
        return pd.Series([True] * len(df), index=df.index)
    # Backward-compatible aliases if an older cache/control value appears.
    if scope == "IRONMAN 70.3 / Middle":
        return txt.str.contains("70.3|middle|challenge", regex=True, na=False) & ~txt.str.contains("t100|pto", regex=True, na=False)
    if scope == "T100 / PTO":
        return txt.str.contains("t100|pto", regex=True, na=False)
    return pd.Series([True] * len(df), index=df.index)


def apply_prediction_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    return df[ranking_scope_mask(df, scope)].copy()


def _overall_evidence_rows(gg: pd.DataFrame, top_n: int) -> List[Dict[str, Any]]:
    if gg is None or gg.empty:
        return []
    evidence = gg.sort_values("ors_for_rank", ascending=False).head(top_n).copy()
    rows = []
    for _, r in evidence.iterrows():
        rows.append({
            "Date": format_date(r.get("race_date")),
            "Race": clean_str(r.get("race_name")),
            "Race Type": clean_str(r.get("race_type")),
            "Place": clean_str(r.get("place")),
            "Status": clean_str(r.get("status")),
            "ORS": None if safe_float(r.get("ors_for_rank")) is None else round(float(r.get("ors_for_rank")), 2),
            "SOF": None if safe_float(r.get("sof")) is None else round(float(r.get("sof")), 2),
        })
    return rows


def _split_evidence_rows(g: pd.DataFrame, top_n: int) -> List[Dict[str, Any]]:
    if g is None or g.empty:
        return []
    evidence = g.sort_values(["split_openrank_score", "race_date"], ascending=[False, False]).head(top_n).copy()
    rows = []
    for _, r in evidence.iterrows():
        rows.append({
            "Date": format_date(r.get("race_date")),
            "Race": clean_str(r.get("race_name")),
            "Race Type": clean_str(r.get("race_type")),
            "Quality": clean_str(r.get("quality_tier")),
            "Place": clean_str(r.get("place")),
            "SOF": None if safe_float(r.get("sof")) is None else round(float(r.get("sof")), 2),
            "Sample": parse_int(r.get("sample_size")) or parse_int(r.get("field_size")),
            "Split": clean_str(r.get("split")),
            "Split Rank": clean_str(r.get("rank_display")) or clean_str(r.get("sample_rank_display")),
            "% Behind Fastest": None if safe_float(r.get("pct_behind_fastest")) is None else round(float(r.get("pct_behind_fastest")), 2),
            "Evidence Score": None if safe_float(r.get("split_openrank_score")) is None else round(float(r.get("split_openrank_score")), 2),
        })
    return rows


# Simple overall score: average the available top X ORS rows inside trailing 52 weeks; no zero padding.
def score_overall(
    results: pd.DataFrame,
    start_athletes: pd.DataFrame,
    overrides: pd.DataFrame,
    target_date: pd.Timestamp,
    target_year: int,
    top_n: int,
    lookback_days: int = DEFAULT_SCORECARD_LOOKBACK_DAYS,
) -> pd.DataFrame:
    if results is None or results.empty or start_athletes is None or start_athletes.empty:
        return pd.DataFrame()
    start_urls = set(start_athletes.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).tolist())
    start_names = set(start_athletes.get("athlete_name", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())
    df = results.copy()
    window_start = pd.to_datetime(target_date) - pd.Timedelta(days=int(lookback_days or DEFAULT_SCORECARD_LOOKBACK_DAYS))
    df = df[(df["race_date"].notna()) & (df["race_date"] >= window_start) & (df["race_date"] <= target_date) & (~df["bad_status"])]
    df = df[(df["athlete_url"].isin(start_urls)) | (df["athlete_name"].fillna("").str.lower().isin(start_names))]
    df = df[df["ors"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        scored_rows = []
        for _, r in g.sort_values("race_date", ascending=False).iterrows():
            excluded, mult, reason = match_override(r, overrides, "Overall")
            if excluded:
                continue
            rr = r.copy()
            rr["ors_for_rank"] = (safe_float(r.get("ors")) or 0.0) * mult
            rr["override_reason"] = reason
            scored_rows.append(rr)
        if not scored_rows:
            continue
        gg = pd.DataFrame(scored_rows).sort_values("race_date", ascending=False)
        rank_score_val, best_scores = best4_openrank_average(gg["ors_for_rank"].tolist(), top_n)
        current_year = gg[gg["race_date"].dt.year == target_year].copy()
        current_year_values = pd.to_numeric(current_year.get("ors_for_rank", pd.Series(dtype=float)), errors="coerce").dropna().tolist() if not current_year.empty else []
        current_year_score = float(np.mean(sorted(current_year_values, reverse=True)[:top_n])) if current_year_values else None
        strong = gg[(gg["sof"].fillna(0) >= STRONG_SOF_THRESHOLD) | (gg["race_type"].isin(["T100", "WTCS"]))]
        strong_score = pd.to_numeric(strong.get("ors_for_rank", pd.Series(dtype=float)), errors="coerce").mean() if not strong.empty else 0
        name = g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else str(athlete_key)
        url = g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None
        last_row = gg.sort_values("race_date", ascending=False).head(1)
        rows.append({
            "Athlete": name,
            "Athlete URL": url,
            "Score": round(rank_score_val, 1),
            "OpenRank Score": round(rank_score_val, 1),
            "Best Scores Used": ", ".join([f"{x:.1f}" for x in best_scores]),
            "Score Evidence": _overall_evidence_rows(gg, top_n),
            "Recent Form ORS": round(rank_score_val, 1),
            "Current Year ORS": round(float(current_year_score), 1) if current_year_score is not None and not pd.isna(current_year_score) else None,
            "Current Year Races": int(len(current_year)),
            "Current Year Scored": int(len(current_year_values)),
            "Best Recent ORS": round(max(best_scores), 1) if best_scores else 0,
            "Strong Field ORS": round(float(strong_score), 1) if strong_score is not None and not pd.isna(strong_score) else 0,
            "Recent Races Used": len([x for x in best_scores if x > 0]),
            "Last Race": clean_str(last_row["race_name"].iloc[0]) if not last_row.empty else "",
            "Last Race Date": format_date(last_row["race_date"].iloc[0]) if not last_row.empty else "",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out


# Simple split score: average the available top X discipline-specific split scores inside trailing 52 weeks; no zero padding.
def score_splits_for_start_list(
    audit: pd.DataFrame,
    start_athletes: pd.DataFrame,
    target_date: pd.Timestamp,
    top_n: int,
    strong_sof_threshold: float,
    lookback_days: int = DEFAULT_SCORECARD_LOOKBACK_DAYS,
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
    window_start = pd.to_datetime(target_date) - pd.Timedelta(days=int(lookback_days or DEFAULT_SCORECARD_LOOKBACK_DAYS))
    df = df[(df["race_date"].notna()) & (df["race_date"] >= window_start) & (df["race_date"] <= target_date)].copy()
    if df.empty:
        return pd.DataFrame()

    df["premium_evidence"] = df.apply(lambda r: is_premium_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["strong_evidence"] = df.apply(lambda r: is_strong_split_evidence(r, discipline, strong_sof_threshold), axis=1)
    df["quality_tier"] = df.apply(lambda r: evidence_quality_label(r, discipline, strong_sof_threshold), axis=1)

    rows = []
    for athlete_key, g in df.groupby(df["athlete_url"].fillna(df["athlete_name"])):
        g = g.sort_values("race_date", ascending=False).copy()
        score_values = pd.to_numeric(g.get("split_openrank_score"), errors="coerce").dropna().tolist()
        openrank_score, best_scores = best4_openrank_average(score_values, top_n)
        premium = g[g["premium_evidence"].astype(bool)]
        strong = g[g["strong_evidence"].astype(bool)]
        evidence_count = len(g)
        final = float(openrank_score)
        if evidence_count <= 1:
            final = min(final, 45)
            confidence = "Low - 1 race"
        elif len(premium) >= 2:
            confidence = "High - repeated premium proof"
        elif len(premium) == 1:
            confidence = "Good - 1 premium race"
        elif len(strong) >= 2:
            confidence = "Good - repeated strong proof"
        elif len(strong) == 1:
            confidence = "Medium - 1 strong race"
        else:
            final = min(final, 28)
            confidence = "Low - weak evidence only"
        last_row = g.sort_values("race_date", ascending=False).head(1)
        best_row = g.sort_values(["split_openrank_score", "race_date"], ascending=[False, False]).head(1)
        rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None,
            "Score": round(final, 1),
            "OpenRank Split Score": round(openrank_score, 1),
            "Best Split Scores Used": ", ".join([f"{x:.1f}" for x in best_scores]),
            "Score Evidence": _split_evidence_rows(g, top_n),
            "Confidence": confidence,
            "Premium Evidence Count": int(len(premium)),
            "Strong Evidence Count": int(len(strong)),
            "Evidence Count": int(evidence_count),
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


def _startlist_identity_sets(start_athletes: pd.DataFrame) -> Tuple[set, set, Dict[str, str]]:
    if start_athletes is None or start_athletes.empty:
        return set(), set(), {}
    urls = set(start_athletes.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).tolist())
    names = set(start_athletes.get("athlete_name", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())
    name_by_url = {}
    for _, r in start_athletes.iterrows():
        u = clean_str(r.get("athlete_url"))
        n = clean_str(r.get("athlete_name"))
        if u and n:
            name_by_url[u] = n
    return urls, names, name_by_url


def missing_scorecards_for_startlist(scorecard: pd.DataFrame, start_athletes: pd.DataFrame, section: str) -> pd.DataFrame:
    """Return start-list athletes that do not have a saved positive scorecard row."""
    if start_athletes is None or start_athletes.empty:
        return pd.DataFrame()
    urls, names, _ = _startlist_identity_sets(start_athletes)
    scored_urls, scored_names = set(), set()
    if scorecard is not None and not scorecard.empty:
        work = scorecard.copy()
        if "Score" in work.columns:
            work["_score_num"] = pd.to_numeric(work["Score"], errors="coerce").fillna(0.0)
            work = work[work["_score_num"] > 0].copy()
        scored_urls = set(work.get("Athlete URL", pd.Series(dtype=str)).dropna().astype(str).tolist())
        scored_names = set(work.get("Athlete", pd.Series(dtype=str)).dropna().astype(str).str.lower().tolist())
    missing = []
    reason = "No saved scorecard row" if scorecard is not None and not scorecard.empty else "No scorecards saved for this profile/discipline"
    for _, r in start_athletes.iterrows():
        u = clean_str(r.get("athlete_url"))
        n = clean_str(r.get("athlete_name"))
        if (u and u in scored_urls) or (n and n.lower() in scored_names):
            continue
        missing.append({
            "Athlete": n or u,
            "Athlete URL": u,
            "Discipline": section,
            "Reason": reason,
        })
    return pd.DataFrame(missing)


def filter_scorecard_to_startlist(scorecard: pd.DataFrame, start_athletes: pd.DataFrame, section: str) -> pd.DataFrame:
    """Join a global scorecard to the selected start list.

    Only scored athletes are returned here. Missing athletes are handled in a separate
    coverage table so pick tables do not get filled with fake 0.0 rows.
    """
    if start_athletes is None or start_athletes.empty or scorecard is None or scorecard.empty:
        return pd.DataFrame()
    urls, names, name_by_url = _startlist_identity_sets(start_athletes)
    df = scorecard.copy()
    if "Athlete URL" not in df.columns:
        df["Athlete URL"] = None
    if "Athlete" not in df.columns:
        df["Athlete"] = None
    mask = df["Athlete URL"].astype(str).isin(urls) | df["Athlete"].fillna("").astype(str).str.lower().isin(names)
    out = df[mask].copy()
    if out.empty:
        return out
    out["Score"] = pd.to_numeric(out.get("Score"), errors="coerce").fillna(0.0)
    out = out[out["Score"] > 0].copy()
    if out.empty:
        return out
    out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    if "Rank" in out.columns:
        out = out.drop(columns=["Rank"])
    out.insert(0, "Rank", range(1, len(out) + 1))
    out["_section"] = section
    return out





# ============================================================
# Relational athlete scorecards
# ============================================================
SCORECARD_DISCIPLINES = ["overall", "swim", "bike", "run"]


def scorecard_tables_ready() -> bool:
    """Return True when the relational scorecard tables exist."""
    try:
        supabase.table("athlete_scorecards").select("id").limit(1).execute()
        supabase.table("athlete_scorecard_evidence").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def ensure_scorecard_tables() -> None:
    """Stop the rebuild with a clear message if scorecard tables are missing."""
    if not scorecard_tables_ready():
        raise RuntimeError(
            "Missing scorecard tables. Run athlete_scorecard_tables.sql in Supabase, "
            "then redeploy and try the rebuild again."
        )


def clear_scorecard_tables_for_rebuild() -> Dict[str, Any]:
    """Clear saved scorecards without hitting the API statement timeout.

    Preferred path: call the optional Postgres RPC installed by
    scorecard_clear_rpc.sql, which truncates both scorecard tables almost
    instantly. Fallback path: batch-delete ids through Supabase if the RPC has
    not been installed yet.
    """
    try:
        supabase.rpc("clear_scorecard_tables").execute()
        return {"method": "rpc_truncate", "scorecards_deleted": None, "evidence_deleted": None}
    except Exception as rpc_error:
        evidence_deleted = delete_rows_in_batches("athlete_scorecard_evidence", chunk_size=500)
        scorecards_deleted = delete_rows_in_batches("athlete_scorecards", chunk_size=500)
        return {
            "method": "batched_delete",
            "scorecards_deleted": scorecards_deleted,
            "evidence_deleted": evidence_deleted,
            "rpc_error": str(rpc_error),
        }


def _delete_scorecard_combo(gender: str, profile: str, discipline: str, as_of_ts: pd.Timestamp) -> None:
    as_of_label = iso_date(as_of_ts)
    for table_name in ["athlete_scorecard_evidence", "athlete_scorecards"]:
        try:
            (
                supabase.table(table_name)
                .delete()
                .eq("model_version", MODEL_CACHE_VERSION)
                .eq("as_of_date", as_of_label)
                .eq("gender", normalize_gender(gender) or gender)
                .eq("profile", profile)
                .eq("discipline", discipline)
                .execute()
            )
        except Exception:
            # If the table does not exist, the caller will show the table-ready error.
            pass


def _parse_best_scores(value: Any) -> List[float]:
    if value is None:
        return []
    if isinstance(value, list):
        vals = value
    else:
        vals = str(value).replace("[", "").replace("]", "").split(",")
    out = []
    for v in vals:
        fv = safe_float(v)
        if fv is not None and float(fv) > 0:
            out.append(round(float(fv), 3))
    return out


def _evidence_list(value: Any) -> List[Dict[str, Any]]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except Exception:
            return []
    return []



def build_athlete_ranking_result(
    results: pd.DataFrame,
    overrides: pd.DataFrame,
    gender: str,
    race_family: str,
    as_of_ts: pd.Timestamp,
    top_n: int,
    view_kind: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Build one saved scorecard view from normalized result rows."""
    if results is None or results.empty:
        return pd.DataFrame(), {"rows_after_gender": 0, "rows_after_family": 0, "athletes_ranked": 0}

    year = int(pd.to_datetime(as_of_ts).year)
    lookback_days = scorecard_lookback_days(race_family)
    window_start_rank = pd.to_datetime(as_of_ts) - pd.Timedelta(days=lookback_days)
    ranking_results = results[(results["race_date"].notna()) & (results["race_date"] >= window_start_rank) & (results["race_date"] <= as_of_ts)].copy()
    pre_gender_count = len(ranking_results)
    ranking_results = filter_rankings_by_gender(ranking_results, gender)
    post_gender_count = len(ranking_results)
    ranking_results = ranking_results[ranking_scope_mask(ranking_results, race_family)].copy()

    metrics = {
        "rows_before_gender": int(pre_gender_count),
        "rows_after_gender": int(post_gender_count),
        "rows_after_family": int(len(ranking_results)),
        "athletes_ranked": 0,
        "lookback_days": int(lookback_days),
    }
    if ranking_results.empty:
        return pd.DataFrame(), metrics

    start_all = ranking_results[["athlete_url", "athlete_name", "gender"]].drop_duplicates().dropna(subset=["athlete_name"]).copy()
    start_all["race_name"] = f"Global Rankings — {race_family}"
    start_all["race_date"] = as_of_ts
    start_all["open_rank"] = None
    metrics["athletes_ranked"] = int(start_all["athlete_name"].nunique())

    if view_kind == "overall":
        out = score_overall(ranking_results, start_all, overrides, as_of_ts, year, top_n, lookback_days=lookback_days)
    else:
        aud = build_split_audit(ranking_results, start_all, overrides, as_of_ts, normalize_gender(gender) or gender, view_kind, min_field_size=LOW_SAMPLE_WARNING_THRESHOLD)
        out = score_splits_for_start_list(aud, start_all, as_of_ts, top_n, strong_sof_threshold=STRONG_SOF_THRESHOLD, lookback_days=lookback_days)
    if not out.empty:
        out["Cache View"] = view_kind
        out["Gender"] = gender
        out["Race Family"] = race_family
        out["As Of"] = format_date(as_of_ts)
    return out, metrics

def save_athlete_scorecard_combo(
    results: pd.DataFrame,
    overrides: pd.DataFrame,
    gender: str,
    profile: str,
    as_of_ts: pd.Timestamp,
    discipline: str,
    top_n: int = TOP_SCORES_USED,
) -> Tuple[int, int, Dict[str, Any]]:
    """Build one profile/discipline/gender scorecard and store it in real tables."""
    df, metrics = build_athlete_ranking_result(results, overrides, gender, profile, as_of_ts, top_n, discipline)
    _delete_scorecard_combo(gender, profile, discipline, as_of_ts)
    if df is None or df.empty:
        return 0, 0, metrics

    as_of_label = iso_date(as_of_ts)
    gender_norm = normalize_gender(gender) or gender
    computed_source = f"{gender_norm} · {profile} · {discipline} · top {top_n} · {format_date(as_of_ts)}"
    score_rows: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []

    for _, r in df.iterrows():
        row = json_safe_row(r)
        athlete_url = canonical_athlete_url(row.get("Athlete URL")) or clean_str(row.get("Athlete URL"))
        athlete_name = clean_str(row.get("Athlete"))
        if not athlete_url and not athlete_name:
            continue
        score = safe_float(row.get("Score")) or 0.0
        if discipline == "overall":
            best_scores = _parse_best_scores(row.get("Best Scores Used"))
            current_year_score = safe_float(row.get("Current Year ORS"))
            current_year_races = parse_int(row.get("Current Year Races"))
            current_year_scored = parse_int(row.get("Current Year Scored"))
            evidence_count = parse_int(row.get("Recent Races Used")) or len([x for x in best_scores if x > 0])
            confidence = ""
            last_race_name = clean_str(row.get("Last Race"))
            last_race_date = clean_str(row.get("Last Race Date"))
        else:
            best_scores = _parse_best_scores(row.get("Best Split Scores Used"))
            current_year_score = None
            current_year_races = None
            current_year_scored = None
            evidence_count = parse_int(row.get("Evidence Count")) or len([x for x in best_scores if x > 0])
            confidence = clean_str(row.get("Confidence"))
            last_race_name = clean_str(row.get("Last Race"))
            last_race_date = clean_str(row.get("Last Race Date"))

        ev_rows = _evidence_list(row.get("Score Evidence"))
        if (score <= 0) and not ev_rows:
            continue

        rank_val = parse_int(row.get("Rank"))
        score_rows.append({
            "model_version": MODEL_CACHE_VERSION,
            "as_of_date": as_of_label,
            "profile": profile,
            "discipline": discipline,
            "gender": gender_norm,
            "athlete_url": athlete_url,
            "athlete_name": athlete_name,
            "rank": rank_val,
            "score": round(float(score), 4),
            "best_scores": best_scores,
            "evidence_count": int(evidence_count or 0),
            "current_year_score": None if current_year_score is None else round(float(current_year_score), 4),
            "current_year_races": current_year_races,
            "current_year_scored": current_year_scored,
            "confidence": confidence,
            "last_race_name": last_race_name,
            "last_race_date": last_race_date or None,
            "computed_source": computed_source,
            "raw": row,
        })

        for used_rank, ev in enumerate(ev_rows[:top_n], start=1):
            ev_safe = json_safe_row(ev)
            evidence_rows.append({
                "model_version": MODEL_CACHE_VERSION,
                "as_of_date": as_of_label,
                "profile": profile,
                "discipline": discipline,
                "gender": gender_norm,
                "athlete_url": athlete_url,
                "athlete_name": athlete_name,
                "used_rank": used_rank,
                "race_date": clean_str(ev_safe.get("Date")) or None,
                "race_name": clean_str(ev_safe.get("Race")),
                "race_type": clean_str(ev_safe.get("Race Type")),
                "place": clean_str(ev_safe.get("Place")),
                "sof": safe_float(ev_safe.get("SOF")),
                "ors": safe_float(ev_safe.get("ORS")),
                "split_text": clean_str(ev_safe.get("Split")),
                "split_rank": clean_str(ev_safe.get("Split Rank")),
                "pct_behind_fastest": safe_float(ev_safe.get("% Behind Fastest")),
                "evidence_score": safe_float(ev_safe.get("Evidence Score")) or safe_float(ev_safe.get("ORS")),
                "raw": ev_safe,
            })

    if score_rows:
        insert_chunks("athlete_scorecards", score_rows, chunk_size=500)
    if evidence_rows:
        insert_chunks("athlete_scorecard_evidence", evidence_rows, chunk_size=500)
    clear_cache()
    return len(score_rows), len(evidence_rows), metrics


def rebuild_all_athlete_scorecards(results: pd.DataFrame, overrides: pd.DataFrame, as_of_ts: pd.Timestamp) -> pd.DataFrame:
    """Fast one-pass rebuild using score_engine.py.

    The older version rebuilt every gender/profile/discipline combination by
    repeatedly filtering/scanning the full results table. This version hands the
    normalized results to a dedicated engine once, then bulk-saves the returned
    scorecard and evidence rows.
    """
    if build_all_scorecards_fast is None:
        raise RuntimeError(f"score_engine.py could not be imported: {SCORE_ENGINE_IMPORT_ERROR}")

    ensure_scorecard_tables()
    progress = st.progress(0, text="Preparing fast scorecard engine...")
    as_of_ts = pd.to_datetime(as_of_ts, errors="coerce")
    if pd.isna(as_of_ts):
        as_of_ts = pd.Timestamp.today().normalize()

    progress.progress(0.15, text="Building all scorecards in one engine pass...")
    scorecards_df, evidence_df, logs_df = build_all_scorecards_fast(
        results=results,
        as_of_date=as_of_ts,
        model_version=MODEL_CACHE_VERSION,
        top_n=TOP_SCORES_USED,
    )

    progress.progress(0.65, text="Clearing saved scorecard tables...")
    # Rebuild-all should be deterministic: clear old scorecards/evidence first,
    # then save the fresh model version. Use RPC truncate when available; fall
    # back to batched deletes so large tables do not time out.
    clear_info = clear_scorecard_tables_for_rebuild()

    progress.progress(0.78, text="Saving athlete scorecards...")
    scorecard_rows = cache_safe_rows(scorecards_df) if scorecards_df is not None and not scorecards_df.empty else []
    evidence_rows = cache_safe_rows(evidence_df) if evidence_df is not None and not evidence_df.empty else []
    if scorecard_rows:
        insert_chunks("athlete_scorecards", scorecard_rows, chunk_size=750)
    progress.progress(0.90, text="Saving scorecard evidence...")
    if evidence_rows:
        insert_chunks("athlete_scorecard_evidence", evidence_rows, chunk_size=750)

    clear_cache()
    progress.progress(1.0, text="Scorecard rebuild complete.")
    progress.empty()

    logs_df = pd.DataFrame() if logs_df is None else logs_df.copy()
    if not logs_df.empty:
        logs_df["Model Version"] = MODEL_CACHE_VERSION
        logs_df["Saved Scorecards"] = len(scorecard_rows)
        logs_df["Saved Evidence Rows"] = len(evidence_rows)
        logs_df["Clear Method"] = clear_info.get("method")
    return logs_df


def _latest_scorecard_date(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty or "as_of_date" not in df.columns:
        return None
    vals = pd.to_datetime(df["as_of_date"], errors="coerce").dropna()
    if vals.empty:
        return None
    return vals.max().strftime("%Y-%m-%d")


def _latest_scorecard_as_of_date(gender: str, profile: str, discipline: str) -> str:
    """Return latest saved as_of_date for this scorecard slice without loading all rows."""
    gender_norm = normalize_gender(gender) or gender
    try:
        res = (
            supabase.table("athlete_scorecards")
            .select("as_of_date")
            .eq("model_version", MODEL_CACHE_VERSION)
            .eq("gender", gender_norm)
            .eq("profile", profile)
            .eq("discipline", discipline)
            .order("as_of_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            return iso_date(rows[0].get("as_of_date"))
    except Exception:
        pass
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def load_athlete_scorecard_view_cached(gender: str, profile: str, discipline: str, as_of_label: str) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    gender_norm = normalize_gender(gender) or gender
    if not as_of_label:
        return pd.DataFrame(), pd.DataFrame(), {}
    filters = (
        ("model_version", MODEL_CACHE_VERSION),
        ("gender", gender_norm),
        ("profile", profile),
        ("discipline", discipline),
        ("as_of_date", as_of_label),
    )
    cards = pd.DataFrame(fetch_all_filtered("athlete_scorecards", filters))
    ev = pd.DataFrame(fetch_all_filtered("athlete_scorecard_evidence", filters))
    return cards, ev, {"as_of_date": as_of_label, "rows": len(cards), "evidence_rows": len(ev)}


def load_athlete_scorecard_view(gender: str, profile: str, discipline: str, as_of_ts: Optional[pd.Timestamp] = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Load one saved scorecard slice using Supabase filters instead of full-table scans."""
    if not scorecard_tables_ready():
        return pd.DataFrame(), pd.DataFrame(), {}
    gender_norm = normalize_gender(gender) or gender
    target = iso_date(as_of_ts) if as_of_ts is not None else ""
    as_of_label = ""

    # Prefer exact date if it exists. Otherwise use latest saved date.
    if target:
        try:
            res = (
                supabase.table("athlete_scorecards")
                .select("id")
                .eq("model_version", MODEL_CACHE_VERSION)
                .eq("gender", gender_norm)
                .eq("profile", profile)
                .eq("discipline", discipline)
                .eq("as_of_date", target)
                .limit(1)
                .execute()
            )
            if res.data:
                as_of_label = target
        except Exception:
            as_of_label = ""
    if not as_of_label:
        as_of_label = _latest_scorecard_as_of_date(gender_norm, profile, discipline)
    if not as_of_label:
        return pd.DataFrame(), pd.DataFrame(), {}
    return load_athlete_scorecard_view_cached(gender_norm, profile, discipline, as_of_label)


def _display_scorecards_from_tables(cards: pd.DataFrame, evidence: pd.DataFrame, discipline: str) -> pd.DataFrame:
    if cards is None or cards.empty:
        return pd.DataFrame()
    evidence_by_url: Dict[str, List[Dict[str, Any]]] = {}
    if evidence is not None and not evidence.empty:
        evidence = evidence.sort_values(["athlete_url", "used_rank"], na_position="last").copy()
        for url, g in evidence.groupby("athlete_url"):
            rows = []
            for _, ev in g.iterrows():
                raw = ev.get("raw") if isinstance(ev.get("raw"), dict) else {}
                if raw:
                    rows.append(raw)
                else:
                    rows.append({
                        "Date": format_date(ev.get("race_date")),
                        "Race": clean_str(ev.get("race_name")),
                        "Race Type": clean_str(ev.get("race_type")),
                        "Place": clean_str(ev.get("place")),
                        "SOF": ev.get("sof"),
                        "ORS": ev.get("ors"),
                        "Split": clean_str(ev.get("split_text")),
                        "Split Rank": clean_str(ev.get("split_rank")),
                        "% Behind Fastest": ev.get("pct_behind_fastest"),
                        "Evidence Score": ev.get("evidence_score"),
                    })
            evidence_by_url[clean_str(url)] = rows
    out_rows = []
    for _, r in cards.sort_values("rank", na_position="last").iterrows():
        url = canonical_athlete_url(r.get("athlete_url")) or clean_str(r.get("athlete_url"))
        best_scores = r.get("best_scores")
        if isinstance(best_scores, str):
            try:
                best_scores = json.loads(best_scores)
            except Exception:
                best_scores = _parse_best_scores(best_scores)
        if not isinstance(best_scores, list):
            best_scores = []
        best_text = ", ".join([f"{safe_float(x):.1f}" for x in best_scores if safe_float(x) is not None])
        raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
        row = {
            "Rank": parse_int(r.get("rank")),
            "Athlete": clean_str(r.get("athlete_name")),
            "Athlete URL": url,
            "Score": round(float(safe_float(r.get("score")) or 0.0), 1),
            "Best Scores Used": best_text if discipline == "overall" else None,
            "Best Split Scores Used": best_text if discipline != "overall" else None,
            "Score Evidence": evidence_by_url.get(url, []),
            "Evidence Count": parse_int(r.get("evidence_count")) or 0,
            "Confidence": clean_str(r.get("confidence")),
            "Current Year ORS": r.get("current_year_score"),
            "Current Year Races": r.get("current_year_races"),
            "Current Year Scored": r.get("current_year_scored"),
            "Last Race": clean_str(r.get("last_race_name")),
            "Last Race Date": format_date(r.get("last_race_date")),
            "Computed Source": clean_str(r.get("computed_source")),
        }
        # Preserve any extra high-value columns from the original scoring row.
        for extra in [
            "OpenRank Score", "OpenRank Split Score", "Best Recent ORS", "Strong Field ORS", "Recent Races Used",
            "Premium Evidence Count", "Strong Evidence Count", "Last Rank", "Best Recent Split",
            "Premium Field Score", "Strong Field Score", "Premium Avg Behind %", "Strong Avg Behind %", "Recent Avg Behind %",
        ]:
            if extra in raw and extra not in row:
                row[extra] = raw.get(extra)
        if discipline == "overall":
            row["OpenRank Score"] = row.get("OpenRank Score") or row["Score"]
        else:
            row["OpenRank Split Score"] = row.get("OpenRank Split Score") or row["Score"]
        out_rows.append(row)
    out = pd.DataFrame(out_rows)
    if not out.empty:
        out = out.sort_values("Score", ascending=False).reset_index(drop=True)
        out["Rank"] = range(1, len(out) + 1)
    return out


def load_athlete_scorecard_display(gender: str, profile: str, discipline: str, as_of_ts: Optional[pd.Timestamp] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    cards, ev, meta = load_athlete_scorecard_view(gender, profile, discipline, as_of_ts)
    return _display_scorecards_from_tables(cards, ev, discipline), meta


def build_race_prediction_from_scorecard_tables(starts: pd.DataFrame, selected_race: str, selected_date: pd.Timestamp, selected_gender: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if starts is None or starts.empty:
        return pd.DataFrame(), {}
    selected_date = pd.to_datetime(selected_date) if not pd.isna(selected_date) else pd.Timestamp.today().normalize()
    profile = prediction_scope_from_race(selected_race, None, None)
    start_athletes = starts[(starts["race_name"] == selected_race) & (starts["gender"] == selected_gender)].copy()
    if "race_date" in start_athletes.columns:
        start_athletes = start_athletes[start_athletes["race_date"] == selected_date]
    imported_start_rows = len(start_athletes)
    start_athletes = dedupe_start_athletes(start_athletes)
    if start_athletes.empty:
        return pd.DataFrame(), {"prediction_scope": profile, "start_list_athletes": 0}

    combined = []
    meta = {
        "prediction_scope": profile,
        "start_list_athletes": int(len(start_athletes)),
        "duplicate_start_rows": int(imported_start_rows - len(start_athletes)),
        "source": "athlete_scorecards",
        "missing_scorecards": {},
    }
    for discipline in SCORECARD_DISCIPLINES:
        scorecard, smeta = load_athlete_scorecard_display(selected_gender, profile, discipline, None)
        meta[f"{discipline}_scorecard_rows"] = int(len(scorecard)) if scorecard is not None else 0
        if smeta.get("as_of_date"):
            meta[f"{discipline}_as_of_date"] = smeta.get("as_of_date")
        selected = filter_scorecard_to_startlist(scorecard, start_athletes, discipline)
        missing_df = missing_scorecards_for_startlist(scorecard, start_athletes, discipline)
        meta[f"{discipline}_matched"] = int(len(selected))
        meta[f"{discipline}_missing_count"] = int(len(missing_df))
        meta["missing_scorecards"][discipline] = cache_safe_rows(missing_df.head(250)) if not missing_df.empty else []
        for row in cache_safe_rows(selected.head(120)):
            row["_section"] = discipline
            combined.append(row)
    return pd.DataFrame(combined), meta

def render_score_evidence(scored: pd.DataFrame, title: str, limit: int = 5) -> None:
    if scored is None or scored.empty or "Score Evidence" not in scored.columns:
        return
    st.caption(f"Open an athlete to see the up to {TOP_SCORES_USED} race rows feeding the displayed score. Missing slots are not padded with 0.0.")
    for _, r in scored.head(limit).iterrows():
        athlete = clean_str(r.get("Athlete")) or "Athlete"
        score = r.get("Score")
        evidence = r.get("Score Evidence")
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except Exception:
                evidence = []
        if not isinstance(evidence, list):
            evidence = []
        with st.expander(f"{athlete} — Score {score}", expanded=False):
            if evidence:
                display_table(pd.DataFrame(evidence), list(pd.DataFrame(evidence).columns), height=240)
            else:
                st.info("No eligible evidence rows for this scorecard profile.")


def _positive_score_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["Score"] = pd.to_numeric(out.get("Score"), errors="coerce").fillna(0.0)
    return out[out["Score"] > 0].copy()


def _render_missing_scorecards(params: Dict[str, Any], discipline: str) -> None:
    missing = []
    if isinstance(params, dict):
        missing = (params.get("missing_scorecards") or {}).get(discipline, []) or []
    if missing:
        with st.expander(f"Missing {discipline.title()} scorecards / no eligible evidence ({len(missing)})", expanded=False):
            st.caption("These athletes are on the start list, but they do not have an eligible positive scorecard for this profile/discipline. Use Split Audit → Raw imported career rows to see whether the cause is missing imports, missing splits, outside the 52-week window, wrong gender, or outside the selected profile.")
            display_table(pd.DataFrame(missing), ["Athlete", "Discipline", "Reason", "Athlete URL"], height=280)


def display_cached_race_prediction(cached_df: pd.DataFrame, cache_meta: Optional[Dict[str, Any]] = None) -> None:
    params = (cache_meta or {}).get("params", {}) if isinstance(cache_meta, dict) else {}
    computed_at = (cache_meta or {}).get("computed_at") if isinstance(cache_meta, dict) else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scored rows", f"{len(cached_df) if cached_df is not None else 0:,}")
    c2.metric("Start athletes", params.get("start_list_athletes", "—"))
    c3.metric("Profile", params.get("prediction_scope", "—"))
    c4.metric("Scorecards as of", clean_str(computed_at)[:19] if computed_at else "—")
    st.info("Fast mode: showing saved athlete scorecards joined to this start list. Missing/no-evidence athletes are shown in separate expanders instead of polluting the pick tables with 0.0 rows.")

    section_title("🏆", "Overall Picks")
    overall = _positive_score_rows(cached_section(cached_df, "overall"))
    display_table(overall.head(20), ["Rank", "Athlete", "Score", "OpenRank Score", "Best Scores Used", "Current Year ORS", "Current Year Races", "Current Year Scored", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "Last Race", "Last Race Date"])
    render_score_evidence(overall, "Overall score evidence", limit=8)
    _render_missing_scorecards(params, "overall")

    st.divider()
    tabs = st.tabs(["🏊 Fastest Swim", "🚴 Fastest Bike", "🏃 Fastest Run"])
    for tab, disc, title in zip(tabs, ["swim", "bike", "run"], ["Fastest Swim", "Fastest Bike", "Fastest Run"]):
        with tab:
            section_title("🏊" if disc == "swim" else "🚴" if disc == "bike" else "🏃", title)
            scored = _positive_score_rows(cached_section(cached_df, disc))
            display_table(
                scored.head(20),
                ["Rank", "Athlete", "Score", "OpenRank Split Score", "Best Split Scores Used", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split"],
                height=360,
            )
            render_score_evidence(scored, f"{title} evidence", limit=8)
            _render_missing_scorecards(params, disc)



# ============================================================
# Command center and data-quality views
# ============================================================
def scorecard_latest_summary() -> Dict[str, Any]:
    try:
        cards = load_table("athlete_scorecards")
        ev = load_table("athlete_scorecard_evidence")
    except Exception:
        cards, ev = pd.DataFrame(), pd.DataFrame()
    if not cards.empty and "model_version" in cards.columns:
        cards = cards[cards["model_version"] == MODEL_CACHE_VERSION].copy()
    if not ev.empty and "model_version" in ev.columns:
        ev = ev[ev["model_version"] == MODEL_CACHE_VERSION].copy()
    latest = _latest_scorecard_date(cards) if not cards.empty else None
    return {"cards": cards, "evidence": ev, "scorecard_rows": len(cards), "evidence_rows": len(ev), "latest_date": latest or "—"}


def start_list_scorecard_coverage(starts: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    if starts is None or starts.empty:
        return pd.DataFrame()
    work = starts.dropna(subset=["race_name"]).copy()
    if work.empty:
        return pd.DataFrame()
    rows = []
    card_work = cards.copy() if cards is not None else pd.DataFrame()
    if not card_work.empty:
        card_work["athlete_url"] = card_work.get("athlete_url", pd.Series(dtype=str)).map(canonical_athlete_url)
        card_work = card_work[card_work.get("model_version", "") == MODEL_CACHE_VERSION].copy() if "model_version" in card_work.columns else card_work
        card_work = card_work[card_work.get("discipline", "") == "overall"].copy() if "discipline" in card_work.columns else card_work
    group_cols = ["race_name", "race_date", "gender"]
    for keys, g in work.groupby(group_cols, dropna=False):
        race_name, race_date, gender = keys
        sg = dedupe_start_athletes(g)
        profile = prediction_scope_from_race(race_name, None, None)
        urls = set(sg.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).map(canonical_athlete_url).tolist())
        matched = 0
        latest = "—"
        if not card_work.empty:
            cw = card_work[(card_work.get("gender", "") == (normalize_gender(gender) or gender)) & (card_work.get("profile", "") == profile)].copy()
            if not cw.empty:
                latest = _latest_scorecard_date(cw) or "—"
                if latest != "—" and "as_of_date" in cw.columns:
                    cw = cw[cw["as_of_date"].map(iso_date) == latest].copy()
                scored_urls = set(cw.get("athlete_url", pd.Series(dtype=str)).dropna().astype(str).map(canonical_athlete_url).tolist())
                matched = len(urls & scored_urls)
        rows.append({
            "Race": race_name,
            "Date": format_date(race_date),
            "Gender": normalize_gender(gender) or gender or "Unknown",
            "Profile": profile,
            "Start Athletes": int(len(sg)),
            "Scorecards Matched": int(matched),
            "Missing Scorecards": int(max(len(sg) - matched, 0)),
            "Coverage %": round((matched / len(sg) * 100), 1) if len(sg) else 0,
            "Scorecards As Of": latest,
        })
    return pd.DataFrame(rows).sort_values(["Date", "Race", "Gender"], ascending=[False, True, True], na_position="last")


def render_command_center() -> None:
    st.header("📊 Command Center")
    st.caption("A quick operating view: data coverage, scorecard status, and start lists that need attention.")
    results, starts, athletes, overrides = prepare_dataframes()
    score_summary = scorecard_latest_summary()
    cards = score_summary["cards"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Athletes", f"{len(athletes):,}")
    c2.metric("Result rows", f"{len(results):,}")
    c3.metric("Start-list rows", f"{len(starts):,}")
    c4.metric("Scorecard rows", f"{score_summary['scorecard_rows']:,}")

    missing_gender = int(athletes.get("gender", pd.Series(dtype=object)).map(normalize_gender).isna().sum()) if not athletes.empty and "gender" in athletes.columns else 0
    missing_result_gender = int(results.get("gender", pd.Series(dtype=object)).map(normalize_gender).isna().sum()) if not results.empty and "gender" in results.columns else 0
    missing_ors = int(pd.to_numeric(results.get("ors", pd.Series(dtype=float)), errors="coerce").isna().sum()) if not results.empty else 0
    stale_msg = "Ready" if score_summary["scorecard_rows"] else "Needs scorecard rebuild"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Missing athlete gender", f"{missing_gender:,}")
    c2.metric("Missing result gender", f"{missing_result_gender:,}")
    c3.metric("Rows missing ORS", f"{missing_ors:,}")
    c4.metric("Scorecards as of", score_summary["latest_date"], delta=stale_msg)

    st.divider()
    section_title("📋", "Start-list readiness")
    coverage = start_list_scorecard_coverage(starts, cards)
    if coverage.empty:
        st.info("No start lists imported yet.")
    else:
        needs = coverage[coverage["Missing Scorecards"] > 0].copy()
        st.caption("Scorecard coverage checks the selected race profile against saved Overall scorecards. Missing athletes may still need gender fixes, result imports, or eligible recent races.")
        display_table(coverage.head(20), ["Race", "Date", "Gender", "Profile", "Start Athletes", "Scorecards Matched", "Missing Scorecards", "Coverage %", "Scorecards As Of"], height=420)
        if not needs.empty:
            with st.expander(f"Start lists needing attention ({len(needs)})", expanded=False):
                display_table(needs, ["Race", "Date", "Gender", "Profile", "Start Athletes", "Scorecards Matched", "Missing Scorecards", "Coverage %", "Scorecards As Of"], height=360)


def render_data_quality() -> None:
    st.header("🧹 Data Quality")
    st.caption("Find the data problems that create missing scorecards, unknown race groups, and weird rankings.")
    results, starts, athletes, overrides = prepare_dataframes()
    score_summary = scorecard_latest_summary()

    athlete_gender = athletes.get("gender", pd.Series(dtype=object)).map(normalize_gender) if not athletes.empty and "gender" in athletes.columns else pd.Series(dtype=object)
    result_gender = results.get("gender", pd.Series(dtype=object)).map(normalize_gender) if not results.empty and "gender" in results.columns else pd.Series(dtype=object)
    start_gender = starts.get("gender", pd.Series(dtype=object)).map(normalize_gender) if not starts.empty and "gender" in starts.columns else pd.Series(dtype=object)
    ors_missing = pd.to_numeric(results.get("ors", pd.Series(dtype=float)), errors="coerce").isna() if not results.empty else pd.Series(dtype=bool)
    sof_missing = pd.to_numeric(results.get("sof", pd.Series(dtype=float)), errors="coerce").isna() if not results.empty else pd.Series(dtype=bool)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Athletes missing gender", f"{int(athlete_gender.isna().sum()) if len(athlete_gender) else 0:,}")
    c2.metric("Result rows missing gender", f"{int(result_gender.isna().sum()) if len(result_gender) else 0:,}")
    c3.metric("Result rows missing ORS", f"{int(ors_missing.sum()) if len(ors_missing) else 0:,}")
    c4.metric("Result rows missing SOF", f"{int(sof_missing.sum()) if len(sof_missing) else 0:,}")

    st.divider()
    tabs = st.tabs(["Missing gender", "Missing ORS/SOF", "Duplicates", "Scorecard coverage"])
    with tabs[0]:
        if not athletes.empty and "gender" in athletes.columns:
            missing_ath = athletes[athletes["gender"].map(normalize_gender).isna()].copy()
            if not missing_ath.empty:
                display_table(missing_ath.head(300), ["athlete_name", "athlete_url", "gender"], height=420)
                st.download_button("Download missing athlete gender CSV", missing_ath.to_csv(index=False).encode("utf-8"), "missing_athlete_gender.csv", "text/csv")
            else:
                st.success("No athletes missing gender.")
    with tabs[1]:
        if not results.empty:
            show = results[ors_missing | sof_missing].copy()
            display_table(show.head(300), ["athlete_name", "gender", "race_date", "race_name", "race_type", "ors", "sof", "athlete_url"], height=460)
            if not show.empty:
                st.download_button("Download rows missing ORS/SOF", show.to_csv(index=False).encode("utf-8"), "missing_ors_sof_rows.csv", "text/csv")
    with tabs[2]:
        dup_cards = []
        if not athletes.empty and "athlete_url" in athletes.columns:
            d = athletes[athletes["athlete_url"].notna()].groupby("athlete_url").size().reset_index(name="Rows")
            dup_cards.append(("Duplicate athlete master URLs", d[d["Rows"] > 1]))
        if not results.empty:
            keys = [c for c in ["athlete_url", "race_date", "race_name", "race_type"] if c in results.columns]
            if keys:
                d = results.groupby(keys, dropna=False).size().reset_index(name="Rows")
                dup_cards.append(("Duplicate result rows", d[d["Rows"] > 1]))
        for title, dup in dup_cards:
            with st.expander(f"{title}: {len(dup):,} groups", expanded=False):
                display_table(dup.head(300), list(dup.columns), height=320)
    with tabs[3]:
        coverage = start_list_scorecard_coverage(starts, score_summary["cards"])
        if coverage.empty:
            st.info("No start lists to check.")
        else:
            display_table(coverage, ["Race", "Date", "Gender", "Profile", "Start Athletes", "Scorecards Matched", "Missing Scorecards", "Coverage %", "Scorecards As Of"], height=520)


with st.sidebar:
    st.markdown(
        """
        <div class="tri-sidebar-brand">
            <div><span class="logo">🏁</span><span class="title">Triathlon Picks</span></div>
            <div class="subtitle">Supabase scoring engine · Streamlit dashboard</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for section, items in NAV_GROUPS:
        st.markdown(f'<div class="tri-sidebar-section">{section}</div>', unsafe_allow_html=True)
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

if page == "Command Center":
    render_command_center()

elif page == "Data Quality":
    render_data_quality()

elif page == "Connection":
    st.header("🔌 Connection")
    try:
        result = supabase.table("athletes").select("id", count="exact").limit(1).execute()
        st.success("Connected to Supabase.")
        st.metric("Athletes", result.count or 0)

        st.subheader("Table counts")
        count_rows_data = []
        for table_name in ["athletes", "athlete_results", "race_field_results", "start_lists", "athlete_scorecards", "athlete_scorecard_evidence", "race_overrides", "scoring_settings", "model_cache", "model_runs", "split_audit"]:
            count_rows_data.append({"Table": table_name, "Rows in Supabase": count_rows(table_name)})
        st.dataframe(pd.DataFrame(count_rows_data), width="stretch", hide_index=True)
    except Exception as e:
        st.error("Could not read from Supabase. Make sure tables exist and secrets are correct.")
        st.exception(e)

elif page == "Import CSVs":
    st.header("📥 Import Center")
    st.caption("All CSV uploads live here now: results, start-list updates, manual gender fixes, overrides, and settings.")
    render_import_overview()
    st.markdown(
        """
        <div class="tri-help-strip">
            After importing new results or changing start lists, rebuild athlete scorecards in <b>Model Cache</b> so rankings and dashboards use the latest data.
        </div>
        """,
        unsafe_allow_html=True,
    )

    import_tabs = st.tabs(["🏁 Results", "📋 Start Lists", "🧬 Gender Fixes", "⚙️ Settings / Overrides"])

    with import_tabs[0]:
        section_title("🏁", "Result imports")
        st.write("Use this for athlete race history and race-field result CSVs.")
        table_choice = st.radio("Result CSV type", ["Athlete Results", "Race Field Results"], horizontal=True)
        replace_results = st.checkbox(
            f"Replace entire {table_choice} table before import",
            value=False,
            help="Usually leave this off for normal updates. Turn it on only when doing a full reload of that table.",
        )
        uploaded = st.file_uploader(f"Upload {table_choice} CSV", type=["csv"], key="results_import_csv")
        if uploaded is not None:
            df = read_uploaded_csv(uploaded)
            render_csv_preview(df)
            if st.button(f"Import {table_choice}", type="primary", key="import_results_btn"):
                try:
                    with st.spinner(f"Importing {table_choice}..."):
                        import_results_csv(df, table_choice, replace_results)
                    st.info("Next step: Model Cache → Rebuild athlete scorecards.")
                except Exception as e:
                    st.error("Import failed.")
                    st.exception(e)


    with import_tabs[1]:
        section_title("🔄", "Clean API results refresh")
        st.write("Refresh athlete results from the clean TriNews API tables instead of the older spreadsheet import. This repairs corrupted split times like 0:32 or 3:14 when the API has the full leg time.")
        if build_clean_results_refresh is None:
            st.error(f"trinews_api_refresh.py could not be imported: {TRINEWS_API_IMPORT_ERROR}")
            st.info("Add trinews_api_refresh.py to the repo root next to streamlit_app.py.")
        else:
            try:
                default_trinews_key = st.secrets.get("TRINEWS_API_KEY", "")
            except Exception:
                default_trinews_key = ""
            api_key = st.text_input(
                "TriNews API key",
                value=default_trinews_key,
                type="password",
                help="Use the permissioned public/anon API key. Add TRINEWS_API_KEY to Streamlit secrets to avoid pasting it each time.",
                key="trinews_clean_refresh_key",
            )
            st.caption("Enter athlete names, athlete URLs, slugs, or TriNews athlete UUIDs. One per line.")
            identifiers_text = st.text_area(
                "Athletes to refresh",
                value="Hanne De Vet",
                height=120,
                key="trinews_clean_refresh_identifiers",
            )
            c1, c2, c3 = st.columns(3)
            result_limit = c1.number_input("Recent results per athlete", min_value=5, max_value=250, value=100, step=5)
            include_fields = c2.checkbox("Refresh full race fields", value=True, help="Recommended. This pulls every athlete in each refreshed race so split scorecards have the correct field baseline.")
            max_races = c3.number_input("Max race fields", min_value=1, max_value=100, value=40, step=1)
            st.info("Recommended flow: refresh a small group first, review the log, then rebuild athlete scorecards.")
            if st.button("Run clean API refresh", type="primary", key="run_clean_api_refresh"):
                identifiers = [x.strip() for x in identifiers_text.splitlines() if x.strip()]
                if not identifiers:
                    st.warning("Enter at least one athlete.")
                elif not api_key:
                    st.warning("Enter the TriNews API key or add TRINEWS_API_KEY to Streamlit secrets.")
                else:
                    loader = loading_card("Refreshing clean API results", "Resolving athletes, races, results, and split times...")
                    try:
                        refresh_payload = build_clean_results_refresh(
                            api_key=api_key,
                            identifiers=identifiers,
                            result_limit_per_athlete=int(result_limit),
                            include_race_fields=bool(include_fields),
                            max_races=int(max_races),
                        )
                    finally:
                        loader.empty()

                    athlete_rows = refresh_payload.get("athletes", []) or []
                    athlete_result_rows = dedupe_result_rows(refresh_payload.get("athlete_results", []) or [])
                    race_field_rows = dedupe_result_rows(refresh_payload.get("race_field_results", []) or [])

                    # Save master athletes first. Manual gender overrides still win inside the normal sync path.
                    a_inserted, a_updated = upsert_athletes_preserve_gender(athlete_rows)

                    ar_rows, ar_ath_ins, ar_ath_upd, ar_prop = sync_athlete_master_import(athlete_result_rows, athlete_rows)
                    rf_rows, rf_ath_ins, rf_ath_upd, rf_prop = sync_athlete_master_import(race_field_rows, athlete_rows)

                    ar_inserted, ar_skipped, ar_updated = merge_result_rows("athlete_results", ar_rows)
                    rf_inserted, rf_skipped, rf_updated = merge_result_rows("race_field_results", rf_rows)
                    clear_cache()

                    st.success(
                        "Clean API refresh complete. "
                        f"Athlete results: {ar_inserted:,} inserted, {ar_updated:,} updated, {ar_skipped:,} skipped. "
                        f"Race-field results: {rf_inserted:,} inserted, {rf_updated:,} updated, {rf_skipped:,} skipped. "
                        f"Athletes: {a_inserted + ar_ath_ins + rf_ath_ins:,} new, {a_updated + ar_ath_upd + rf_ath_upd:,} updated."
                    )
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Resolved athletes", f"{len(athlete_rows):,}")
                    m2.metric("Athlete result rows", f"{len(ar_rows):,}")
                    m3.metric("Race-field rows", f"{len(rf_rows):,}")
                    m4.metric("Races found", f"{refresh_payload.get('races_found', 0):,}")
                    logs_df = pd.DataFrame(refresh_payload.get("logs", []) or [])
                    if not logs_df.empty:
                        st.subheader("API refresh log")
                        st.dataframe(logs_df, width="stretch")
                    st.info("Next step: Model Cache → Rebuild athlete scorecards.")

    with import_tabs[2]:
        section_title("📋", "Start-list imports and updates")
        st.write("Use this when a start list changes. Replace a selected race/gender group, merge only new athletes, or import a CSV that already includes race/date/gender columns.")
        start_mode = st.radio(
            "Start-list workflow",
            ["Update selected start list", "Import start-list CSV with race/date/gender columns"],
            horizontal=True,
        )
        if start_mode == "Update selected start list":
            try:
                _, starts, _, _ = prepare_dataframes()
            except Exception:
                starts = pd.DataFrame()
            if starts is None or starts.empty:
                st.warning("No existing start lists found. Use the general start-list import workflow first.")
            else:
                groups = start_list_group_summary(starts)
                if groups.empty:
                    st.warning("No start-list groups found.")
                else:
                    default_index = 0
                    preset = st.session_state.get("selected_start_list_for_import")
                    if isinstance(preset, dict):
                        preset_key = f"{preset.get('race_date')} | {preset.get('gender')} | {preset.get('race_name')}"
                        matches = groups.index[groups["_select_key"].eq(preset_key)].tolist()
                        if matches:
                            default_index = int(matches[0])
                    selected_key = st.selectbox("Start list to update", groups["_select_key"].tolist(), index=default_index, key="import_selected_start_group")
                    selected = groups[groups["_select_key"] == selected_key].iloc[0]
                    race_name = selected.get("_race_name")
                    race_date = selected.get("_race_date")
                    gender = selected.get("_gender")
                    current_rows = start_list_rows_for_group(starts, race_name, race_date, gender)
                    current_rows = dedupe_start_athletes(current_rows) if not current_rows.empty else current_rows
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Race", clean_str(race_name) or "—")
                    c2.metric("Gender", clean_str(gender) or "—")
                    c3.metric("Current athletes", f"{len(current_rows):,}")
                    display_table(current_rows.head(25), ["OpenRank", "Athlete", "Gender", "Race Date", "Race", "Athlete URL"], height=260)

                    upload_mode = st.radio("Upload mode", ["Replace selected start list", "Merge new athletes only"], horizontal=True, key="import_start_mode")
                    start_upload = st.file_uploader("Upload updated start-list CSV", type=["csv"], key="import_selected_start_csv")
                    if start_upload is not None:
                        up_df = read_uploaded_csv(start_upload)
                        render_csv_preview(up_df, "Updated start-list CSV preview")
                        if st.button("Apply start-list update", type="primary", key="import_selected_start_apply"):
                            try:
                                rows, athlete_rows = normalize_start_list_upload_for_group(up_df, race_name, race_date, gender)
                                rows, athlete_inserted, athlete_updated, propagated = sync_athlete_master_import(rows, athlete_rows, default_gender=gender)
                                rows = dedupe_start_list_rows(rows)
                                if upload_mode == "Replace selected start list":
                                    delete_matching_start_lists([{"race_name": race_name, "race_date": format_date(race_date), "gender": gender}])
                                    insert_chunks("start_lists", rows)
                                    inserted = len(rows)
                                    skipped = 0
                                else:
                                    inserted, skipped = merge_start_list_rows(rows)
                                clear_cache()
                                st.success(f"Start list updated. Inserted {inserted:,}; skipped {skipped:,}. Athlete master: {athlete_inserted:,} new, {athlete_updated:,} updated. Gender propagated for {propagated:,} athletes.")
                                st.info("Next step: Model Cache → Rebuild athlete scorecards.")
                            except Exception as e:
                                st.error("Start-list upload failed.")
                                st.exception(e)
        else:
            replace_start_groups = st.checkbox(
                "Replace matching race/date/gender groups before import",
                value=True,
                help="This deletes only the matching start-list groups included in the CSV, not the whole start_lists table.",
            )
            start_upload = st.file_uploader("Upload Start Lists CSV", type=["csv"], key="general_start_import_csv")
            if start_upload is not None:
                df = read_uploaded_csv(start_upload)
                render_csv_preview(df)
                if st.button("Import start lists", type="primary", key="general_start_import_btn"):
                    try:
                        with st.spinner("Importing start lists..."):
                            import_general_start_list_csv(df, replace_start_groups)
                        st.info("Next step: Model Cache → Rebuild athlete scorecards.")
                    except Exception as e:
                        st.error("Start-list import failed.")
                        st.exception(e)

    with import_tabs[3]:
        section_title("🧬", "Manual gender fixes")
        st.write("Fix athlete gender from a small CSV. This writes to the athlete master and propagates the gender to linked result/start-list rows.")
        raw_athletes = load_table("athletes")
        render_manual_gender_override_import(raw_athletes, key_prefix="import_center_gender")

    with import_tabs[4]:
        section_title("⚙️", "Overrides and settings")
        admin_choice = st.radio("Admin CSV type", ["Race Overrides", "Scoring Settings"], horizontal=True)
        replace_admin = st.checkbox("Replace existing rows before importing", value=False, key="admin_replace_csv")
        admin_upload = st.file_uploader(f"Upload {admin_choice} CSV", type=["csv"], key="admin_import_csv")
        if admin_upload is not None:
            df = read_uploaded_csv(admin_upload)
            render_csv_preview(df)
            if st.button(f"Import {admin_choice}", type="primary", key="admin_import_btn"):
                try:
                    if admin_choice == "Race Overrides":
                        rows = normalize_race_overrides(df)
                        if replace_admin:
                            delete_all("race_overrides")
                        insert_chunks("race_overrides", rows)
                        clear_cache()
                        st.success(f"Imported {len(rows):,} override rows.")
                    else:
                        rows = normalize_scoring_settings(df)
                        if replace_admin:
                            delete_all("scoring_settings")
                        upsert_chunks("scoring_settings", rows, on_conflict="setting_group,setting_key")
                        clear_cache()
                        st.success(f"Imported/upserted {len(rows):,} scoring settings.")
                except Exception as e:
                    st.error("Import failed.")
                    st.exception(e)


elif page == "Race Lookup":
    st.header("🏁 Race Lookup")
    st.write("Search imported race results, open a race, and see the athletes/results stored for that race.")
    results, starts, athletes, overrides = prepare_dataframes()
    if results.empty:
        st.warning("No race results found. Import Athlete Results or Race Field Results first.")
        st.stop()

    summary = race_lookup_summary(results)
    if summary.empty:
        st.warning("No races found in the imported result tables.")
        st.stop()

    f1, f2, f3, f4 = st.columns([2.4, 1, 1.3, 1.2])
    race_search = f1.text_input("Search races", placeholder="Example: World Championship, T100, Oceanside, WTCS...")
    gender_filter = f2.selectbox("Gender", ["All", "Men", "Women", "Unknown"], index=0)
    race_family_filter = f3.selectbox("Race family", RANKING_FAMILIES, index=0)
    source_options = ["All"] + sorted([s for s in summary["Source"].dropna().astype(str).unique().tolist() if s])
    source_filter = f4.selectbox("Source", source_options, index=0)

    filtered_summary = filter_race_lookup(summary, race_search, gender_filter, race_family_filter, source_filter)
    m1, m2, m3 = st.columns(3)
    m1.metric("Races shown", f"{len(filtered_summary):,}")
    m2.metric("Total result rows", f"{int(filtered_summary['Rows'].sum()) if not filtered_summary.empty else 0:,}")
    m3.metric("Athlete rows", f"{int(filtered_summary['Athletes'].sum()) if not filtered_summary.empty else 0:,}")

    if filtered_summary.empty:
        st.info("No races match those filters.")
        st.stop()

    section_title("🔎", "Race Index")
    display_table(filtered_summary.head(250), ["Race Date", "Race", "Gender", "Race Type", "Source", "Athletes", "Rows", "SOF", "Max ORS"], height=360)

    selected_key = st.selectbox(
        "Open race",
        filtered_summary["_select_key"].tolist(),
        index=0,
        help="Pick one race/date/gender/source group to view the stored athletes.",
    )
    selected = filtered_summary[filtered_summary["_select_key"] == selected_key].iloc[0]
    participants = race_participants(results, selected)

    section_title("👥", f"Athletes in {selected.get('Race')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Athletes", f"{participants['Athlete URL'].fillna(participants['Athlete']).nunique() if not participants.empty else 0:,}")
    c2.metric("Rows", f"{len(participants):,}")
    c3.metric("SOF", selected.get("SOF") if selected.get("SOF") not in [None, ""] else "—")
    c4.metric("Source", selected.get("Source") or "—")
    display_table(
        participants,
        ["Athlete", "Gender", "Place", "ORS", "SOF", "Swim", "Bike", "Run", "Status", "Race Type", "Race Date", "Source", "Athlete URL"],
        height=520,
    )

elif page == "Start Lists":
    st.header("📋 Start Lists")
    st.write("Manage changing race start lists: search, remove athletes, or add athletes. CSV reuploads now live in Import CSVs.")
    results, starts, athletes, overrides = prepare_dataframes()
    if starts.empty:
        st.warning("No start lists found. Import a Start Lists CSV first.")
        st.stop()

    groups = start_list_group_summary(starts)
    if groups.empty:
        st.warning("No start-list groups found.")
        st.stop()

    f1, f2 = st.columns([2.4, 1])
    start_search = f1.text_input("Search start lists", placeholder="Example: WTCS, T100, Oceanside, World Championship...")
    start_gender = f2.selectbox("Gender", ["All", "Men", "Women", "Unknown"], index=0, key="start_list_gender_filter")
    filtered_groups = groups.copy()
    if start_search.strip():
        hay = (filtered_groups["Race"].fillna("").astype(str) + " " + filtered_groups["Gender"].fillna("").astype(str)).str.lower()
        filtered_groups = filtered_groups[hay.str.contains(re.escape(start_search.strip().lower()), na=False)]
    if start_gender != "All":
        filtered_groups = filtered_groups[filtered_groups["Gender"].eq(start_gender)]
    filtered_groups = filtered_groups.reset_index(drop=True)

    if filtered_groups.empty:
        st.info("No start lists match those filters.")
        st.stop()

    section_title("📚", "Imported Start Lists")
    display_table(filtered_groups.head(250), ["Race Date", "Race", "Gender", "Athletes", "Rows", "Duplicate Rows"], height=300)

    selected_key = st.selectbox("Manage start list", filtered_groups["_select_key"].tolist(), index=0)
    selected = filtered_groups[filtered_groups["_select_key"] == selected_key].iloc[0]
    race_name = selected.get("_race_name")
    race_date = selected.get("_race_date")
    gender = selected.get("_gender")
    current_rows = start_list_rows_for_group(starts, race_name, race_date, gender)
    current_rows = dedupe_start_athletes(current_rows) if not current_rows.empty else current_rows

    st.markdown(
        f"<div class='tri-race-card'><div class='eyebrow'>Selected Start List</div><h2>{race_name}</h2><div class='meta'>{gender} · {format_date(race_date)} · {len(current_rows):,} athletes</div></div>",
        unsafe_allow_html=True,
    )

    section_title("👥", "Current Athletes")
    display_table(current_rows, ["OpenRank", "Athlete", "Gender", "Race Date", "Race", "Athlete URL"], height=420)

    tab_remove, tab_add, tab_import = st.tabs(["Remove", "Add", "Import / Reupload"])

    with tab_remove:
        st.subheader("Remove athletes from this start list")
        if current_rows.empty:
            st.info("No athletes to remove.")
        else:
            remove_options = []
            option_to_idx = {}
            for idx, r in current_rows.iterrows():
                label = f"{clean_str(r.get('Athlete')) or clean_str(r.get('athlete_name')) or clean_str(r.get('Athlete URL')) or idx}"
                rank = clean_str(r.get("OpenRank") or r.get("open_rank"))
                if rank:
                    label = f"#{rank} · {label}"
                if label in option_to_idx:
                    label = f"{label} · row {idx}"
                remove_options.append(label)
                option_to_idx[label] = idx
            selected_remove = st.multiselect("Athletes to remove", remove_options)
            if st.button("Remove selected athletes", type="primary", disabled=not selected_remove):
                removed = 0
                for label in selected_remove:
                    idx = option_to_idx.get(label)
                    if idx is None:
                        continue
                    if delete_start_list_row(current_rows.loc[idx]):
                        removed += 1
                clear_cache()
                st.success(f"Removed {removed:,} athlete(s) from the start list.")
                st.info("Rebuild the model cache for this race after start-list edits.")
                st.rerun()

    with tab_add:
        st.subheader("Add one athlete")
        a1, a2 = st.columns([1.3, 2])
        new_name = a1.text_input("Athlete name")
        new_url = a2.text_input("Athlete URL", placeholder="https://protrinews.com/athletes/athlete-slug")
        new_rank = st.number_input("OpenRank", min_value=0, max_value=999999, value=0, help="Use 0/blank if unknown.")
        if st.button("Add athlete", type="primary"):
            ok, msg = add_start_list_athlete(race_name, race_date, gender, new_name, new_url, None if int(new_rank) == 0 else int(new_rank))
            if ok:
                st.success(msg)
                st.info("Rebuild the model cache for this race after start-list edits.")
                st.rerun()
            else:
                st.warning(msg)

    with tab_import:
        st.subheader("Update this start list from CSV")
        st.write("All CSV uploads now live in the Import Center so imports are easier to audit and maintain.")
        st.info("Click below to open Import CSVs with this race/date/gender preselected.")
        if st.button("Open Import CSVs for this start list", type="primary"):
            st.session_state["selected_start_list_for_import"] = {
                "race_name": race_name,
                "race_date": format_date(race_date),
                "gender": gender,
            }
            st.session_state["page_label"] = "📥 Import CSVs"
            st.rerun()

        with st.expander("Danger zone: delete this entire selected start list"):
            st.warning("This deletes only the selected race/date/gender start list rows.")
            confirm = st.checkbox("I understand this will delete the selected start list", key="confirm_delete_start_list")
            if st.button("Delete selected start list", disabled=not confirm):
                deleted_groups = delete_matching_start_lists([{"race_name": race_name, "race_date": format_date(race_date), "gender": gender}])
                clear_cache()
                st.success(f"Deleted {deleted_groups:,} start-list group(s).")
                st.rerun()


elif page == "Athletes":
    st.header("👤 Athletes")
    st.caption("This is the athlete master view. The app links start-list rows and race-result rows back to athletes by canonical athlete URL.")
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
    st.subheader("Athlete master sync")
    st.caption("Use this after older imports. It treats the athletes table as the master identity table, canonicalizes related athlete URLs, and fills missing related-table gender/name from athletes.gender and athletes.athlete_name.")
    if st.button("Sync related rows from athlete master"):
        sync_log = repair_related_rows_from_athlete_master()
        if sync_log.empty:
            st.info("No athlete master rows were available to sync.")
        else:
            st.success("Athlete master sync complete.")
            display_table(sync_log, list(sync_log.columns), height=180)

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
                help="Optional throttle so the cleanup tool does not send requests too fast. Use 0 for no pause on small permissioned batches; 0.25–0.75 is safer for larger batches.",
            )
        st.caption("Delay is optional. It is just a throttle between profile requests so this stays a controlled missing-only cleanup instead of sending requests too aggressively.")
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
    st.subheader("Manual gender overrides")
    st.info("Manual gender CSV uploads now live in Import CSVs → Gender Fixes so every CSV import is in one place.")
    if st.button("Open Import CSVs → Gender Fixes", type="primary"):
        st.session_state["page_label"] = "📥 Import CSVs"
        st.rerun()


elif page == "Model Cache":
    st.header("⚡ Model Cache")
    st.caption("Rebuild durable athlete scorecards. Rankings and race dashboards read these saved rows instead of recalculating live.")

    results, starts, athletes, overrides = prepare_dataframes()
    if results.empty:
        st.warning("No athlete results found. Import Athlete Results first.")
        st.stop()
    if not scorecard_tables_ready():
        st.error("Scorecard tables are missing. Run `athlete_scorecard_tables.sql` in Supabase SQL Editor first.")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profiles", len(RANKING_FAMILIES))
    c2.metric("Disciplines", len(SCORECARD_DISCIPLINES))
    c3.metric("Top scores used", TOP_SCORES_USED)
    c4.metric("Strong SOF", int(STRONG_SOF_THRESHOLD))

    rebuild_date = st.date_input("Scorecards as of", value=date.today(), key="scorecards_asof")
    st.info("Rebuild scorecards after importing new results or fixing athlete genders. Start-list edits usually do not require rebuilding scorecards unless new athletes/results were added.")

    col_a, col_b = st.columns([2, 1])
    if col_a.button("Rebuild all athlete scorecards", type="primary", width="stretch"):
        loader = loading_card("Building athlete scorecards", "Saving profile + discipline scores and top-5 evidence rows into Supabase...")
        try:
            logs = rebuild_all_athlete_scorecards(results, overrides, pd.Timestamp(rebuild_date))
        finally:
            loader.empty()
        st.success("Finished rebuilding athlete scorecards.")
        display_table(logs, ["Gender", "Profile", "Discipline", "Scorecard Rows", "Evidence Rows", "Status", "rows_after_gender", "rows_after_family", "athletes_ranked"], height=520)
        clear_cache()

    if col_b.button("Clear scorecards", width="stretch"):
        try:
            info = clear_scorecard_tables_for_rebuild()
            clear_cache()
            st.success(f"Cleared scorecard tables using {info.get('method', 'batch delete')}.")
        except Exception as e:
            st.error("Could not clear scorecard tables.")
            st.exception(e)

    try:
        cards = load_table("athlete_scorecards")
        ev = load_table("athlete_scorecard_evidence")
    except Exception:
        cards, ev = pd.DataFrame(), pd.DataFrame()
    c1, c2 = st.columns(2)
    c1.metric("Scorecard rows", f"{len(cards):,}")
    c2.metric("Evidence rows", f"{len(ev):,}")
    if not cards.empty:
        latest = cards.sort_values("computed_at", ascending=False).head(300) if "computed_at" in cards.columns else cards.head(300)
        display_table(latest, ["gender", "profile", "discipline", "rank", "athlete_name", "score", "evidence_count", "as_of_date", "computed_at"], height=520)
    else:
        st.info("No athlete_scorecards rows stored yet.")

elif page == "Athlete Rankings":
    st.header("🥇 Athlete Rankings")
    st.caption("Rankings read from the relational athlete_scorecards table. This page no longer loads raw result rows unless you click rebuild.")

    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.2, 1.0])
    ranking_gender = c1.selectbox("Gender", ["Men", "Women"], index=0)
    ranking_scope = c2.selectbox("Scorecard profile", RANKING_FAMILIES, index=0)
    ranking_view = c3.radio("View", ["🏆 Overall", "🏊 Swim", "🚴 Bike", "🏃 Run"], horizontal=True, key="athlete_rankings_view")
    c4.metric("Top scores used", TOP_SCORES_USED)
    view_kind = ranking_view_to_kind(ranking_view)

    if not scorecard_tables_ready():
        st.error("The relational scorecard tables are not installed yet. Run `athlete_scorecard_tables.sql` in Supabase SQL Editor, then rebuild scorecards.")
        st.stop()

    scorecard_df, score_meta = load_athlete_scorecard_display(ranking_gender, ranking_scope, view_kind, None)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Profile", ranking_scope)
    m2.metric("Discipline", view_kind.title())
    m3.metric("Rows", f"{len(scorecard_df):,}")
    m4.metric("As of", score_meta.get("as_of_date", "—"))

    b1, b2 = st.columns([1, 2])
    if b1.button("Rebuild this scorecard", type="primary", width="stretch"):
        results, _starts_unused, _athletes_unused, overrides = prepare_dataframes()
        if results.empty:
            st.warning("No athlete results found. Import Athlete Results first.")
        else:
            loader = loading_card("Rebuilding selected scorecard", f"{ranking_gender} · {ranking_scope} · {view_kind}")
            try:
                rows, ev_rows, metrics = save_athlete_scorecard_combo(results, overrides, ranking_gender, ranking_scope, pd.Timestamp(date.today()), view_kind, TOP_SCORES_USED)
            finally:
                loader.empty()
            st.success(f"Saved {rows:,} scorecard rows and {ev_rows:,} evidence rows.")
            st.json(metrics)
            st.rerun()
    b2.caption("This page does not recalculate rankings on every filter change. It reads saved scorecards for speed.")

    if scorecard_df.empty:
        st.warning("No saved scorecard rows found for this gender/profile/view. Use Rebuild this scorecard or Model Cache → Scorecards → Rebuild all scorecards.")
        st.stop()

    if view_kind == "overall":
        display_table(
            scorecard_df.head(100),
            ["Rank", "Athlete", "Score", "OpenRank Score", "Best Scores Used", "Current Year ORS", "Current Year Races", "Current Year Scored", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "Last Race", "Last Race Date", "Athlete URL"],
            height=650,
        )
    else:
        display_table(
            scorecard_df.head(100),
            ["Rank", "Athlete", "Score", "OpenRank Split Score", "Best Split Scores Used", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split", "Athlete URL"],
            height=650,
        )
    render_score_evidence(scorecard_df.head(10), f"{view_kind.title()} score evidence", limit=10)

elif page == "Database Viewer":
    st.header("🗄️ Database Viewer")
    table = st.selectbox("Table", ["athletes", "athlete_results", "race_field_results", "start_lists", "athlete_scorecards", "athlete_scorecard_evidence", "race_overrides", "scoring_settings", "model_cache", "model_runs", "split_audit"])
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
    if page == "Race Dashboard":
        # Fast path: the dashboard reads saved athlete_scorecards and the selected start list.
        # Do not load/normalize the full athlete_results + race_field_results tables here.
        starts = load_start_lists_light()
        results = pd.DataFrame()
        athletes = pd.DataFrame()
        overrides = pd.DataFrame()
    else:
        results, starts, athletes, overrides = prepare_dataframes()
    if starts.empty:
        st.warning("No start lists found. Import Start Lists first.")
        st.stop()
    if page != "Race Dashboard" and results.empty:
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
        top_n = TOP_SCORES_USED
        min_field_size = LOW_SAMPLE_WARNING_THRESHOLD
        strong_sof_threshold = STRONG_SOF_THRESHOLD
        st.caption(f"Model settings: top {TOP_SCORES_USED} scores · strong SOF {int(STRONG_SOF_THRESHOLD)}")

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

    prediction_scope = prediction_scope_from_race(selected_race, None, None)

    render_race_card(selected_race, selected_gender, selected_date, window_start)


    if page == "Race Dashboard":
        table_prediction, table_meta = build_race_prediction_from_scorecard_tables(starts, selected_race, selected_date, selected_gender)
        if table_prediction is not None and not table_prediction.empty:
            st.success("Loaded prediction from athlete_scorecards without scanning raw result tables.")
            display_cached_race_prediction(table_prediction, {"params": table_meta, "computed_at": max([v for k, v in table_meta.items() if k.endswith("_as_of_date")], default="")})
        else:
            st.warning("No saved scorecard prediction found for this race/profile. Rebuild athlete scorecards in ⚡ Model Cache after importing results or fixing athlete genders.")
        st.stop()

    # Use two full calendar years back through race day for Split Audit only.
    results_window_all = results[(results["race_date"].notna()) & (results["race_date"] >= window_start) & (results["race_date"] <= selected_date)].copy()
    results_window = apply_prediction_scope(results_window_all, prediction_scope)

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
        c5.metric("Model", f"Top {TOP_SCORES_USED} · SOF {int(STRONG_SOF_THRESHOLD)}")
        if prediction_scope == "Short Course / WTCS":
            st.info("Short-course / WTCS predictor uses WTCS, World Triathlon Cup, Olympic Games, and only high-SOF Olympic-distance continental/development races. Sprint / Super Sprint Continental Cup rows are excluded; 70.3, T100, and full-distance rows are not used.")
        elif prediction_scope == "IRONMAN 70.3 / Middle":
            st.info("70.3 predictor uses 70.3, T100/PTO, Challenge middle, full-distance swim/bike evidence, and elite Olympic-distance proof. Development Sprint / Super Sprint cup rows are excluded so weak short-course samples do not top the split boards.")

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
                    # Show ALL imported rows in the two-year analysis window, not only rows that passed the
                    # selected prediction profile. This is the fastest way to see whether a missing scorecard is
                    # caused by missing imports, missing split seconds, wrong gender, outside the 52-week scoring
                    # window, or a race-family filter.
                    raw_all = results_window_all[results_window_all["athlete_name"].fillna("").eq(athlete_filter)].copy()
                    if raw_all.empty:
                        st.info("No raw imported result rows found for this athlete in the full analysis window.")
                    else:
                        split_col = f"{disc}_seconds"
                        raw_all[f"{disc}_split"] = raw_all[split_col].map(format_seconds) if split_col in raw_all.columns else "—"
                        raw_all["Has Split"] = raw_all[split_col].notna() if split_col in raw_all.columns else False
                        raw_all["Profile Eligible"] = ranking_scope_mask(raw_all, prediction_scope)
                        trailing_start = selected_date - pd.Timedelta(days=365)
                        raw_all["Inside 52 Weeks"] = (raw_all["race_date"].notna()) & (raw_all["race_date"] >= trailing_start) & (raw_all["race_date"] <= selected_date)
                        raw_all["Gender Compatible"] = raw_all.apply(lambda rr: (normalize_gender(rr.get("gender")) == selected_gender) or pd.isna(rr.get("gender")) or race_gender_compatible(rr.get("race_name"), selected_gender), axis=1)
                        raw_all["Why Not Used"] = raw_all.apply(
                            lambda rr: "; ".join([x for x in [
                                None if bool(rr.get("Gender Compatible")) else "gender mismatch",
                                None if bool(rr.get("Profile Eligible")) else "outside selected profile",
                                None if bool(rr.get("Inside 52 Weeks")) else "outside trailing 52 weeks",
                                None if bool(rr.get("Has Split")) else f"missing {disc} split",
                                "bad status" if bool(rr.get("bad_status")) else None,
                            ] if x]) or "eligible for audit",
                            axis=1,
                        )
                        raw_all = raw_all.sort_values("race_date", ascending=False)
                        st.caption("This shows every imported row for the athlete in the full two-year analysis window. If only one row appears here, the app only has one imported result for that athlete. If rows appear but are not used, check the 'Why Not Used' column.")
                        display_table(
                            raw_all,
                            ["race_date", "race_name", "race_type", "distance", "place", "status", "gender", "sof", "sof_source", "ors", f"{disc}_split", "Has Split", "Profile Eligible", "Inside 52 Weeks", "Gender Compatible", "Why Not Used", "swim_seconds", "bike_seconds", "run_seconds"],
                            height=420,
                        )

