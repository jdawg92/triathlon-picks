import json
import math
import re
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Triathlon Picks", layout="wide")

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
    return pd.DataFrame(fetch_all(table_name))


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
    results = load_table("athlete_results")
    starts = load_table("start_lists")
    athletes = load_table("athletes")
    overrides = load_table("race_overrides")

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
        return 95 if discipline == "swim" else 92 if discipline == "bike" else 70
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
        return 0.95 if discipline == "swim" else 0.90 if discipline == "bike" else 0.55
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


def is_strong_split_evidence(row: pd.Series, discipline: str, strong_sof_threshold: float = 70.0) -> bool:
    """Return whether this split row should drive rankings.

    Strong evidence should be the races that actually translate to the target
    70.3 prediction. For split picks, full-distance swim/bike with good SOF is
    strong evidence. Full-distance run is useful but not strong by default
    because the marathon fatigue profile does not transfer cleanly to a 70.3
    half-marathon split.
    """
    rt = (clean_str(row.get("race_type")) or "").lower()
    sof = safe_float(row.get("sof"))

    if rt == "t100":
        return True

    if discipline == "swim" and rt == "wtcs":
        return True

    if rt == "full":
        return discipline in {"swim", "bike"} and sof is not None and sof >= strong_sof_threshold

    if sof is not None and sof >= strong_sof_threshold:
        return True

    return False


def evidence_quality_label(row: pd.Series, discipline: str, strong_sof_threshold: float = 70.0) -> str:
    rt = (clean_str(row.get("race_type")) or "").lower()
    sof = safe_float(row.get("sof"))
    if is_strong_split_evidence(row, discipline, strong_sof_threshold):
        if rt == "t100" or (discipline == "swim" and rt == "wtcs") or (sof is not None and sof >= 80):
            return "Premium"
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
                "strong_evidence": bool(
                    is_strong_split_evidence(pd.Series(r), discipline, 70.0)
                    and not split_status_excluded
                    and not draft_bike
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

    # Recompute the strong-evidence flag from the sidebar threshold. This is
    # intentionally stricter than "included". Included = usable evidence;
    # strong_evidence = evidence allowed to drive the top rankings.
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

        strong = recent_scored[recent_scored["strong_evidence"].astype(bool)].copy()
        medium_or_better = recent_scored[recent_scored["quality_tier"].isin(["Premium", "Strong", "Medium"])].copy()

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

        # Low-SOF / development-field rows can support the profile, but they
        # cannot be the main reason someone outranks Jamie/MVR-type athletes
        # with strong-field evidence. So top rankings are anchored to strong
        # rows first, then recent score, then all-row consistency.
        if strong_count > 0:
            final = (
                0.62 * strong_score
                + 0.18 * recent_score
                + 0.10 * (strong_top3_rate or 0) * 100
                + 0.04 * (strong_fastest_rate or 0) * 100
                + 0.06 * count_score
            )
        else:
            # No strong rows: useful but capped. This is where low-SOF wins and
            # short-course/development races land unless the athlete also has
            # high-SOF/T100/WTCS-swim proof.
            final = (
                0.45 * recent_score
                + 0.18 * all_top3_rate * 100
                + 0.07 * all_fastest_rate * 100
                + 0.05 * count_score
            )

        # Strong-field closeness gates. Being 8th but 1% down in a T100 swim is
        # better than winning a weak race, but being repeatedly 5%+ back in
        # strong fields should not rank high.
        if strong_avg_behind is not None:
            if strong_avg_behind > 6:
                final = min(final, 55)
            elif strong_avg_behind > 4:
                final = min(final, 68)
            elif strong_avg_behind > 2.5:
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

        # Strong-evidence confidence caps. One big race can be a strong signal,
        # but the top of the board should favor athletes with repeated proof.
        if strong_count == 0:
            # A couple of medium rows can lift this slightly, but still below
            # athletes with true strong-field evidence.
            cap = 58 if len(medium_or_better) >= 3 else 52
            final = min(final, cap)
            confidence = "Low - no strong-field proof"
        elif strong_count == 1:
            final = min(final, 70)
            confidence = "Medium - 1 strong row"
        elif strong_count == 2:
            confidence = "Good - 2 strong rows"
        else:
            confidence = "High - repeated strong proof"

        # Evidence-count confidence caps. A single validated split should not
        # rank beside athletes with several recent validated splits.
        if evidence_count <= 1:
            final = min(final, 45)
            confidence = "Low - 1 split"
        elif evidence_count == 2:
            final = min(final, 60)
            if strong_count < 2:
                confidence = "Low - 2 splits"
        elif evidence_count == 3 and strong_count == 0:
            final = min(final, 58)
            confidence = "Low - 3 weak/medium splits"

        best_row = recent_scored.sort_values(["evidence_score", "race_date"], ascending=[False, False]).head(1)
        last_row = recent.head(1)
        rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None,
            "Score": round(final, 1),
            "Confidence": confidence,
            "Strong Evidence Count": strong_count,
            "Evidence Count": evidence_count,
            "Strong Field Score": round(strong_score, 1),
            "Recent Score": round(recent_score, 1),
            "Strong Avg Behind %": None if strong_avg_behind is None else round(strong_avg_behind, 2),
            "Recent Avg Behind %": None if avg_behind is None else round(avg_behind, 2),
            "Strong Top 3 %": round((strong_top3_rate or 0) * 100, 1),
            "Strong Fastest %": round((strong_fastest_rate or 0) * 100, 1),
            "Recent Top 3 %": round(all_top3_rate * 100, 1),
            "Recent Fastest %": round(all_fastest_rate * 100, 1),
            "Last Race": clean_str(last_row["race_name"].iloc[0]) if not last_row.empty else "",
            "Last Race Date": format_date(last_row["race_date"].iloc[0]) if not last_row.empty else "",
            "Last Rank": clean_str(last_row["rank_display"].iloc[0]) if not last_row.empty else "",
            "Best Recent Split": clean_str(best_row["split"].iloc[0]) if not best_row.empty else "",
        })
    out = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
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
st.title("Triathlon Picks Dashboard")
st.caption("Supabase + Streamlit MVP")

