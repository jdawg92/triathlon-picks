"""Small TriNews API helper for permissioned clean result refreshes.

This module intentionally stays independent from Streamlit/Supabase. It reads
from the public PostgREST API using a caller-provided key and returns normalized
rows shaped for the Triathlon Picks Supabase tables.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

TRINEWS_REST_BASE = "https://api.trinews.app/rest/v1"
PROTRINEWS_BASE = "https://protrinews.com"


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "—", "-"}:
        return None
    return s


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "TriathlonPicksCleanRefresh/1.0 (permissioned results refresh)",
    }


def _get(api_key: str, path: str, params: Dict[str, Any], timeout: int = 30) -> List[Dict[str, Any]]:
    resp = requests.get(f"{TRINEWS_REST_BASE}/{path.lstrip('/')}", headers=_headers(api_key), params=params, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"GET /{path} failed {resp.status_code}: {resp.text[:700]}")
    data = resp.json()
    return data if isinstance(data, list) else [data]


def _post_rpc(api_key: str, rpc_name: str, payload: Dict[str, Any], timeout: int = 30) -> List[Dict[str, Any]]:
    resp = requests.post(f"{TRINEWS_REST_BASE}/rpc/{rpc_name}", headers=_headers(api_key), json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"RPC {rpc_name} failed {resp.status_code}: {resp.text[:700]}")
    data = resp.json()
    return data if isinstance(data, list) else [data]


def _slug_from_identifier(identifier: str) -> Optional[str]:
    s = _clean(identifier)
    if not s:
        return None
    m = re.search(r"/athletes/([^/?#]+)", s, flags=re.I)
    if m:
        return m.group(1).strip()
    # Plain slug like hanne-de-vet.
    if " " not in s and re.match(r"^[a-z0-9][a-z0-9-]+$", s, flags=re.I):
        return s
    return None


def _uuid_like(identifier: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", str(identifier).strip(), flags=re.I))


def _athlete_row_to_id(row: Dict[str, Any]) -> Optional[str]:
    return _clean(row.get("id") or row.get("athlete_id"))


def resolve_athlete(api_key: str, identifier: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Resolve a name/url/slug/id to one row from /athletes."""
    ident = _clean(identifier)
    if not ident:
        return None, {"input": identifier, "status": "blank"}

    try:
        if _uuid_like(ident):
            rows = _get(api_key, "athletes", {"select": "*", "id": f"eq.{ident}", "limit": 1})
            return (rows[0] if rows else None), {"input": ident, "status": "id_lookup", "matches": len(rows)}

        slug = _slug_from_identifier(ident)
        if slug:
            rows = _get(api_key, "athletes", {"select": "*", "slug": f"eq.{slug}", "limit": 1})
            if rows:
                return rows[0], {"input": ident, "status": "slug_lookup", "matches": len(rows)}

        search_payload = {
            "p_query": ident,
            "p_gender": None,
            "p_country_code": None,
            "p_limit": 5,
            "p_offset": 0,
            "p_is_pro": None,
            "p_sort": "openrank",
            "p_letter": None,
        }
        search_rows = _post_rpc(api_key, "search_athletes", search_payload)
        if not search_rows:
            return None, {"input": ident, "status": "search_no_match"}

        # Prefer exact full-name match when present, else first result.
        chosen = search_rows[0]
        for row in search_rows:
            nm = _clean(row.get("full_name") or row.get("athlete_name") or row.get("name") or row.get("display_name"))
            if nm and nm.lower() == ident.lower():
                chosen = row
                break
        athlete_id = _athlete_row_to_id(chosen)
        if athlete_id:
            rows = _get(api_key, "athletes", {"select": "*", "id": f"eq.{athlete_id}", "limit": 1})
            if rows:
                return rows[0], {"input": ident, "status": "search_then_id", "matches": len(search_rows), "athlete_id": athlete_id}
        # Some search rows may already have enough fields.
        return chosen, {"input": ident, "status": "search_row_only", "matches": len(search_rows), "athlete_id": athlete_id}
    except Exception as e:
        return None, {"input": ident, "status": "error", "error": str(e)}


def seconds_from_api_time(value: Any) -> Optional[int]:
    s = _clean(value)
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = [int(float(x)) for x in parts]
            return h * 3600 + m * 60 + sec
        if len(parts) == 2:
            m, sec = [int(float(x)) for x in parts]
            return m * 60 + sec
        return int(float(s))
    except Exception:
        return None


def gender_from_api(athlete: Optional[Dict[str, Any]], result: Optional[Dict[str, Any]] = None) -> Optional[str]:
    candidates = []
    if result:
        candidates.append(result.get("program_name"))
    if athlete:
        candidates.append(athlete.get("gender"))
    for v in candidates:
        s = (_clean(v) or "").lower()
        if not s:
            continue
        if "women" in s or "female" in s or s in {"f", "fpro", "female"} or s.startswith("fpro"):
            return "Women"
        if "men" in s or "male" in s or s in {"m", "mpro", "male"} or s.startswith("mpro"):
            return "Men"
    return None


