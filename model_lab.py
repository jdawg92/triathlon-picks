#!/usr/bin/env python3
"""Fast local model lab for Triathlon Picks.

Why this exists
---------------
Do not tune rankings by committing, waiting for Streamlit Cloud, clicking pages,
and rebuilding cache. That loop is too slow.

This script runs the scoring model locally against the already-built Supabase
`scoring_result_pool`, writes CSV outputs, and lets you inspect rankings/evidence
in seconds.

Typical use
-----------
First run, pull fresh local cache from Supabase:

    python model_lab.py --refresh

Then tune score_engine.py and rerun without refetching data:

    python model_lab.py --profile "Long Course / 70.3 + T100" --gender Men

Test a start-list race:

    python model_lab.py --race "World Triathlon" --gender Men --profile "Short Course / WTCS"

Build all slices locally:

    python model_lab.py --all-slices

Outputs go to:

    model_lab_outputs/

This script is read-only. It does not save scorecards back to Supabase.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from model_lab_config import (
        DEFAULT_AS_OF_DATE,
        DEFAULT_GENDER,
        DEFAULT_PROFILE,
        DEFAULT_TOP_N_EVIDENCE,
        DEFAULT_TOP_ROWS,
        EXPECTATIONS,
        MODEL_VERSION,
        WATCHLIST,
    )
except Exception:
    DEFAULT_AS_OF_DATE = "2026-06-17"
    DEFAULT_GENDER = "Men"
    DEFAULT_PROFILE = "Long Course / 70.3 + T100"
    DEFAULT_TOP_N_EVIDENCE = 4
    DEFAULT_TOP_ROWS = 40
    MODEL_VERSION = "score_engine_v11_wtcs_sof_watchcards"
    WATCHLIST = []
    EXPECTATIONS = {}

try:
    from score_engine import (
        DISCIPLINES,
        PROFILES,
        build_all_scorecards,
        build_scorecard_slice,
        prep_results,
    )
except Exception as exc:
    raise RuntimeError(
        "Could not import score_engine.py. Make sure model_lab.py is in the repo "
        "next to score_engine.py and that score_engine.py exports DISCIPLINES, "
        "PROFILES, prep_results, build_scorecard_slice, and build_all_scorecards."
    ) from exc


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "model_lab_cache"
OUT_DIR = ROOT / "model_lab_outputs"

SCORING_POOL_CACHE = CACHE_DIR / "scoring_result_pool.pkl"
START_LIST_CACHE = CACHE_DIR / "start_lists.pkl"


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def _slug(text: Any, max_len: int = 80) -> str:
    s = str(text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return (s[:max_len].strip("_") or "output")


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
    if s.startswith("m"):
        return "Men"
    if s.startswith("w") or s.startswith("f"):
        return "Women"
    return _clean(value)


def _canonical_url(value: Any) -> str:
    s = _clean(value)
    if not s:
        return ""
    s = s.split("?")[0].rstrip("/")
    s = s.replace("https://protrinews.com/en/athletes/", "https://protrinews.com/athletes/")
    s = s.replace("http://protrinews.com/en/athletes/", "https://protrinews.com/athletes/")
    s = s.replace("http://protrinews.com/athletes/", "https://protrinews.com/athletes/")
    return s


def _extract_raw(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _raw_value(row: pd.Series, *keys: str) -> Any:
    raw = _extract_raw(row.get("raw"))
    for key in keys:
        if key in raw:
            return raw.get(key)
    return None


def _display_cols(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in df.columns]
    return df[keep].copy() if keep else df.copy()


def _print_table(title: str, df: pd.DataFrame, max_rows: int = 20) -> None:
    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)
    if df.empty:
        print("(no rows)")
        return
    with pd.option_context(
        "display.max_rows", max_rows,
        "display.max_columns", 20,
        "display.width", 220,
        "display.max_colwidth", 34,
    ):
        print(df.head(max_rows).to_string(index=False))


# ---------------------------------------------------------------------------
# Secrets / Supabase
# ---------------------------------------------------------------------------

def _read_streamlit_secrets() -> Dict[str, Any]:
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data if isinstance(data, dict) else {}


def get_secret(name: str, fallback_names: Iterable[str] = ()) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value

    secrets = _read_streamlit_secrets()
    if name in secrets:
        return str(secrets[name])

    for alt in fallback_names:
        if os.getenv(alt):
            return os.getenv(alt)
        if alt in secrets:
            return str(secrets[alt])

    return None


def get_supabase_client():
    if create_client is None:
        raise RuntimeError(
            "Missing supabase package. Install with: pip install supabase"
        )

    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_SERVICE_KEY", ["SUPABASE_ANON_KEY", "SUPABASE_KEY"])

    if not url or not key:
        raise RuntimeError(
            "Missing Supabase credentials. Add SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "to environment variables or .streamlit/secrets.toml."
        )

    return create_client(url, key)


def fetch_table_paginated(
    table: str,
    select: str = "*",
    page_size: int = 1000,
    order_col: Optional[str] = None,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    max_rows: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch a Supabase table in 1,000-row pages.

    Supabase/PostgREST commonly caps responses at 1,000 rows, so do not use a
    bigger page size here.
    """
    sb = get_supabase_client()
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        end = offset + page_size - 1
        q = sb.table(table).select(select)

        if filters:
            for col, op, val in filters:
                if op == "eq":
                    q = q.eq(col, val)
                elif op == "gte":
                    q = q.gte(col, val)
                elif op == "lte":
                    q = q.lte(col, val)
                elif op == "ilike":
                    q = q.ilike(col, val)
                else:
                    raise ValueError(f"Unsupported filter op: {op}")

        if order_col:
            q = q.order(order_col)

        data = q.range(offset, end).execute().data or []
        rows.extend(data)

        print(f"Fetched {table}: {len(rows):,} rows", end="\r", flush=True)

        if len(data) < page_size:
            break
        offset += page_size

        if max_rows and len(rows) >= max_rows:
            rows = rows[:max_rows]
            break

    print(f"Fetched {table}: {len(rows):,} rows")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Local cache
