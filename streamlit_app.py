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

# -----------------------------
# Supabase connection
# -----------------------------
@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# -----------------------------
# Helpers
# -----------------------------
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
    # Strip time zone/time if it came through from Sheets.
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
    # Values like 75%, 75.0, $75, or accidental commas.
    s = s.replace(",", "").replace("$", "").strip()
    is_percent = s.endswith("%")
    s = s.replace("%", "")
    # Reject obvious time strings for SOF/ORS.
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


def parse_split_seconds(value: Any, discipline: str, race_type: Optional[str] = None) -> Optional[int]:
    """Parse split values from Sheets/CSV into seconds.

    Rules:
    - Swim 21:28 = 21m28s.
    - Bike/70.3 run 1:10 = 1h10m.
    - Short-course/WTCS run 29:30 = 29m30s.
    - Reject impossible values with discipline/race-type ranges.
    """
    s = clean_str(value)
    if not s:
        return None

    # Reject obvious corrupted Sheets durations like 2028:00:00.
    if re.match(r"^\d{4,}:\d{2}:\d{2}$", s):
        return None

    s = s.strip()
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
                if "wtcs" in rt or "world triathlon" in rt or "sprint" in rt or "olympic" in rt:
                    # 29:30 = 29m30s. 1:02 in T100/70.3 should be h:mm, but short-course is m:ss.
                    if a >= 18:
                        seconds = a * 60 + b
                    else:
                        seconds = a * 3600 + b * 60
                else:
                    seconds = a * 3600 + b * 60
        elif len(parts) == 1:
            # Numeric seconds from a preprocessed export.
            n = parse_number(s)
            if n is not None:
                seconds = int(round(n))
    except Exception:
        return None

    if seconds is None:
        return None

    # Discipline/race validity filters. These are broad; scoring will refine later.
    rt = (race_type or "").lower()
    if discipline == "swim":
        if "full" in rt or "140.6" in rt:
            return seconds if 35 * 60 <= seconds <= 95 * 60 else None
        if "sprint" in rt or "world triathlon" in rt or "wtcs" in rt:
            return seconds if 5 * 60 <= seconds <= 20 * 60 else None
        return seconds if 12 * 60 <= seconds <= 65 * 60 else None

    if discipline == "bike":
        if "wtcs" in rt or "draft" in rt:
            return None
        if "full" in rt or "140.6" in rt:
            return seconds if 3 * 3600 <= seconds <= 6 * 3600 else None
        if "sprint" in rt or "world triathlon" in rt:
            return seconds if 15 * 60 <= seconds <= 90 * 60 else None
        return seconds if 90 * 60 <= seconds <= 4 * 3600 else None

    if discipline == "run":
        if "full" in rt or "140.6" in rt:
            return seconds if 2 * 3600 <= seconds <= 5 * 3600 else None
        if "sprint" in rt or "world triathlon" in rt or "wtcs" in rt:
            return seconds if 14 * 60 <= seconds <= 70 * 60 else None
        return seconds if 55 * 60 <= seconds <= 2 * 3600 else None

    return seconds


def normalize_race_type(race_name: Optional[str], race_type: Optional[str], distance: Optional[str]) -> Optional[str]:
    txt = " ".join([race_name or "", race_type or "", distance or ""]).lower()
    if "t100" in txt or "pto" in txt:
        return "T100"
    if "wtcs" in txt or "world triathlon championship series" in txt:
        return "WTCS"
    if "world triathlon cup" in txt:
        return "World Triathlon Cup"
    if "americas triathlon cup" in txt or "europe triathlon cup" in txt or "asia triathlon cup" in txt or "africa triathlon cup" in txt or "oceania triathlon cup" in txt:
        return "Continental Cup"
    if "challenge" in txt and "middle" in txt:
        return "Challenge Middle"
    if "challenge" in txt:
        return "Challenge Middle"
    if "140.6" in txt or "full" in txt or re.search(r"\bironman\b", txt) and "70.3" not in txt:
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


def read_uploaded_csv(uploaded_file) -> pd.DataFrame:
    # Try UTF-8, then fallback.
    try:
        return pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, encoding="latin-1")


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

# -----------------------------
# Normalizers
# -----------------------------
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
        gender = clean_str(first_col(r, ["Gender", "gender"]))
        status = parse_status(r)
        place = parse_place(first_col(r, ["Place", "Rank", "Finish Place", "place"]))

        # Skip fully blank rows.
        if not athlete_name and not athlete_url and not race_name:
            continue

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
            "swim_seconds": parse_split_seconds(first_col(r, ["Swim", "Swim Split", "swim"]), "swim", race_type),
            "bike_seconds": parse_split_seconds(first_col(r, ["Bike", "Bike Split", "bike"]), "bike", race_type),
            "run_seconds": parse_split_seconds(first_col(r, ["Run", "Run Split", "run"]), "run", race_type),
            "status": status,
            "raw": json_safe_row(r),
        }
        rows.append(rec)
        if athlete_url and athlete_name:
            athletes[athlete_url] = {
                "athlete_url": athlete_url,
                "athlete_name": athlete_name,
                "gender": gender,
            }
    return rows, list(athletes.values())


