import json
import math
import re
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
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
    """Polished dark UI styling for the Streamlit dashboard."""
    st.markdown(
        """
        <style>
        :root {
            --ptn-bg: #070B12;
            --ptn-panel: rgba(18, 24, 38, 0.88);
            --ptn-panel-2: rgba(23, 31, 48, 0.92);
            --ptn-border: rgba(148, 163, 184, 0.18);
            --ptn-text: #E5ECF8;
            --ptn-muted: #94A3B8;
            --ptn-red: #EF4444;
            --ptn-orange: #F97316;
            --ptn-blue: #38BDF8;
            --ptn-green: #22C55E;
            --ptn-purple: #8B5CF6;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 30rem),
                radial-gradient(circle at top right, rgba(239, 68, 68, 0.12), transparent 28rem),
                linear-gradient(135deg, #050816 0%, #08111F 45%, #070B12 100%);
            color: var(--ptn-text);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(8, 13, 25, 0.98), rgba(15, 23, 42, 0.98));
            border-right: 1px solid var(--ptn-border);
        }

        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p {
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
            width: 2.25rem;
            height: 2.25rem;
            border-radius: 0.8rem;
            margin-right: 0.5rem;
            background: linear-gradient(135deg, var(--ptn-red), var(--ptn-orange));
            box-shadow: 0 0 30px rgba(239, 68, 68, 0.35);
        }

        .ptn-sidebar-brand .title {
            font-weight: 800;
            font-size: 1.05rem;
            letter-spacing: -0.02em;
        }

        .ptn-sidebar-brand .subtitle {
            color: var(--ptn-muted);
            font-size: 0.78rem;
            margin-top: 0.15rem;
        }

        .ptn-hero {
            padding: 1.35rem 1.5rem;
            border: 1px solid var(--ptn-border);
            border-radius: 1.25rem;
            background:
                linear-gradient(135deg, rgba(239, 68, 68, 0.16), rgba(56, 189, 248, 0.08)),
                rgba(15, 23, 42, 0.82);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
            margin: 0.25rem 0 1.2rem 0;
        }

        .ptn-hero .eyebrow, .ptn-race-card .eyebrow {
            color: #FCA5A5;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .ptn-hero h1 {
            font-size: 2.15rem;
            line-height: 1.05;
            margin: 0;
            letter-spacing: -0.04em;
        }

        .ptn-hero p {
            color: var(--ptn-muted);
            margin: 0.55rem 0 0 0;
            font-size: 1rem;
        }

        .ptn-race-card {
            padding: 1.15rem 1.25rem;
            border: 1px solid var(--ptn-border);
            border-radius: 1.15rem;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 41, 59, 0.72));
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
            margin: 0.35rem 0 1rem 0;
        }

        .ptn-race-card h2 {
            margin: 0;
            font-size: 1.55rem;
            letter-spacing: -0.03em;
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
            font-weight: 800;
            font-size: 1.3rem;
            letter-spacing: -0.02em;
            margin: 1.25rem 0 0.7rem 0;
        }

        .ptn-pill {
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            color: #FEE2E2;
            background: rgba(239, 68, 68, 0.16);
            border: 1px solid rgba(239, 68, 68, 0.26);
        }

        [data-testid="stMetric"] {
            background: rgba(15, 23, 42, 0.78);
            border: 1px solid var(--ptn-border);
            border-radius: 1rem;
            padding: 0.9rem 1rem;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.18);
        }

        [data-testid="stMetricLabel"] p {
            color: var(--ptn-muted) !important;
            font-weight: 700;
        }

        [data-testid="stMetricValue"] {
            color: var(--ptn-text);
            font-weight: 900;
        }

        .stDataFrame, [data-testid="stDataFrame"] {
            border-radius: 1rem;
            overflow: hidden;
            border: 1px solid var(--ptn-border);
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--ptn-border);
            border-radius: 1rem;
            background: rgba(15, 23, 42, 0.56);
            overflow: hidden;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }

        .stTabs [data-baseweb="tab"] {
            height: 2.75rem;
            border-radius: 999px;
            padding: 0 1rem;
            background: rgba(15, 23, 42, 0.68);
            border: 1px solid var(--ptn-border);
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.26), rgba(249, 115, 22, 0.18));
            border-color: rgba(248, 113, 113, 0.55);
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 999px;
            border: 1px solid rgba(248, 113, 113, 0.45);
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.9), rgba(249, 115, 22, 0.9));
            color: white;
            font-weight: 800;
            box-shadow: 0 10px 30px rgba(239, 68, 68, 0.25);
        }

        .stSelectbox, .stSlider, .stRadio, .stFileUploader, .stCheckbox {
            color: var(--ptn-text);
        }

        div[data-testid="stAlert"] {
            border-radius: 1rem;
            border: 1px solid var(--ptn-border);
        }

        h1, h2, h3 {
            letter-spacing: -0.03em;
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

# ============================================================
# CSV normalizers
# ============================================================
def normalize_athlete_results(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = []
    athletes = {}
    for _, r in df.iterrows():
        athlete_url = clean_str(first_col(r, ["Athlete URL", "athlete_url", "Source URL", "Profile URL"]))
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
            "sof": parse_number(first_col(r, ["SOF", "Strength of Field", "sof"])),
            "ors": parse_number(first_col(r, ["ORS", "Score", "ors"])),
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
        athlete_url = clean_str(first_col(r, ["Athlete URL", "athlete_url", "Profile URL"]))
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
            "athlete_url": clean_str(first_col(r, ["Athlete URL", "athlete_url", "Profile URL"])),
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
def prepare_dataframes() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    athlete_results = load_table("athlete_results")
    race_field_results = load_table("race_field_results")
    starts = load_table("start_lists")
    athletes = load_table("athletes")
    overrides = load_table("race_overrides")

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
            dedupe_cols = [c for c in ["athlete_url", "athlete_name", "race_date", "race_name", "race_type"] if c in results.columns]
            if dedupe_cols:
                results = results.sort_values("_source_priority").drop_duplicates(subset=dedupe_cols, keep="first")
            results = results.drop(columns=["_source_priority"], errors="ignore")
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
            u = clean_str(r.get("athlete_url"))
            n = clean_str(r.get("athlete_name"))
            if u:
                gender_map[u] = g
            if n:
                name_gender_map[n.lower()] = g

    if not results.empty:
        results["race_date"] = pd.to_datetime(results["race_date"], errors="coerce")
        results["gender"] = results.apply(
            lambda r: normalize_gender(r.get("gender"))
            or gender_map.get(clean_str(r.get("athlete_url")) or "")
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
    recent_n: int,
    drop_worst: int,
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
        recent = g.head(recent_n).copy()
        if len(recent) > drop_worst + 2 and drop_worst > 0:
            # Drop worst by evidence score so one bad/mechanical day doesn't wreck the current estimate.
            drop_idx = recent.sort_values("evidence_score", ascending=True).head(drop_worst).index
            recent_scored = recent.drop(index=drop_idx)
        else:
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
    recent_n: int,
    drop_worst: int,
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

    start_lookup = start_athletes.set_index("athlete_url", drop=False).to_dict("index") if "athlete_url" in start_athletes else {}
    name_start_lookup = {str(r.get("athlete_name", "")).lower(): r for _, r in start_athletes.iterrows()}
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
        recent = gg.head(recent_n).copy()
        if len(recent) > drop_worst + 2 and drop_worst > 0:
            drop_idx = recent.sort_values("ors", ascending=True).head(drop_worst).index
            recent_scored = recent.drop(index=drop_idx)
        else:
            recent_scored = recent
        current_year = gg[gg["race_date"].dt.year == target_year]
        strong = recent_scored[(recent_scored["sof"].fillna(0) >= 70) | (recent_scored["race_type"].isin(["T100", "WTCS"]))]

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

        final = 0.45 * recent_score + 0.25 * current_year_score + 0.15 * best_recent + 0.10 * strong_score + 0.05 * open_rank_score
        rows.append({
            "Athlete": name,
            "Athlete URL": url,
            "Score": round(final, 1),
            "Recent Form ORS": round(recent_score, 1),
            "Current Year ORS": round(current_year_score, 1) if current_year_score is not None else None,
            "Best Recent ORS": round(best_recent, 1),
            "Strong Field ORS": round(strong_score, 1),
            "Recent Races Used": len(recent_scored),
            "OpenRank": open_rank,
            "Last Race": clean_str(recent.iloc[0].get("race_name")) if len(recent) else "",
            "Last Race Date": format_date(recent.iloc[0].get("race_date")) if len(recent) else "",
        })
    out = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
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
        "final_cap", "SOF", "ORS", "Score"
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
        "use_container_width": True,
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
        "use_container_width": True,
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
        st.dataframe(show, use_container_width=True, hide_index=True)
    return None

# ============================================================
# UI
# ============================================================
apply_dashboard_theme()

PAGE_OPTIONS = {
    "🏆 Race Dashboard": "Race Dashboard",
    "🥇 Athlete Rankings": "Athlete Rankings",
    "👤 Athletes": "Athletes",
    "🔎 Split Audit": "Split Audit",
    "📥 Import CSVs": "Import CSVs",
    "🗄️ Database Viewer": "Database Viewer",
    "🔌 Connection": "Connection",
}

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
    page_label = st.radio(
        "Navigation",
        list(PAGE_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    page = PAGE_OPTIONS[page_label]
    st.markdown("---")
    if st.button("🔄 Refresh database cache", use_container_width=True):
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
        st.dataframe(pd.DataFrame(count_rows_data), use_container_width=True, hide_index=True)
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
        st.dataframe(df.head(20), use_container_width=True)
        st.write(f"Rows detected: {len(df):,}")

        if st.button(f"Import {table_choice}", type="primary"):
            try:
                if table_choice == "Athlete Results":
                    rows, athlete_rows = normalize_athlete_results(df)
                    before_count = count_rows("athlete_results")
                    if replace:
                        delete_all("athlete_results")
                    insert_chunks("athlete_results", rows)
                    upsert_chunks("athletes", athlete_rows, on_conflict="athlete_url")
                    clear_cache()
                    after_count = count_rows("athlete_results")
                    st.success(f"Imported {len(rows):,} athlete result rows and upserted {len(athlete_rows):,} athletes.")
                    st.info(f"Supabase athlete_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")

                elif table_choice == "Race Field Results":
                    rows, athlete_rows = normalize_race_field_results(df)
                    before_count = count_rows("race_field_results")
                    if replace:
                        delete_all("race_field_results")
                    insert_chunks("race_field_results", rows)
                    upsert_chunks("athletes", athlete_rows, on_conflict="athlete_url")
                    clear_cache()
                    after_count = count_rows("race_field_results")
                    st.success(f"Imported {len(rows):,} race-field result rows and upserted {len(athlete_rows):,} athletes.")
                    st.info(f"Supabase race_field_results count: before {before_count if before_count is not None else 'unknown'} → after {after_count if after_count is not None else 'unknown'}")

                elif table_choice == "Start Lists":
                    rows, athlete_rows = normalize_start_lists(df)
                    if replace:
                        delete_all("start_lists")
                    insert_chunks("start_lists", rows)
                    upsert_chunks("athletes", athlete_rows, on_conflict="athlete_url")
                    clear_cache()
                    st.success(f"Imported {len(rows):,} start-list rows and upserted {len(athlete_rows):,} athletes.")

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

elif page == "Athlete Rankings":
    st.header("🥇 Athlete Rankings")
    results, starts, athletes, overrides = prepare_dataframes()
    if results.empty:
        st.warning("No athlete results found. Import Athlete Results first.")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    ranking_gender = c1.selectbox("Gender", ["Men", "Women"], index=0)
    as_of = c2.date_input("As of date", value=date.today())
    recent_n_rank = c3.slider("Recent races used", 3, 8, 5, key="rank_recent_n")
    drop_worst_rank = c4.slider("Drop worst", 0, 2, 1, key="rank_drop_worst")
    as_of_ts = pd.Timestamp(as_of)
    year = int(as_of_ts.year)
    window_start_rank = pd.Timestamp(date(year - 2, 1, 1))
    ranking_results = results[(results["race_date"].notna()) & (results["race_date"] >= window_start_rank) & (results["race_date"] <= as_of_ts)].copy()
    ranking_results = ranking_results[(ranking_results["gender"].eq(ranking_gender)) | ranking_results["gender"].isna()]

    # Build an all-athlete candidate list from imported rows for this gender/window.
    candidate_cols = ["athlete_url", "athlete_name", "gender"]
    start_all = ranking_results[candidate_cols].drop_duplicates().dropna(subset=["athlete_name"]).copy()
    start_all["race_name"] = "Global Rankings"
    start_all["race_date"] = as_of_ts
    start_all["open_rank"] = None

    tabs = st.tabs(["🏆 Overall", "🏊 Swim", "🚴 Bike", "🏃 Run"])
    with tabs[0]:
        overall_all = score_overall(ranking_results, start_all, overrides, as_of_ts, year, recent_n_rank, drop_worst_rank)
        display_table(overall_all.head(50), ["Rank", "Athlete", "Score", "Recent Form ORS", "Current Year ORS", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "Last Race", "Last Race Date", "Athlete URL"], height=620)
    for tab, disc in zip(tabs[1:], ["swim", "bike", "run"]):
        with tab:
            aud = build_split_audit(ranking_results, start_all, overrides, as_of_ts, ranking_gender, disc, min_field_size=5)
            scored = score_splits_for_start_list(aud, start_all, as_of_ts, recent_n_rank, drop_worst_rank, strong_sof_threshold=70)
            display_table(scored.head(50), ["Rank", "Athlete", "Score", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Premium Field Score", "Strong Field Score", "Premium Avg Behind %", "Strong Avg Behind %", "Recent Avg Behind %", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split", "Athlete URL"], height=620)

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
        st.dataframe(df_all.head(limit), use_container_width=True)
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
        recent_n = st.slider("Recent races used", 3, 8, 5)
        drop_worst = st.slider("Drop worst recent result", 0, 2, 1)
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

    # Use two full calendar years back through race day.
    results_window = results[(results["race_date"].notna()) & (results["race_date"] >= window_start) & (results["race_date"] <= selected_date)].copy()

    render_race_card(selected_race, selected_gender, selected_date, window_start)

    audit_by_disc = {
        disc: build_split_audit(results_window, start_athletes, overrides, selected_date, selected_gender, disc, min_field_size)
        for disc in ["swim", "bike", "run"]
    }

    if page == "Race Dashboard":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Start list athletes", len(start_athletes))
        c2.metric("Result rows in window", len(results_window))
        c3.metric("Overrides", len(overrides) if not overrides.empty else 0)
        c4.metric("Low-sample warning threshold", min_field_size)

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
                health.append({
                    "Discipline": disc,
                    "Valid result rows in window": valid_rows,
                    "Audit rows": audit_rows,
                    "Included audit rows": included_rows,
                    "Included start-list rows": start_included,
                })
            st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
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
        overall = score_overall(results_window, start_athletes, overrides, selected_date, target_year, recent_n, drop_worst)
        display_table(
            overall.head(15),
            ["Rank", "Athlete", "Score", "Recent Form ORS", "Current Year ORS", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "OpenRank", "Last Race", "Last Race Date"],
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
        st.info("Split ranks use each discipline's own recent valid split rows — not the athlete's top overall races. Swim uses recent swim evidence, bike uses recent bike evidence, and run uses recent run evidence. Full-distance swim/bike now count as high-value non-draft evidence; full-distance run is weighted lower because it transfers less directly to 70.3 speed. Imported sample coverage is still not the full ProTriNews field yet.")
        tabs = st.tabs(["🏊 Fastest Swim", "🚴 Fastest Bike", "🏃 Fastest Run"])
        for tab, disc, title in zip(tabs, ["swim", "bike", "run"], ["Fastest Swim", "Fastest Bike", "Fastest Run"]):
            with tab:
                section_title("🏊" if disc == "swim" else "🚴" if disc == "bike" else "🏃", title)
                scored = score_splits_for_start_list(audit_by_disc[disc], start_athletes, selected_date, recent_n, drop_worst, strong_sof_threshold)
                scored_top = scored.head(12).copy()
                display_table(
                    scored_top,
                    ["Rank", "Athlete", "Score", "Confidence", "Premium Evidence Count", "Strong Evidence Count", "Evidence Count", "Premium Field Score", "Strong Field Score", "Premium Avg Behind %", "Strong Avg Behind %", "Premium Top 3 %", "Strong Top 3 %", "Recent Avg Behind %", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split"],
                    height=360,
                )
                st.caption("Open an athlete below to see the exact recent split rows used for this discipline. These are not the athlete's best overall races; each split is scored from its own swim/bike/run evidence.")

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