# ---------------------------------------------------------------------------

def save_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(path)


def load_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_pickle(path)


def load_scoring_pool(refresh: bool = False, max_rows: Optional[int] = None) -> pd.DataFrame:
    if refresh or not SCORING_POOL_CACHE.exists():
        print("Loading scoring_result_pool from Supabase...")
        df = fetch_table_paginated(
            "scoring_result_pool",
            select="*",
            page_size=1000,
            order_col="race_date",
            max_rows=max_rows,
        )
        save_cache(df, SCORING_POOL_CACHE)
        return df

    df = load_cache(SCORING_POOL_CACHE)
    print(f"Loaded scoring_result_pool from local cache: {len(df):,} rows")
    return df


def load_start_lists(refresh: bool = False) -> pd.DataFrame:
    if refresh or not START_LIST_CACHE.exists():
        print("Loading start_lists from Supabase...")
        df = fetch_table_paginated(
            "start_lists",
            select="*",
            page_size=1000,
            order_col="race_date",
        )
        save_cache(df, START_LIST_CACHE)
        return df

    df = load_cache(START_LIST_CACHE)
    print(f"Loaded start_lists from local cache: {len(df):,} rows")
    return df


# ---------------------------------------------------------------------------
# Scorecard building
# ---------------------------------------------------------------------------