def race_type_from_api_race(race: Dict[str, Any]) -> Optional[str]:
    txt = " ".join(str(race.get(k) or "") for k in ["name", "distance_category", "brand", "wt_category", "circuit", "organization"]).lower()
    if "t100" in txt or "pto" in txt or "100k" in txt:
        return "T100"
    if "70.3" in txt or "middle" in txt:
        return "70.3"
    if ("ironman" in txt and "70.3" not in txt) or "140.6" in txt or "full" in txt:
        return "Full"
    if "wtcs" in txt or "world triathlon championship series" in txt:
        return "WTCS"
    if "world triathlon cup" in txt:
        return "World Triathlon Cup"
    if any(x in txt for x in ["continental", "europe triathlon cup", "americas triathlon cup", "asia triathlon cup", "africa triathlon cup", "oceania triathlon cup"]):
        return "Continental Cup"
    if "olympic" in txt or "standard" in txt:
        return "Olympic"
    if "sprint" in txt:
        return "Sprint"
    return _clean(race.get("distance_category") or race.get("wt_category") or race.get("brand"))


def date_from_api(value: Any) -> Optional[str]:
    s = _clean(value)
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return s[:10]


def athlete_url_from_api(athlete: Optional[Dict[str, Any]], athlete_id: Optional[str] = None) -> str:
    slug = _clean((athlete or {}).get("slug"))
    if slug:
        return f"{PROTRINEWS_BASE}/athletes/{slug}"
    return f"missing-url::trinews-{athlete_id or 'unknown'}"


def athlete_name_from_api(athlete: Optional[Dict[str, Any]], athlete_id: Optional[str] = None) -> Optional[str]:
    if not athlete:
        return athlete_id
    return _clean(athlete.get("full_name") or athlete.get("display_name") or " ".join(x for x in [_clean(athlete.get("first_name")), _clean(athlete.get("last_name"))] if x))


def points_openrank(result: Dict[str, Any]) -> Optional[float]:
    pts = result.get("points")
    if isinstance(pts, str):
        try:
            pts = json.loads(pts)
        except Exception:
            pts = {}
    if not isinstance(pts, dict):
        pts = {}
    val = pts.get("openrank")
    try:
        return float(val) if val is not None else None
    except Exception:
        return None


