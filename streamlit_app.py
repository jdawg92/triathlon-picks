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

        # Guarantee split columns exist and recover missing values from raw CSV payloads.
        # This avoids needing to re-import if the first importer missed a split value.
        for disc in ["swim", "bike", "run"]:
            col = f"{disc}_seconds"
            if col not in results.columns:
                results[col] = np.nan
            results[col] = pd.to_numeric(results[col], errors="coerce")
            missing = results[col].isna()
            if missing.any() and "raw" in results.columns:
                results.loc[missing, col] = results[missing].apply(lambda r, d=disc: recover_split_from_raw(r, d), axis=1)
            results[col] = pd.to_numeric(results[col], errors="coerce")

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
        return 75 if discipline in {"swim", "bike"} else 70
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
        return 0.75 if discipline in {"swim", "bike"} else 0.70
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
    split_col = f"{discipline}_seconds"
    if results.empty or split_col not in results.columns:
        return pd.DataFrame()

    # Same-gender only when known. Unknown-gender rows are allowed when the race
    # name does not clearly indicate the opposite gender. This prevents partial
    # imported fields from collapsing to 1-2 athletes and making Included only blank.
    start_urls = set(start_athletes["athlete_url"].dropna().astype(str).tolist()) if "athlete_url" in start_athletes else set()
    df = results.copy()
    df = df[(df["race_date"].notna()) & (df["race_date"] <= target_date)]
    df = df[(df[split_col].notna()) & (~df["bad_status"])]

    gender_known_match = df["gender"].eq(gender)
    gender_unknown_ok = df["gender"].isna() & df["race_name"].map(lambda x: race_gender_compatible(x, gender))
    start_list_match = df["athlete_url"].isin(start_urls)
    df = df[gender_known_match | gender_unknown_ok | start_list_match]

    if discipline == "bike":
        df = df[~df["race_type"].fillna("").str.lower().str.contains("wtcs|world triathlon|continental|draft")]

    if df.empty:
        return pd.DataFrame()

    df["race_key"] = df.apply(race_key, axis=1)
    audit_rows = []

    for _, g in df.groupby("race_key"):
        g = g.copy().sort_values(split_col, ascending=True)
        # Re-rank after filtering invalid rows.
        fastest = safe_float(g[split_col].min())
        if fastest is None or fastest <= 0:
            continue
        field_size = len(g)
        if field_size < min_field_size:
            # still show in audit as excluded
            pass
        sorted_splits = g[split_col].dropna().sort_values().tolist()
        second = sorted_splits[1] if len(sorted_splits) > 1 else None

        for idx, (_, r) in enumerate(g.iterrows(), start=1):
            split_sec = safe_float(r.get(split_col))
            if split_sec is None:
                continue
            pct_behind = ((split_sec - fastest) / fastest) * 100
            gap_second = None
            if idx == 1 and second:
                gap_second = ((second - fastest) / fastest) * 100
            rs = rank_score(idx, field_size)
            cs = closeness_score(pct_behind, discipline)
            ds = dominance_score(gap_second, discipline)
            raw_score = 0.70 * cs + 0.20 * rs + 0.10 * ds
            rt = clean_str(r.get("race_type")) or "Unknown"
            s_cap = sof_cap(r.get("sof"), rt, discipline)
            f_cap = field_cap(field_size)
            t_cap = race_type_cap(rt, discipline)
            final_cap = min(s_cap, f_cap, t_cap)
            # Include any valid race-relative sample with at least two athletes.
            # Small fields are handled by low field caps/weights instead of being
            # hidden completely. The min_field_size slider is now informational
            # for low-sample warnings, not a hard include/exclude gate.
            included = field_size >= 2 and final_cap > 0

            excluded_override, override_mult, override_reason = match_override(r, overrides, discipline)
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
            if field_size < 2:
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
                "sof": safe_float(r.get("sof")),
                "field_size": field_size,
                "split_seconds": int(split_sec),
                "split": format_seconds(split_sec),
                "split_rank": idx,
                "rank_display": f"{idx}/{field_size}",
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
                "included": bool(included),
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

        scores = recent_scored["evidence_score"].astype(float).tolist()
        weights = recent_scored["evidence_weight"].astype(float).tolist()
        recent_score = weighted_avg(scores, weights) or 0
        strong = recent_scored[(recent_scored["sof"].fillna(0) >= strong_sof_threshold) | (recent_scored["race_type"].isin(["T100", "WTCS"]))]
        strong_score = weighted_avg(strong["evidence_score"].astype(float).tolist(), strong["evidence_weight"].astype(float).tolist()) if not strong.empty else 0
        top3_rate = weighted_avg((recent_scored["split_rank"] <= 3).astype(float).tolist(), weights) or 0
        fastest_rate = weighted_avg((recent_scored["split_rank"] == 1).astype(float).tolist(), weights) or 0
        avg_behind = weighted_avg(recent_scored["pct_behind_fastest"].astype(float).tolist(), weights)
        evidence_count = len(recent_scored)
        count_score = min(100, evidence_count / 5 * 100)

        # Recent form is the anchor. Strong-field score matters, but no single cherry-picked race can dominate.
        final = (
            0.45 * recent_score
            + 0.30 * strong_score
            + 0.12 * top3_rate * 100
            + 0.05 * fastest_rate * 100
            + 0.08 * count_score
        )

        # Recent gates: if the athlete is consistently not close, cap the score.
        if avg_behind is not None:
            if avg_behind > 8:
                final = min(final, 45)
            elif avg_behind > 5:
                final = min(final, 60)
            elif avg_behind > 3.5:
                final = min(final, 72)

        # If no recent top-5 and not close by percentage, cap hard.
        if len(recent_scored) and not (recent_scored["split_rank"] <= 5).any() and (avg_behind is None or avg_behind > 2.5):
            final = min(final, 50)

        best_row = recent_scored.sort_values(["evidence_score", "race_date"], ascending=[False, False]).head(1)
        last_row = recent.head(1)
        rows.append({
            "Athlete": g["athlete_name"].dropna().iloc[0] if g["athlete_name"].notna().any() else athlete_key,
            "Athlete URL": g["athlete_url"].dropna().iloc[0] if g["athlete_url"].notna().any() else None,
            "Score": round(final, 1),
            "Recent Score": round(recent_score, 1),
            "Strong Field Score": round(strong_score, 1),
            "Recent Avg Behind %": None if avg_behind is None else round(avg_behind, 2),
            "Recent Top 3 %": round(top3_rate * 100, 1),
            "Recent Fastest %": round(fastest_rate * 100, 1),
            "Evidence Count": evidence_count,
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


def display_table(df: pd.DataFrame, columns: List[str], height: Optional[int] = None):
    if df is None or df.empty:
        st.info("No data to show.")
        return

    show = df[[c for c in columns if c in df.columns]].copy()

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
                    if replace:
                        delete_all("athlete_results")
                    insert_chunks("athlete_results", rows)
                    upsert_chunks("athletes", athlete_rows, on_conflict="athlete_url")
                    clear_cache()
                    st.success(f"Imported {len(rows):,} athlete result rows and upserted {len(athlete_rows):,} athletes.")

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
    limit = st.slider("Rows", 10, 5000, 500)
    try:
        df = pd.DataFrame(fetch_all(table, page_size=1000)).head(limit)
        st.write(f"Showing {len(df):,} rows")
        st.dataframe(df, use_container_width=True)
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
        c4.metric("Low-sample threshold", min_field_size)

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
            st.caption("Included rows now require at least two same-race split rows. Small fields are included but capped/weighted down. If included start-list rows are 0, check split parsing, athlete URL/name matching, or DNF/status filters.")

        st.subheader("Overall Picks")
        overall = score_overall(results_window, start_athletes, overrides, selected_date, target_year, recent_n, drop_worst)
        display_table(
            overall.head(15),
            ["Rank", "Athlete", "Score", "Recent Form ORS", "Current Year ORS", "Best Recent ORS", "Strong Field ORS", "Recent Races Used", "OpenRank", "Last Race", "Last Race Date"],
        )

        st.divider()
        tabs = st.tabs(["Fastest Swim", "Fastest Bike", "Fastest Run"])
        for tab, disc, title in zip(tabs, ["swim", "bike", "run"], ["Fastest Swim", "Fastest Bike", "Fastest Run"]):
            with tab:
                st.subheader(title)
                scored = score_splits_for_start_list(audit_by_disc[disc], start_athletes, selected_date, recent_n, drop_worst, strong_sof_threshold)
                scored_top = scored.head(12).copy()
                selected_row = selectable_table(
                    scored_top,
                    ["Rank", "Athlete", "Score", "Recent Score", "Strong Field Score", "Recent Avg Behind %", "Recent Top 3 %", "Recent Fastest %", "Evidence Count", "Last Race", "Last Race Date", "Last Rank", "Best Recent Split"],
                    key=f"split_pick_table_{disc}",
                )
                st.caption("Click an athlete row above to show their last 5 valid split rows. Score is based on recent race-relative split performance; % behind fastest is the main metric.")

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
                        if selected_url:
                            mask = aud["athlete_url"].astype(str).eq(selected_url)
                        else:
                            mask = aud["athlete_name"].fillna("").str.lower().eq(str(selected_athlete).lower())
                        ev = aud[mask].sort_values("race_date", ascending=False).head(5)
                        display_table(
                            ev,
                            ["race_date", "race_name", "race_type", "sof", "field_size", "split", "rank_display", "pct_behind_fastest", "evidence_score", "final_cap", "included", "reason"],
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
                ["athlete_name", "race_date", "race_name", "race_type", "sof", "field_size", "split", "rank_display", "pct_behind_fastest", "gap_when_fastest_pct", "closeness_score", "rank_score", "raw_score", "sof_cap", "field_cap", "race_type_cap", "final_cap", "evidence_score", "evidence_weight", "included", "reason"],
                height=650,
            )