def build_selected_scorecards(
    pool: pd.DataFrame,
    as_of_date: str,
    model_version: str,
    top_n: int,
    gender: str,
    profile: str,
    all_slices: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = time.time()
    prep = prep_results(pool)

    cards_all: List[Dict[str, Any]] = []
    evidence_all: List[Dict[str, Any]] = []
    logs_all: List[Dict[str, Any]] = []

    if all_slices:
        genders = ["Men", "Women"]
        profiles = list(PROFILES)
        disciplines = list(DISCIPLINES)
    else:
        genders = [_norm_gender(gender)]
        profiles = [profile]
        disciplines = list(DISCIPLINES)

    print(
        f"Building scorecards locally: genders={genders}, profiles={profiles}, "
        f"disciplines={disciplines}, top_n={top_n}"
    )

    for g in genders:
        for p in profiles:
            for d in disciplines:
                c, e, log = build_scorecard_slice(
                    prep_df=prep,
                    gender=g,
                    profile=p,
                    discipline=d,
                    as_of_date=as_of_date,
                    model_version=model_version,
                    top_n=top_n,
                )
                cards_all.extend(c)
                evidence_all.extend(e)
                logs_all.append(log)
                print(
                    f"  {g} | {p} | {d}: "
                    f"{log.get('Scorecard Rows', 0):,} cards, "
                    f"{log.get('Evidence Rows', 0):,} evidence, "
                    f"{log.get('Rows After Profile', 0):,} profile rows"
                )

    cards = pd.DataFrame(cards_all)
    evidence = pd.DataFrame(evidence_all)
    logs = pd.DataFrame(logs_all)
    print(f"Local build done in {time.time() - start:.1f}s")
    print(f"Scorecards: {len(cards):,} | Evidence: {len(evidence):,}")

    return cards, evidence, logs


def flatten_raw_columns(cards: pd.DataFrame) -> pd.DataFrame:
    if cards.empty:
        return cards

    out = cards.copy()
    raw_series = out["raw"].map(_extract_raw) if "raw" in out.columns else pd.Series([{}] * len(out))

    for key in [
        "performance_score",
        "ranking_score",
        "prior_score",
        "prior_available",
        "prior_evidence_count",
        "evidence_count",
        "premium_evidence_count",
        "strong_evidence_count",
        "best_scores_used",
        "best_scores_padded",
        "ranking_slots",
        "ranking_method",
    ]:
        out[key] = raw_series.map(lambda x, k=key: x.get(k))

    return out


# ---------------------------------------------------------------------------
# Race / start-list analysis
# ---------------------------------------------------------------------------

def available_races(start_lists: pd.DataFrame) -> pd.DataFrame:
    if start_lists.empty:
        return pd.DataFrame()

    df = start_lists.copy()
    for col in ["race_name", "race_date", "gender"]:
        if col not in df.columns:
            df[col] = ""

    df["gender"] = df["gender"].map(_norm_gender)
    grouped = (
        df.groupby(["race_name", "race_date", "gender"], dropna=False)
          .agg(start_athletes=("athlete_name", "count"))
          .reset_index()
          .sort_values(["race_date", "race_name", "gender"], ascending=[False, True, True])
    )
    return grouped


def find_race_start_list(
    start_lists: pd.DataFrame,
    race_query: str,
    gender: str,
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]], pd.DataFrame]:
    races = available_races(start_lists)
    if races.empty:
        return pd.DataFrame(), None, races

    q = _clean(race_query).lower()
    g = _norm_gender(gender)

    matches = races.copy()
    if q:
        matches = matches[matches["race_name"].fillna("").str.lower().str.contains(re.escape(q), na=False)]
    if g:
        matches_g = matches[matches["gender"].map(_norm_gender).eq(g)]
        if not matches_g.empty:
            matches = matches_g

    if matches.empty:
        return pd.DataFrame(), None, races

    selected = matches.sort_values(["race_date", "start_athletes"], ascending=[False, False]).iloc[0].to_dict()

    sl = start_lists.copy()
    sl["gender"] = sl.get("gender", "").map(_norm_gender)
    mask = (
        sl["race_name"].fillna("").eq(selected["race_name"])
        & sl["race_date"].fillna("").astype(str).eq(str(selected["race_date"]))
        & sl["gender"].eq(_norm_gender(selected["gender"]))
    )
    return sl[mask].copy(), selected, matches