def fetch_results_for_athlete(api_key: str, athlete_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    return _get(api_key, "results", {
        "select": "*",
        "athlete_id": f"eq.{athlete_id}",
        "limit": int(limit),
        "order": "created_at.desc",
    })


def fetch_results_for_race(api_key: str, race_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    return _get(api_key, "results", {
        "select": "*",
        "race_id": f"eq.{race_id}",
        "limit": int(limit),
        "order": "placement.asc",
    })


def fetch_by_ids(api_key: str, table: str, ids: Iterable[str], chunk_size: int = 100) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    clean_ids = [x for x in dict.fromkeys([_clean(x) for x in ids]) if x]
    for i in range(0, len(clean_ids), chunk_size):
        chunk = clean_ids[i:i + chunk_size]
        if not chunk:
            continue
        rows = _get(api_key, table, {"select": "*", "id": f"in.({','.join(chunk)})", "limit": len(chunk)})
        for row in rows:
            row_id = _clean(row.get("id"))
            if row_id:
                out[row_id] = row
    return out


def result_to_pick_rows(result: Dict[str, Any], race: Optional[Dict[str, Any]], athlete: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    race = race or {}
    athlete_id = _clean(result.get("athlete_id"))
    race_slug = _clean(race.get("slug"))
    race_type = race_type_from_api_race(race)
    gender = gender_from_api(athlete, result)
    row = {
        "athlete_url": athlete_url_from_api(athlete, athlete_id),
        "athlete_name": athlete_name_from_api(athlete, athlete_id),
        "gender": gender,
        "race_date": date_from_api(race.get("date") or result.get("race_date")),
        "race_name": _clean(race.get("name") or result.get("race_name")),
        "race_url": f"{PROTRINEWS_BASE}/races/{race_slug}" if race_slug else None,
        "race_type": race_type,
        "distance": _clean(race.get("distance_category")),
        "place": str(result.get("placement")) if result.get("placement") is not None else _clean(result.get("status")),
        "sof": race.get("strength_of_field"),
        "ors": points_openrank(result),
        "swim_seconds": seconds_from_api_time(result.get("swim_time")),
        "bike_seconds": seconds_from_api_time(result.get("bike_time")),
        "run_seconds": seconds_from_api_time(result.get("run_time")),
        "status": _clean(result.get("status")),
        "raw": {
            "source": "trinews_api",
            "trinews_result_id": result.get("id"),
            "trinews_athlete_id": athlete_id,
            "trinews_race_id": result.get("race_id"),
            "program_name": result.get("program_name"),
            "finish_time": result.get("finish_time"),
            "swim_time": result.get("swim_time"),
            "bike_time": result.get("bike_time"),
            "run_time": result.get("run_time"),
            "swim_rank": result.get("swim_rank"),
            "bike_rank": result.get("bike_rank"),
            "run_rank": result.get("run_rank"),
            "points": result.get("points"),
            "race_slug": race_slug,
            "race_tier": race.get("tier"),
            "race_brand": race.get("brand"),
            "race_circuit": race.get("circuit"),
            "api_updated_at": result.get("updated_at"),
        },
    }
    return row


def athlete_master_row_from_api(athlete: Dict[str, Any]) -> Dict[str, Any]:
    athlete_id = _clean(athlete.get("id"))
    return {
        "athlete_url": athlete_url_from_api(athlete, athlete_id),
        "athlete_name": athlete_name_from_api(athlete, athlete_id),
        "gender": gender_from_api(athlete),
    }


def build_clean_results_refresh(
    api_key: str,
    identifiers: List[str],
    result_limit_per_athlete: int = 100,
    include_race_fields: bool = True,
    race_field_limit: int = 1000,
    max_races: int = 40,
) -> Dict[str, Any]:
    """Resolve athletes and return normalized clean result rows.

    Returns keys: athletes, athlete_results, race_field_results, logs.
    """
    if not _clean(api_key):
        raise ValueError("TriNews API key is required.")

    logs: List[Dict[str, Any]] = []
    resolved_athletes: Dict[str, Dict[str, Any]] = {}
    athlete_results_raw: List[Dict[str, Any]] = []

    for ident in identifiers:
        athlete, log = resolve_athlete(api_key, ident)
        athlete_id = _athlete_row_to_id(athlete or {})
        log["athlete_id"] = athlete_id
        log["athlete_name"] = athlete_name_from_api(athlete, athlete_id) if athlete else None
        if athlete and athlete_id:
            resolved_athletes[athlete_id] = athlete
            try:
                results = fetch_results_for_athlete(api_key, athlete_id, result_limit_per_athlete)
                athlete_results_raw.extend(results)
                log["results"] = len(results)
            except Exception as e:
                log["result_error"] = str(e)
        logs.append(log)

    race_ids = [r.get("race_id") for r in athlete_results_raw if _clean(r.get("race_id"))]
    race_map = fetch_by_ids(api_key, "races", race_ids)

    # Fetch full race fields for races touched by the selected athletes.
    race_field_raw: List[Dict[str, Any]] = []
    if include_race_fields:
        for race_id in list(dict.fromkeys([_clean(x) for x in race_ids if _clean(x)]))[:max_races]:
            try:
                race_field_raw.extend(fetch_results_for_race(api_key, race_id, race_field_limit))
            except Exception as e:
                logs.append({"input": race_id, "status": "race_field_error", "error": str(e)})

    all_athlete_ids = []
    for r in athlete_results_raw + race_field_raw:
        aid = _clean(r.get("athlete_id"))
        if aid:
            all_athlete_ids.append(aid)
    athlete_map = fetch_by_ids(api_key, "athletes", all_athlete_ids)
    athlete_map.update(resolved_athletes)

    all_race_ids = [r.get("race_id") for r in race_field_raw if _clean(r.get("race_id"))]
    missing_race_ids = [x for x in all_race_ids if _clean(x) and _clean(x) not in race_map]
    if missing_race_ids:
        race_map.update(fetch_by_ids(api_key, "races", missing_race_ids))

    athlete_rows = [athlete_master_row_from_api(a) for a in athlete_map.values()]
    # Deduplicate athletes by URL.
    by_url: Dict[str, Dict[str, Any]] = {}
    for row in athlete_rows:
        url = _clean(row.get("athlete_url"))
        if url:
            by_url[url] = row

    athlete_result_rows = [result_to_pick_rows(r, race_map.get(_clean(r.get("race_id"))), athlete_map.get(_clean(r.get("athlete_id")))) for r in athlete_results_raw]
    field_result_rows = [result_to_pick_rows(r, race_map.get(_clean(r.get("race_id"))), athlete_map.get(_clean(r.get("athlete_id")))) for r in race_field_raw]

    # Remove rows that cannot map to a named race/athlete.
    athlete_result_rows = [r for r in athlete_result_rows if _clean(r.get("athlete_name")) and _clean(r.get("race_name"))]
    field_result_rows = [r for r in field_result_rows if _clean(r.get("athlete_name")) and _clean(r.get("race_name"))]

    return {
        "athletes": list(by_url.values()),
        "athlete_results": athlete_result_rows,
        "race_field_results": field_result_rows,
        "logs": logs,
        "races_found": len(race_map),
        "race_fields_refreshed": len(set(_clean(r.get("race_id")) for r in race_field_raw if _clean(r.get("race_id")))) if include_race_fields else 0,
    }