def normalize_start_lists(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = []
    athletes = {}
    for _, r in df.iterrows():
        athlete_url = clean_str(first_col(r, ["Athlete URL", "athlete_url", "Profile URL"]))
        athlete_name = clean_str(first_col(r, ["Athlete", "Athlete Name", "athlete_name", "Name"]))
        race_name = clean_str(first_col(r, ["Race", "Race Name", "race_name"]))
        race_date = parse_date_value(first_col(r, ["Race Date", "Date", "race_date"]))
        gender = clean_str(first_col(r, ["Gender", "gender"])) or "Men"
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
            athletes[athlete_url] = {
                "athlete_url": athlete_url,
                "athlete_name": athlete_name,
                "gender": gender,
            }
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

# -----------------------------
# UI
# -----------------------------
st.title("Triathlon Picks Dashboard")
st.caption("Supabase + Streamlit MVP")

with st.sidebar:
    page = st.radio("Page", ["Connection", "Import CSVs", "Database Viewer", "Next Dashboard Stub"], index=0)

if page == "Connection":
    st.success("Streamlit is running.")
    try:
        result = supabase.table("athletes").select("id", count="exact").limit(1).execute()
        st.success("Connected to Supabase and found the athletes table.")
        st.metric("Athletes table count", result.count or 0)
    except Exception as e:
        st.error("Could not read from Supabase. Make sure the SQL tables were created.")
        st.exception(e)

elif page == "Import CSVs":
    st.header("Import Google Sheet CSV exports")
    st.write("Export each Google Sheet tab as CSV, then upload it here. Use replace mode for the first import.")
    replace = st.checkbox("Replace existing rows in selected table before importing", value=True)

    table_choice = st.selectbox(
        "CSV type",
        ["Athlete Results", "Start Lists", "Race Overrides", "Scoring Settings"],
    )
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
                    st.success(f"Imported {len(rows):,} athlete result rows and upserted {len(athlete_rows):,} athletes.")

                elif table_choice == "Start Lists":
                    rows, athlete_rows = normalize_start_lists(df)
                    if replace:
                        delete_all("start_lists")
                    insert_chunks("start_lists", rows)
                    upsert_chunks("athletes", athlete_rows, on_conflict="athlete_url")
                    st.success(f"Imported {len(rows):,} start-list rows and upserted {len(athlete_rows):,} athletes.")

                elif table_choice == "Race Overrides":
                    rows = normalize_race_overrides(df)
                    if replace:
                        delete_all("race_overrides")
                    insert_chunks("race_overrides", rows)
                    st.success(f"Imported {len(rows):,} override rows.")

                elif table_choice == "Scoring Settings":
                    rows = normalize_scoring_settings(df)
                    if replace:
                        delete_all("scoring_settings")
                    # Upsert so editing CSV and reimporting updates values.
                    upsert_chunks("scoring_settings", rows, on_conflict="setting_group,setting_key")
                    st.success(f"Imported/upserted {len(rows):,} scoring settings.")

            except Exception as e:
                st.error("Import failed.")
                st.exception(e)

elif page == "Database Viewer":
    st.header("Database Viewer")
    table = st.selectbox("Table", ["athletes", "athlete_results", "start_lists", "race_overrides", "scoring_settings", "model_runs", "split_audit"])
    limit = st.slider("Rows", 10, 1000, 100)
    try:
        result = supabase.table(table).select("*").limit(limit).execute()
        data = result.data or []
        st.write(f"Showing {len(data):,} rows")
        st.dataframe(pd.DataFrame(data), use_container_width=True)
    except Exception as e:
        st.error("Could not load table.")
        st.exception(e)

else:
    st.header("Next Dashboard Stub")
    st.write("After importing Athlete Results and Start Lists, we will add the scoring dashboard here.")
    try:
        starts = supabase.table("start_lists").select("race_name,race_date,gender").limit(5000).execute().data or []
        if not starts:
            st.info("No start lists imported yet.")
        else:
            starts_df = pd.DataFrame(starts).drop_duplicates().sort_values(["race_date", "race_name", "gender"], na_position="last")
            st.dataframe(starts_df, use_container_width=True)
    except Exception as e:
        st.exception(e)