def join_start_list_scorecards(
    start_list: pd.DataFrame,
    cards: pd.DataFrame,
    profile: str,
    gender: str,
    discipline: str,
) -> pd.DataFrame:
    if start_list.empty or cards.empty:
        return pd.DataFrame()

    sl = start_list.copy()
    sl["athlete_url_key"] = sl.get("athlete_url", "").map(_canonical_url)
    sl["athlete_name_key"] = sl.get("athlete_name", "").map(lambda x: _clean(x).lower())

    sc = cards.copy()
    sc["gender"] = sc.get("gender", "").map(_norm_gender)
    sc = sc[
        sc["profile"].eq(profile)
        & sc["discipline"].eq(discipline)
        & sc["gender"].eq(_norm_gender(gender))
    ].copy()
    if sc.empty:
        return pd.DataFrame()

    sc = flatten_raw_columns(sc)
    sc["athlete_url_key"] = sc.get("athlete_url", "").map(_canonical_url)
    sc["athlete_name_key"] = sc.get("athlete_name", "").map(lambda x: _clean(x).lower())

    # Prefer URL join, then fallback to name join.
    joined_url = sl.merge(
        sc,
        on="athlete_url_key",
        how="left",
        suffixes=("_start", "_score"),
    )
    missing = joined_url["score"].isna() if "score" in joined_url.columns else pd.Series([True] * len(joined_url))

    if missing.any():
        fallback = sl[missing].merge(
            sc.drop(columns=["athlete_url_key"], errors="ignore"),
            on="athlete_name_key",
            how="left",
            suffixes=("_start", "_score"),
        )
        joined_url = pd.concat([joined_url[~missing], fallback], ignore_index=True)

    if "score" not in joined_url.columns:
        joined_url["score"] = None

    joined_url = joined_url.sort_values(["score", "athlete_name_start"], ascending=[False, True])
    joined_url["race_rank"] = range(1, len(joined_url) + 1)
    return joined_url


# ---------------------------------------------------------------------------
# Watchlist / output
# ---------------------------------------------------------------------------

def build_watchlist(cards: pd.DataFrame, names: List[str]) -> pd.DataFrame:
    if cards.empty or not names:
        return pd.DataFrame()

    c = flatten_raw_columns(cards)
    frames = []
    for name in names:
        key = name.lower()
        m = c[c["athlete_name"].fillna("").str.lower().str.contains(re.escape(key), na=False)].copy()
        if m.empty:
            frames.append(pd.DataFrame([{"watchlist_name": name, "found": False, "expectation": EXPECTATIONS.get(name, "")}]))
            continue
        m["watchlist_name"] = name
        m["found"] = True
        m["expectation"] = EXPECTATIONS.get(name, "")
        frames.append(m)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out


