"""Probe TriNews public API tables for a clean fresh rebuild.

Usage:
  $env:TRINEWS_API_KEY="..."
  py trinews_fresh_source_probe.py --race-slug t100-triathlon-world-tour-spain-2026
  py trinews_fresh_source_probe.py --race-slug t100-triathlon-world-tour-spain-2026 --athlete "Hanne De Vet"
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE = "https://api.trinews.app/rest/v1"

START_TABLES = [
    "start_lists", "startlists", "race_start_lists", "race_startlists",
    "race_entries", "entries", "race_participants", "participants",
    "event_entries", "event_participants", "program_entries",
]
START_FILTERS = [
    ("race_id", "id"), ("race", "id"), ("race_uuid", "id"),
    ("event_hub_id", "event_hub_id"), ("event_id", "event_hub_id"),
    ("race_slug", "slug"), ("slug", "slug"),
]


def headers() -> Dict[str, str]:
    key = os.environ.get("TRINEWS_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set TRINEWS_API_KEY first.")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "TriathlonPicksFreshSourceProbe/1.0",
    }


def get(path: str, params: Dict[str, Any]) -> Tuple[int, Any]:
    r = requests.get(f"{BASE}/{path.lstrip('/')}", headers=headers(), params=params, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def post_rpc(name: str, payload: Dict[str, Any]) -> Tuple[int, Any]:
    r = requests.post(f"{BASE}/rpc/{name}", headers=headers(), json=payload, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def show(label: str, status: int, data: Any, max_chars: int = 3500) -> None:
    print("=" * 110)
    print(label)
    print(f"Status: {status}")
    txt = json.dumps(data, indent=2, ensure_ascii=False, default=str) if not isinstance(data, str) else data
    print(txt[:max_chars] + ("\n... [truncated]" if len(txt) > max_chars else ""))


def resolve_race(slug: str) -> Optional[Dict[str, Any]]:
    status, data = get("races", {"select": "*", "slug": f"eq.{slug}", "limit": 1})
    show(f"GET /races?slug=eq.{slug}", status, data)
    if status == 200 and isinstance(data, list) and data:
        return data[0]
    return None


def resolve_athlete(name: str) -> Optional[Dict[str, Any]]:
    payload = {
        "p_query": name,
        "p_gender": None,
        "p_country_code": None,
        "p_limit": 5,
        "p_offset": 0,
        "p_is_pro": None,
        "p_sort": "openrank",
        "p_letter": None,
    }
    status, data = post_rpc("search_athletes", payload)
    show(f"RPC search_athletes for {name}", status, data)
    if status == 200 and isinstance(data, list) and data:
        aid = data[0].get("id") or data[0].get("athlete_id")
        if aid:
            st2, athlete_rows = get("athletes", {"select": "*", "id": f"eq.{aid}", "limit": 1})
            show(f"GET /athletes?id=eq.{aid}", st2, athlete_rows)
            if st2 == 200 and isinstance(athlete_rows, list) and athlete_rows:
                return athlete_rows[0]
    return None


def probe_start_lists(race: Dict[str, Any], limit: int = 10) -> None:
    print("=" * 110)
    print("START LIST SOURCE PROBE")
    race_values = {
        "id": race.get("id"),
        "event_hub_id": race.get("event_hub_id"),
        "slug": race.get("slug"),
    }
    found = False
    for table in START_TABLES:
        for col, key in START_FILTERS:
            val = race_values.get(key)
            if not val:
                continue
            params = {"select": "*", col: f"eq.{val}", "limit": limit}
            status, data = get(table, params)
            rows = data if isinstance(data, list) else []
            if status == 200 or rows:
                show(f"GET /{table}?{col}=eq.{val}", status, data, max_chars=2500)
            if status == 200 and rows:
                found = True
                print("FOUND START LIST SOURCE ABOVE. Stopping early.")
                return
    if not found:
        print("No non-empty public start-list table/view found for this race with the tested names/keys.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race-slug", required=True)
    ap.add_argument("--athlete", default="")
    args = ap.parse_args()

    race = resolve_race(args.race_slug)
    if not race:
        return
    race_id = race.get("id")

    st, result_rows = get("results", {"select": "*", "race_id": f"eq.{race_id}", "limit": 5, "order": "placement.asc"})
    show(f"GET /results?race_id=eq.{race_id}", st, result_rows)

    if args.athlete:
        athlete = resolve_athlete(args.athlete)
        if athlete:
            aid = athlete.get("id")
            st2, athlete_results = get("results", {"select": "*", "athlete_id": f"eq.{aid}", "limit": 10, "order": "created_at.desc"})
            show(f"GET /results?athlete_id=eq.{aid}", st2, athlete_results)

    probe_start_lists(race)


if __name__ == "__main__":
    main()