with st.sidebar:
    page = st.radio(
        "Page",
        ["Race Dashboard", "Split Audit", "Import CSVs", "Database Viewer", "Connection"],
        index=0,
    )
    if st.button("Refresh database cache"):
        clear_cache()
        st.rerun()

if page == "Connection":
    st.header("Connection")
    try:
        result = supabase.table("athletes").select("id", count="exact").limit(1).execute()
        st.success("Connected to Supabase.")
        st.metric("Athletes", result.count or 0)

        st.subheader("Table counts")
        count_rows_data = []
        for table_name in ["athletes", "athlete_results", "start_lists", "race_overrides", "scoring_settings", "model_runs", "split_audit"]:
            count_rows_data.append({"Table": table_name, "Rows in Supabase": count_rows(table_name)})
        st.dataframe(pd.DataFrame(count_rows_data), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error("Could not read from Supabase. Make sure tables exist and secrets are correct.")
        st.exception(e)

elif page == "Import CSVs":
    st.header("Import Google Sheet CSV exports")
    st.write("Export each Google Sheet tab as CSV, then upload it here. Use replace mode for the first import.")
    replace = st.checkbox("Replace existing rows in selected table before importing", value=True)

    table_choice = st.selectbox("CSV type", ["Athlete Results", "Start Lists", "Race Overrides", "Scoring Settings"])
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

elif page == "Database Viewer":
    st.header("Database Viewer")
    table = st.selectbox("Table", ["athletes", "athlete_results", "start_lists", "race_overrides", "scoring_settings", "model_runs", "split_audit"])
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

    st.header(selected_race)
    st.caption(f"{selected_gender} · Race date {format_date(selected_date)} · Analysis window {format_date(window_start)} to {format_date(selected_date)}")

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

        st.subheader("Overall Picks")
        overall = score_overall(results_window, start_athletes, overrides, selected_date, target_year, recent_n, drop_worst)
        display_table(
            overall.head(15),
            ["Rank", "Athlete", "Score", "Recent Form ORS", "Current Year ORS", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "OpenRank", "Last Race", "Last Race Date"],
        )

        st.divider()
        st.info("Split ranks use each discipline's own recent valid split rows — not the athlete's top overall races. Swim uses recent swim evidence, bike uses recent bike evidence, and run uses recent run evidence. Full-distance swim/bike now count as high-value non-draft evidence; full-distance run is weighted lower because it transfers less directly to 70.3 speed. Imported sample coverage is still not the full ProTriNews field yet.")
        tabs = st.tabs(["Fastest Swim", "Fastest Bike", "Fastest Run"])
        for tab, disc, title in zip(tabs, ["swim", "bike", "run"], ["Fastest Swim", "Fastest Bike", "Fastest Run"]):
            with tab:
                st.subheader(title)
                scored = score_splits_for_start_list(audit_by_disc[disc], start_athletes, selected_date, recent_n, drop_worst, strong_sof_threshold)
                scored_top = scored.head(12).copy()
                selected_row = selectable_table(
                    scored_top,
                    ["Rank", "Athlete", "Score", "Confidence", "Strong Evidence Count", "Evidence Count", "Strong Field Score", "Strong Avg Behind %", "Strong Top 3 %", "Strong Fastest %", "Recent Avg Behind %", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split"],
                    key=f"split_pick_table_{disc}",
                )
                st.caption("Click an athlete row above to show the recent split rows used for that discipline. These are not the athlete's best overall races; each split is scored from its own swim/bike/run evidence.")

                if not scored_top.empty:
                    aud = audit_by_disc[disc]
                    fallback_athlete = scored_top["Athlete"].iloc[0]
                    selected_athlete = clean_str(selected_row.get("Athlete")) if selected_row is not None else fallback_athlete
                    selected_url = clean_str(selected_row.get("Athlete URL")) if selected_row is not None and "Athlete URL" in selected_row.index else None

                    # Fallback selector is still useful on mobile or if the row
                    # selection gets reset after Streamlit reruns.
                    athlete = st.selectbox(
                        f"Selected {title} athlete",
                        scored_top["Athlete"].tolist(),
                        index=max(0, scored_top["Athlete"].tolist().index(selected_athlete)) if selected_athlete in scored_top["Athlete"].tolist() else 0,
                        key=f"evidence_{disc}",
                    )
                    if athlete != selected_athlete:
                        selected_athlete = athlete
                        selected_url = clean_str(scored_top.loc[scored_top["Athlete"] == athlete, "Athlete URL"].iloc[0]) if "Athlete URL" in scored_top.columns and not scored_top.loc[scored_top["Athlete"] == athlete].empty else None

                    st.markdown(f"**Last 5 {disc} rows for {selected_athlete}**")
                    if aud.empty:
                        st.info("No audit rows for this athlete.")
                    else:
                        # Match by URL OR athlete name. Sometimes an imported CSV
                        # has a slightly different/missing URL even though the
                        # displayed athlete name is correct; using only URL made
                        # the evidence table look stuck on the previous athlete.
                        name_mask = aud["athlete_name"].fillna("").str.lower().eq(str(selected_athlete).lower())
                        if selected_url:
                            url_mask = aud["athlete_url"].astype(str).eq(selected_url)
                            mask = url_mask | name_mask
                        else:
                            mask = name_mask
                        athlete_audit = aud[mask].sort_values("race_date", ascending=False)
                        evidence_view = st.radio(
                            f"{selected_athlete} evidence rows",
                            ["Used in score", "All evaluated rows"],
                            horizontal=True,
                            key=f"evidence_view_{disc}_{selected_athlete}",
                        )
                        if evidence_view == "Used in score":
                            ev = athlete_audit[athlete_audit["included"]].head(5)
                        else:
                            ev = athlete_audit.head(8)
                        if ev.empty:
                            st.warning("No included split evidence found for the selected athlete. Switch to 'All evaluated rows' to see excluded DNF/DNS/DSQ, draft-legal, or invalid rows.")
                        display_table(
                            ev,
                            ["race_date", "race_name", "race_type", "quality_tier", "strong_evidence", "place", "status", "bad_status", "split_status_excluded", "sof", "sof_source", "sample_size", "split", "sample_rank_display", "pct_behind_fastest", "evidence_score", "final_cap", "included", "coverage_note", "reason"],
                        )

    else:
        st.subheader("Split Audit")
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
                ["athlete_name", "race_date", "race_name", "race_type", "quality_tier", "strong_evidence", "place", "status", "bad_status", "split_status_excluded", "sof", "sof_source", "sof_original", "sample_size", "field_source", "split", "sample_rank_display", "pct_behind_fastest", "gap_when_fastest_pct", "closeness_score", "rank_score", "raw_score", "sof_cap", "field_cap", "race_type_cap", "final_cap", "evidence_score", "evidence_weight", "included", "coverage_note", "reason"],
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