def save_outputs(
    cards: pd.DataFrame,
    evidence: pd.DataFrame,
    logs: pd.DataFrame,
    watchlist: pd.DataFrame,
    prefix: str,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cards.to_csv(OUT_DIR / f"{prefix}_scorecards.csv", index=False)
    evidence.to_csv(OUT_DIR / f"{prefix}_evidence.csv", index=False)
    logs.to_csv(OUT_DIR / f"{prefix}_logs.csv", index=False)
    if not watchlist.empty:
        watchlist.to_csv(OUT_DIR / f"{prefix}_watchlist.csv", index=False)

    print(f"\nSaved outputs to: {OUT_DIR}")


def save_race_outputs(
    race_tables: Dict[str, pd.DataFrame],
    prefix: str,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for discipline, df in race_tables.items():
        df.to_csv(OUT_DIR / f"{prefix}_race_{discipline}.csv", index=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fast local scorecard/ranking lab.")
    parser.add_argument("--refresh", action="store_true", help="Refresh local cache from Supabase.")
    parser.add_argument("--refresh-start-lists", action="store_true", help="Refresh start_lists cache from Supabase.")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit scoring pool rows for quick debugging.")
    parser.add_argument("--as-of", default=DEFAULT_AS_OF_DATE, help="As-of date, YYYY-MM-DD.")
    parser.add_argument("--model-version", default=MODEL_VERSION, help="Model version label.")
    parser.add_argument("--gender", default=DEFAULT_GENDER, choices=["Men", "Women"], help="Gender slice.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, choices=list(PROFILES), help="Profile slice.")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N_EVIDENCE, help="Evidence rows per scorecard.")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_ROWS, help="Rows to print per table.")
    parser.add_argument("--all-slices", action="store_true", help="Build all genders/profiles/disciplines.")
    parser.add_argument("--race", default="", help="Optional race-name search from start_lists.")
    parser.add_argument("--no-watchlist", action="store_true", help="Skip watchlist output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load_scoring_pool(refresh=args.refresh, max_rows=args.max_rows)
    if pool.empty:
        print("No scoring_result_pool rows loaded. Run with --refresh or check Supabase connection.")
        return 1

    start_lists = pd.DataFrame()
    if args.race:
        start_lists = load_start_lists(refresh=args.refresh or args.refresh_start_lists)

    cards, evidence, logs = build_selected_scorecards(
        pool=pool,
        as_of_date=args.as_of,
        model_version=args.model_version,
        top_n=args.top_n,
        gender=args.gender,
        profile=args.profile,
        all_slices=args.all_slices,
    )

    cards_flat = flatten_raw_columns(cards)
    prefix = "_".join([
        _slug(args.as_of),
        _slug(args.gender if not args.all_slices else "all_genders"),
        _slug(args.profile if not args.all_slices else "all_profiles"),
        _slug(args.race) if args.race else "global",
    ])

    _print_table(
        "Slice build logs",
        logs,
        max_rows=100,
    )

    if not cards_flat.empty:
        for discipline in DISCIPLINES:
            if not args.all_slices:
                view = cards_flat[
                    cards_flat["gender"].eq(args.gender)
                    & cards_flat["profile"].eq(args.profile)
                    & cards_flat["discipline"].eq(discipline)
                ].copy()
            else:
                view = cards_flat[cards_flat["discipline"].eq(discipline)].copy()

            view = view.sort_values("score", ascending=False)
            _print_table(
                f"Global top {args.top}: {discipline}",
                _display_cols(view, [
                    "rank", "athlete_name", "gender", "profile", "discipline",
                    "score", "performance_score", "prior_score", "best_scores_padded",
                    "evidence_count", "prior_evidence_count", "confidence",
                    "last_race_name", "last_race_date",
                ]),
                max_rows=args.top,
            )

    watchlist_df = pd.DataFrame()
    if not args.no_watchlist:
        watchlist_df = build_watchlist(cards_flat, WATCHLIST)
        _print_table(
            "Watchlist",
            _display_cols(watchlist_df, [
                "watchlist_name", "found", "athlete_name", "gender", "profile",
                "discipline", "rank", "score", "performance_score", "prior_score",
                "best_scores_padded", "evidence_count", "prior_evidence_count",
                "confidence", "expectation",
            ]),
            max_rows=200,
        )

    race_tables: Dict[str, pd.DataFrame] = {}
    if args.race:
        sl, selected_race, matches = find_race_start_list(start_lists, args.race, args.gender)
        _print_table(
            "Matching start-list races",
            matches,
            max_rows=25,
        )

        if selected_race is None or sl.empty:
            print(f"\nNo start list found for race query: {args.race!r}")
        else:
            print(
                "\nSelected race: "
                f"{selected_race.get('race_name')} | {selected_race.get('race_date')} | "
                f"{selected_race.get('gender')} | {len(sl):,} athletes"
            )
            for discipline in DISCIPLINES:
                joined = join_start_list_scorecards(
                    start_list=sl,
                    cards=cards_flat,
                    profile=args.profile,
                    gender=args.gender,
                    discipline=discipline,
                )
                race_tables[discipline] = joined
                _print_table(
                    f"Race ranking: {discipline}",
                    _display_cols(joined, [
                        "race_rank",
                        "athlete_name_start",
                        "athlete_name_score",
                        "score",
                        "performance_score",
                        "prior_score",
                        "best_scores_padded",
                        "evidence_count",
                        "prior_evidence_count",
                        "confidence",
                        "last_race_name",
                        "last_race_date",
                    ]),
                    max_rows=args.top,
                )

    save_outputs(cards_flat, evidence, logs, watchlist_df, prefix)
    if race_tables:
        save_race_outputs(race_tables, prefix)

    print("\nNext tuning loop:")
    print("  1. Edit score_engine.py")
    print("  2. Run this script again without --refresh")
    print("  3. Inspect CSVs in model_lab_outputs/")
    print("  4. Only commit/deploy once rankings look right locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






