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


def display_race_name_from_api(race: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> Optional[str]:
    name = _clean(race.get("name") or (result or {}).get("race_name"))
    if not name:
        return None
    # Match legacy/imported naming where the leading calendar year was not stored
    # in the race name. The date remains stored separately in race_date.
    return re.sub(r"^\s*(19|20)\d{2}\s+", "", name).strip()


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
        "race_name": display_race_name_from_api(race, result),
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



def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def computed_race_sof_from_results(results: List[Dict[str, Any]], top_n: int = 10) -> Optional[float]:
    """Estimate race SOF from the top OpenRank values in the field.

    TriNews sometimes leaves races.strength_of_field blank while each result has
    points.openrank. The old app needs a race-level SOF number for evidence
    weighting, so this computes a stable field-quality proxy from the race field.
    """
    vals: List[float] = []
    for r in results or []:
        if (_clean(r.get('status')) or '').upper() not in {'FIN', 'OK', 'FINISH'}:
            # DNS/DNF rows can be present and should not define field quality.
            pass
        v = points_openrank(r)
        if v is not None and v > 0:
            vals.append(float(v))
    vals = sorted(vals, reverse=True)
    if not vals:
        return None
    n = min(max(3, top_n), len(vals))
    return round(sum(vals[:n]) / n, 1)


def fetch_races(
    api_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    circuit: Optional[str] = None,
    brand: Optional[str] = None,
    max_races: int = 250,
    page_size: int = 200,
) -> List[Dict[str, Any]]:
    """Fetch race metadata from /races with safe pagination."""
    if max_races <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))
    while len(rows) < max_races:
        params: Dict[str, Any] = {
            'select': '*',
            'has_results': 'eq.true',
            'order': 'date.desc',
            'limit': min(page_size, max_races - len(rows)),
            'offset': offset,
        }
        and_clauses = []
        sd = _clean(start_date)
        ed = _clean(end_date)
        if sd:
            and_clauses.append(f'date.gte.{sd}')
        if ed:
            and_clauses.append(f'date.lte.{ed}')
        if and_clauses:
            params['and'] = '(' + ','.join(and_clauses) + ')'
        c = _clean(circuit)
        if c and c.lower() not in {'all', 'any'}:
            params['circuit'] = f'eq.{c}'
        b = _clean(brand)
        if b and b.lower() not in {'all', 'any'}:
            params['brand'] = f'eq.{b}'
        page = _get(api_key, 'races', params, timeout=45)
        rows.extend(page)
        if len(page) < int(params['limit']):
            break
        offset += int(params['limit'])
    return rows[:max_races]


def fetch_all_pro_athletes(api_key: str, max_athletes: int = 10000, page_size: int = 1000) -> List[Dict[str, Any]]:
    """Optionally fetch lightweight pro athlete profiles from /athletes."""
    if max_athletes <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))
    while len(rows) < max_athletes:
        params = {
            'select': '*',
            'is_pro': 'eq.true',
            'order': 'full_name.asc',
            'limit': min(page_size, max_athletes - len(rows)),
            'offset': offset,
        }
        page = _get(api_key, 'athletes', params, timeout=45)
        rows.extend(page)
        if len(page) < int(params['limit']):
            break
        offset += int(params['limit'])
    return rows[:max_athletes]


def trinews_race_source_row(race: Dict[str, Any], computed_sof: Optional[float] = None) -> Dict[str, Any]:
    race_id = _clean(race.get('id'))
    sof = _as_float(race.get('strength_of_field'))
    if sof is None:
        sof = computed_sof
    return {
        'id': race_id,
        'name': _clean(race.get('name')),
        'slug': _clean(race.get('slug')),
        'race_date': date_from_api(race.get('date')),
        'organization': _clean(race.get('organization')),
        'distance_category': _clean(race.get('distance_category')),
        'tier': _clean(race.get('tier')),
        'brand': _clean(race.get('brand')),
        'circuit': _clean(race.get('circuit')),
        'venue': _clean(race.get('venue')),
        'city': _clean(race.get('city')),
        'country_name': _clean(race.get('country_name')),
        'country_iso2': _clean(race.get('country_iso2')),
        'strength_of_field': sof,
        'difficulty_score': _as_float(race.get('difficulty_score')),
        'has_results': bool(race.get('has_results')),
        'updated_at': _clean(race.get('updated_at')),
        'raw': race,
    }


def trinews_result_source_row(result: Dict[str, Any], race: Optional[Dict[str, Any]], athlete: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    pts = result.get('points')
    if isinstance(pts, str):
        try:
            pts = json.loads(pts)
        except Exception:
            pts = {}
    if not isinstance(pts, dict):
        pts = {}
    return {
        'id': _clean(result.get('id')),
        'race_id': _clean(result.get('race_id')),
        'athlete_id': _clean(result.get('athlete_id')),
        'race_slug': _clean((race or {}).get('slug')),
        'race_name': _clean((race or {}).get('name')),
        'race_date': date_from_api((race or {}).get('date')),
        'athlete_name': athlete_name_from_api(athlete, _clean(result.get('athlete_id'))),
        'athlete_slug': _clean((athlete or {}).get('slug')),
        'gender': gender_from_api(athlete, result),
        'program_name': _clean(result.get('program_name')),
        'placement': result.get('placement'),
        'status': _clean(result.get('status')),
        'finish_time': _clean(result.get('finish_time')),
        'swim_time': _clean(result.get('swim_time')),
        'bike_time': _clean(result.get('bike_time')),
        'run_time': _clean(result.get('run_time')),
        'swim_seconds': seconds_from_api_time(result.get('swim_time')),
        'bike_seconds': seconds_from_api_time(result.get('bike_time')),
        'run_seconds': seconds_from_api_time(result.get('run_time')),
        'swim_rank': result.get('swim_rank'),
        'bike_rank': result.get('bike_rank'),
        'run_rank': result.get('run_rank'),
        'openrank': points_openrank(result),
        'pto_points': _as_float(pts.get('pto')),
        't100_points': _as_float(pts.get('t100')),
        'source': _clean(result.get('source')),
        'updated_at': _clean(result.get('updated_at')),
        'raw': result,
    }


def trinews_athlete_source_row(athlete: Dict[str, Any]) -> Dict[str, Any]:
    aid = _clean(athlete.get('id'))
    return {
        'id': aid,
        'full_name': athlete_name_from_api(athlete, aid),
        'slug': _clean(athlete.get('slug')),
        'gender': gender_from_api(athlete),
        'country_name': _clean(athlete.get('country_name')),
        'country_iso2': _clean(athlete.get('country_iso2')),
        'country_iso3': _clean(athlete.get('country_iso3')),
        'year_of_birth': athlete.get('year_of_birth'),
        'photo_url': _clean(athlete.get('photo_url')),
        'is_pro': bool(athlete.get('is_pro')),
        'updated_at': _clean(athlete.get('updated_at')),
        'raw': athlete,
    }


def build_full_clean_api_rebuild(
    api_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    circuit: Optional[str] = None,
    brand: Optional[str] = None,
    max_races: int = 250,
    race_result_limit: int = 1000,
    sync_all_pro_athletes: bool = False,
    max_athletes: int = 10000,
) -> Dict[str, Any]:
    """Build a full clean-source payload from TriNews API data.

    This intentionally returns data only; the Streamlit app decides whether to
    preview it or clear/insert tables.
    """
    if not _clean(api_key):
        raise ValueError('TriNews API key is required.')

    logs: List[Dict[str, Any]] = []
    races = fetch_races(
        api_key=api_key,
        start_date=start_date,
        end_date=end_date,
        circuit=circuit,
        brand=brand,
        max_races=int(max_races),
    )
    logs.append({'stage': 'races', 'status': 'ok', 'rows': len(races)})

    race_map: Dict[str, Dict[str, Any]] = {}
    race_results_by_race: Dict[str, List[Dict[str, Any]]] = {}
    all_results: List[Dict[str, Any]] = []
    for race in races:
        rid = _clean(race.get('id'))
        if not rid:
            continue
        race_map[rid] = race
        try:
            results = fetch_results_for_race(api_key, rid, int(race_result_limit))
            race_results_by_race[rid] = results
            all_results.extend(results)
            logs.append({'stage': 'results', 'race_id': rid, 'race_name': race.get('name'), 'rows': len(results), 'status': 'ok'})
        except Exception as e:
            logs.append({'stage': 'results', 'race_id': rid, 'race_name': race.get('name'), 'status': 'error', 'error': str(e)})

    computed_sof: Dict[str, Optional[float]] = {rid: computed_race_sof_from_results(rows) for rid, rows in race_results_by_race.items()}

    athlete_ids = [_clean(r.get('athlete_id')) for r in all_results if _clean(r.get('athlete_id'))]
    athlete_map = fetch_by_ids(api_key, 'athletes', athlete_ids)
    logs.append({'stage': 'athletes_from_results', 'status': 'ok', 'rows': len(athlete_map)})

    if sync_all_pro_athletes:
        try:
            pro_rows = fetch_all_pro_athletes(api_key, max_athletes=int(max_athletes))
            for a in pro_rows:
                aid = _clean(a.get('id'))
                if aid:
                    athlete_map[aid] = a
            logs.append({'stage': 'all_pro_athletes', 'status': 'ok', 'rows': len(pro_rows)})
        except Exception as e:
            logs.append({'stage': 'all_pro_athletes', 'status': 'error', 'error': str(e)})

    # Build normalized app rows. Inject computed SOF when the API race row has none.
    app_result_rows: List[Dict[str, Any]] = []
    source_result_rows: List[Dict[str, Any]] = []
    for r in all_results:
        rid = _clean(r.get('race_id'))
        aid = _clean(r.get('athlete_id'))
        race = dict(race_map.get(rid) or {})
        if _as_float(race.get('strength_of_field')) is None and computed_sof.get(rid) is not None:
            race['strength_of_field'] = computed_sof.get(rid)
        athlete = athlete_map.get(aid)
        row = result_to_pick_rows(r, race, athlete)
        if _clean(row.get('athlete_name')) and _clean(row.get('race_name')):
            app_result_rows.append(row)
        source_result_rows.append(trinews_result_source_row(r, race, athlete))

    athlete_rows = [athlete_master_row_from_api(a) for a in athlete_map.values()]
    athlete_rows_by_url: Dict[str, Dict[str, Any]] = {}
    for row in athlete_rows:
        url = _clean(row.get('athlete_url'))
        if url:
            athlete_rows_by_url[url] = row

    source_athletes = [trinews_athlete_source_row(a) for a in athlete_map.values()]
    source_races = [trinews_race_source_row(r, computed_sof.get(_clean(r.get('id')))) for r in races]

    rows_with_swim = sum(1 for r in app_result_rows if seconds_from_api_time(((r.get('raw') or {}).get('swim_time'))) or r.get('swim_seconds'))
    rows_with_bike = sum(1 for r in app_result_rows if r.get('bike_seconds'))
    rows_with_run = sum(1 for r in app_result_rows if r.get('run_seconds'))
    return {
        'athletes': list(athlete_rows_by_url.values()),
        'athlete_results': app_result_rows,
        'race_field_results': app_result_rows,
        'trinews_athletes': source_athletes,
        'trinews_races': source_races,
        'trinews_results': source_result_rows,
        'logs': logs,
        'summary': {
            'races': len(races),
            'results': len(all_results),
            'app_result_rows': len(app_result_rows),
            'athletes': len(athlete_rows_by_url),
            'source_athletes': len(source_athletes),
            'source_races': len(source_races),
            'source_results': len(source_result_rows),
            'rows_with_swim': rows_with_swim,
            'rows_with_bike': rows_with_bike,
            'rows_with_run': rows_with_run,
            'computed_sof_races': sum(1 for v in computed_sof.values() if v is not None),
        },
    }

# ============================================================
# Fresh rebuild + start-list sync additions
# ============================================================

START_LIST_CANDIDATE_TABLES = [
    "start_lists",
    "startlists",
    "race_start_lists",
    "race_startlists",
    "race_entries",
    "entries",
    "race_participants",
    "participants",
    "event_entries",
    "event_participants",
    "program_entries",
]

START_LIST_FILTER_CANDIDATES = [
    ("race_id", "id"),
    ("race", "id"),
    ("race_uuid", "id"),
    ("event_hub_id", "event_hub_id"),
    ("event_id", "event_hub_id"),
    ("race_slug", "slug"),
    ("slug", "slug"),
]


def _get_optional(api_key: str, path: str, params: Dict[str, Any], timeout: int = 25) -> Tuple[int, Any]:
    """GET a PostgREST path and return (status, json_or_text), never raise."""
    try:
        resp = requests.get(
            f"{TRINEWS_REST_BASE}/{path.lstrip('/')}",
            headers=_headers(api_key),
            params=params,
            timeout=timeout,
        )
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return resp.status_code, data
    except Exception as e:
        return 0, {"error": str(e)}


def probe_start_list_sources_for_race(api_key: str, race: Dict[str, Any], limit: int = 25) -> List[Dict[str, Any]]:
    """Try common public tables/views for start-list data for one race.

    This is intentionally read-only and small. It helps discover whether the
    public API exposes start lists and which table/key combination works.
    """
    out: List[Dict[str, Any]] = []
    race_id = _clean(race.get("id"))
    event_hub_id = _clean(race.get("event_hub_id"))
    slug = _clean(race.get("slug"))
    race_values = {"id": race_id, "event_hub_id": event_hub_id, "slug": slug}

    for table in START_LIST_CANDIDATE_TABLES:
        for col, race_key in START_LIST_FILTER_CANDIDATES:
            val = race_values.get(race_key)
            if not val:
                continue
            params = {"select": "*", col: f"eq.{val}", "limit": int(limit)}
            status, data = _get_optional(api_key, table, params)
            rows = data if isinstance(data, list) else []
            out.append({
                "table": table,
                "filter_column": col,
                "filter_value": val,
                "status": status,
                "row_count": len(rows),
                "sample": rows[:3] if rows else data,
            })
            if status == 200 and rows:
                # A non-empty exact-race match is enough. Avoid hammering every
                # remaining candidate table in app flows.
                return out
    return out


def discover_start_list_rows_for_race(api_key: str, race: Dict[str, Any], limit: int = 1000) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return first non-empty start-list candidate rows plus discovery log."""
    attempts = probe_start_list_sources_for_race(api_key, race, limit=min(25, int(limit)))
    for a in attempts:
        if a.get("status") == 200 and int(a.get("row_count") or 0) > 0:
            table = a.get("table")
            col = a.get("filter_column")
            val = a.get("filter_value")
            rows = _get(api_key, str(table), {"select": "*", str(col): f"eq.{val}", "limit": int(limit)}, timeout=45)
            return rows, {"status": "ok", "table": table, "filter_column": col, "rows": len(rows), "race_id": race.get("id"), "race_slug": race.get("slug")}
    return [], {"status": "not_found_or_empty", "attempts": attempts, "race_id": race.get("id"), "race_slug": race.get("slug")}


def _extract_nested(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        cur: Any = row
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur.get(part)
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _start_list_athlete_id(row: Dict[str, Any]) -> Optional[str]:
    return _clean(_extract_nested(row, [
        "athlete_id", "athlete.id", "athletes.id", "participant.athlete_id", "entry.athlete_id", "profile_id"
    ]))


def _start_list_gender(row: Dict[str, Any], athlete: Optional[Dict[str, Any]]) -> Optional[str]:
    return gender_from_api(athlete, {
        "program_name": _extract_nested(row, ["program_name", "program", "division", "category", "gender"])
    })


def _start_list_openrank(row: Dict[str, Any]) -> Optional[float]:
    for k in ["openrank", "open_rank", "open_rank_score", "ors", "score", "rank", "ranking"]:
        v = _extract_nested(row, [k, f"points.{k}"])
        try:
            if v is not None and str(v).strip() != "":
                return float(v)
        except Exception:
            pass
    pts = row.get("points")
    if isinstance(pts, str):
        try:
            pts = json.loads(pts)
        except Exception:
            pts = {}
    if isinstance(pts, dict):
        for k in ["openrank", "open_rank", "ors"]:
            try:
                if pts.get(k) is not None:
                    return float(pts.get(k))
            except Exception:
                pass
    return None


def start_list_row_to_pick_row(row: Dict[str, Any], race: Dict[str, Any], athlete: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    aid = _start_list_athlete_id(row)
    athlete_name = athlete_name_from_api(athlete, aid)
    if not athlete_name:
        athlete_name = _clean(_extract_nested(row, [
            "athlete_name", "full_name", "name", "display_name", "athlete.full_name", "athlete.name", "athletes.full_name"
        ]))
    athlete_url = athlete_url_from_api(athlete, aid) if athlete or aid else None
    if not athlete_url:
        slug = _clean(_extract_nested(row, ["athlete_slug", "slug", "athlete.slug", "athletes.slug"]))
        if slug:
            athlete_url = f"{PROTRINEWS_BASE}/athletes/{slug}"
    if not athlete_name and not athlete_url:
        return None
    return {
        "race_name": display_race_name_from_api(race),
        "race_date": date_from_api(race.get("date")),
        "gender": _start_list_gender(row, athlete) or gender_from_api(athlete) or "Men",
        "athlete_url": athlete_url,
        "athlete_name": athlete_name,
        "open_rank": _start_list_openrank(row),
        "raw": {
            "source": "trinews_api_start_list",
            "trinews_race_id": race.get("id"),
            "race_slug": race.get("slug"),
            "trinews_athlete_id": aid,
            "api_row": row,
        },
    }


def trinews_start_list_source_row(row: Dict[str, Any], race: Dict[str, Any], athlete: Optional[Dict[str, Any]], source: Optional[str] = None) -> Dict[str, Any]:
    aid = _start_list_athlete_id(row)
    return {
        "id": _clean(row.get("id")) or f"{_clean(race.get('id'))}:{aid or athlete_name_from_api(athlete, aid) or hash(json.dumps(row, sort_keys=True, default=str))}",
        "race_id": _clean(race.get("id")),
        "race_slug": _clean(race.get("slug")),
        "race_name": _clean(race.get("name")),
        "race_date": date_from_api(race.get("date")),
        "event_hub_id": _clean(race.get("event_hub_id")),
        "athlete_id": aid,
        "athlete_name": athlete_name_from_api(athlete, aid),
        "athlete_slug": _clean((athlete or {}).get("slug")),
        "gender": _start_list_gender(row, athlete) or gender_from_api(athlete),
        "openrank": _start_list_openrank(row),
        "source_table": source,
        "raw": row,
    }


def fetch_races_for_start_lists(
    api_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    circuit: Optional[str] = None,
    brand: Optional[str] = None,
    max_races: int = 150,
    page_size: int = 200,
) -> List[Dict[str, Any]]:
    """Fetch race metadata without requiring has_results=true, for start lists."""
    if max_races <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))
    while len(rows) < max_races:
        params: Dict[str, Any] = {
            "select": "*",
            "order": "date.asc",
            "limit": min(page_size, max_races - len(rows)),
            "offset": offset,
        }
        and_clauses = []
        sd = _clean(start_date)
        ed = _clean(end_date)
        if sd:
            and_clauses.append(f"date.gte.{sd}")
        if ed:
            and_clauses.append(f"date.lte.{ed}")
        if and_clauses:
            params["and"] = "(" + ",".join(and_clauses) + ")"
        c = _clean(circuit)
        if c and c.lower() not in {"all", "any"}:
            params["circuit"] = f"eq.{c}"
        b = _clean(brand)
        if b and b.lower() not in {"all", "any"}:
            params["brand"] = f"eq.{b}"
        page = _get(api_key, "races", params, timeout=45)
        rows.extend(page)
        if len(page) < int(params["limit"]):
            break
        offset += int(params["limit"])
    return rows[:max_races]


def build_clean_start_list_sync(
    api_key: str,
    race_slugs: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    circuit: Optional[str] = None,
    brand: Optional[str] = None,
    max_races: int = 100,
    row_limit_per_race: int = 1000,
) -> Dict[str, Any]:
    """Build normalized start-list rows from any public TriNews start-list source discovered."""
    if not _clean(api_key):
        raise ValueError("TriNews API key is required.")
    logs: List[Dict[str, Any]] = []
    races: List[Dict[str, Any]] = []
    if race_slugs:
        for slug in race_slugs:
            s = _clean(slug)
            if not s:
                continue
            try:
                got = _get(api_key, "races", {"select": "*", "slug": f"eq.{s}", "limit": 1}, timeout=30)
                races.extend(got)
                logs.append({"stage": "race_lookup", "slug": s, "rows": len(got), "status": "ok"})
            except Exception as e:
                logs.append({"stage": "race_lookup", "slug": s, "status": "error", "error": str(e)})
    else:
        races = fetch_races_for_start_lists(api_key, start_date, end_date, circuit, brand, int(max_races))
        logs.append({"stage": "races_for_start_lists", "status": "ok", "rows": len(races)})

    raw_start_rows: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    athlete_ids: List[str] = []
    for race in races[: int(max_races)]:
        rows, log = discover_start_list_rows_for_race(api_key, race, int(row_limit_per_race))
        logs.append({"stage": "start_list_discovery", **{k: v for k, v in log.items() if k != "attempts"}})
        source = _clean(log.get("table"))
        for row in rows:
            raw_start_rows.append((row, race, source or "unknown"))
            aid = _start_list_athlete_id(row)
            if aid:
                athlete_ids.append(aid)

    athlete_map = fetch_by_ids(api_key, "athletes", athlete_ids) if athlete_ids else {}
    app_rows: List[Dict[str, Any]] = []
    source_rows: List[Dict[str, Any]] = []
    athlete_rows_by_url: Dict[str, Dict[str, Any]] = {}
    for raw_row, race, source in raw_start_rows:
        aid = _start_list_athlete_id(raw_row)
        athlete = athlete_map.get(aid)
        app_row = start_list_row_to_pick_row(raw_row, race, athlete)
        if app_row:
            app_rows.append(app_row)
            if athlete:
                master = athlete_master_row_from_api(athlete)
                url = _clean(master.get("athlete_url"))
                if url:
                    athlete_rows_by_url[url] = master
        source_rows.append(trinews_start_list_source_row(raw_row, race, athlete, source))

    return {
        "start_lists": app_rows,
        "athletes": list(athlete_rows_by_url.values()),
        "trinews_start_lists": source_rows,
        "logs": logs,
        "summary": {
            "races_checked": len(races),
            "raw_start_rows": len(raw_start_rows),
            "start_list_rows": len(app_rows),
            "athletes": len(athlete_rows_by_url),
        },
    }


# Override earlier build_full_clean_api_rebuild with start-list-aware version.
def build_full_clean_api_rebuild(
    api_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    circuit: Optional[str] = None,
    brand: Optional[str] = None,
    max_races: int = 250,
    race_result_limit: int = 1000,
    sync_all_pro_athletes: bool = False,
    max_athletes: int = 10000,
    sync_start_lists: bool = False,
    start_list_start_date: Optional[str] = None,
    start_list_end_date: Optional[str] = None,
    max_start_list_races: int = 150,
) -> Dict[str, Any]:
    """Full fresh build: athletes, races, clean results, and optional start lists."""
    if not _clean(api_key):
        raise ValueError("TriNews API key is required.")

    logs: List[Dict[str, Any]] = []
    races = fetch_races(api_key, start_date, end_date, circuit, brand, int(max_races))
    logs.append({"stage": "races", "status": "ok", "rows": len(races)})

    race_map: Dict[str, Dict[str, Any]] = {}
    race_results_by_race: Dict[str, List[Dict[str, Any]]] = {}
    all_results: List[Dict[str, Any]] = []
    for race in races:
        rid = _clean(race.get("id"))
        if not rid:
            continue
        race_map[rid] = race
        try:
            results = fetch_results_for_race(api_key, rid, int(race_result_limit))
            race_results_by_race[rid] = results
            all_results.extend(results)
            logs.append({"stage": "results", "race_id": rid, "race_name": race.get("name"), "rows": len(results), "status": "ok"})
        except Exception as e:
            logs.append({"stage": "results", "race_id": rid, "race_name": race.get("name"), "status": "error", "error": str(e)})

    computed_sof = {rid: computed_race_sof_from_results(rows) for rid, rows in race_results_by_race.items()}
    athlete_ids = [_clean(r.get("athlete_id")) for r in all_results if _clean(r.get("athlete_id"))]
    athlete_map = fetch_by_ids(api_key, "athletes", athlete_ids) if athlete_ids else {}
    logs.append({"stage": "athletes_from_results", "status": "ok", "rows": len(athlete_map)})

    if sync_all_pro_athletes:
        try:
            pro_rows = fetch_all_pro_athletes(api_key, max_athletes=int(max_athletes))
            for a in pro_rows:
                aid = _clean(a.get("id"))
                if aid:
                    athlete_map[aid] = a
            logs.append({"stage": "all_pro_athletes", "status": "ok", "rows": len(pro_rows)})
        except Exception as e:
            logs.append({"stage": "all_pro_athletes", "status": "error", "error": str(e)})

    app_result_rows: List[Dict[str, Any]] = []
    source_result_rows: List[Dict[str, Any]] = []
    for r in all_results:
        rid = _clean(r.get("race_id"))
        aid = _clean(r.get("athlete_id"))
        race = dict(race_map.get(rid) or {})
        if _as_float(race.get("strength_of_field")) is None and computed_sof.get(rid) is not None:
            race["strength_of_field"] = computed_sof.get(rid)
        athlete = athlete_map.get(aid)
        row = result_to_pick_rows(r, race, athlete)
        if _clean(row.get("athlete_name")) and _clean(row.get("race_name")):
            app_result_rows.append(row)
        source_result_rows.append(trinews_result_source_row(r, race, athlete))

    start_list_payload: Dict[str, Any] = {"start_lists": [], "athletes": [], "trinews_start_lists": [], "logs": [], "summary": {}}
    if sync_start_lists:
        try:
            start_list_payload = build_clean_start_list_sync(
                api_key=api_key,
                race_slugs=None,
                start_date=start_list_start_date,
                end_date=start_list_end_date,
                circuit=circuit,
                brand=brand,
                max_races=int(max_start_list_races),
            )
            logs.extend(start_list_payload.get("logs", []))
            for a in start_list_payload.get("athletes", []) or []:
                # Convert back from app athlete row only if possible; for local
                # app output this is enough, source athlete table uses API map.
                pass
        except Exception as e:
            logs.append({"stage": "start_lists", "status": "error", "error": str(e)})

    athlete_rows = [athlete_master_row_from_api(a) for a in athlete_map.values()]
    for a in start_list_payload.get("athletes", []) or []:
        athlete_rows.append(a)
    athlete_rows_by_url: Dict[str, Dict[str, Any]] = {}
    for row in athlete_rows:
        url = _clean(row.get("athlete_url"))
        if url:
            athlete_rows_by_url[url] = row

    source_athletes = [trinews_athlete_source_row(a) for a in athlete_map.values()]
    source_races = [trinews_race_source_row(r, computed_sof.get(_clean(r.get("id")))) for r in races]

    rows_with_swim = sum(1 for r in app_result_rows if r.get("swim_seconds"))
    rows_with_bike = sum(1 for r in app_result_rows if r.get("bike_seconds"))
    rows_with_run = sum(1 for r in app_result_rows if r.get("run_seconds"))
    return {
        "athletes": list(athlete_rows_by_url.values()),
        "athlete_results": app_result_rows,
        "race_field_results": app_result_rows,
        "start_lists": start_list_payload.get("start_lists", []) or [],
        "trinews_athletes": source_athletes,
        "trinews_races": source_races,
        "trinews_results": source_result_rows,
        "trinews_start_lists": start_list_payload.get("trinews_start_lists", []) or [],
        "logs": logs,
        "summary": {
            "races": len(races),
            "results": len(all_results),
            "app_result_rows": len(app_result_rows),
            "athletes": len(athlete_rows_by_url),
            "source_athletes": len(source_athletes),
            "source_races": len(source_races),
            "source_results": len(source_result_rows),
            "rows_with_swim": rows_with_swim,
            "rows_with_bike": rows_with_bike,
            "rows_with_run": rows_with_run,
            "computed_sof_races": sum(1 for v in computed_sof.values() if v is not None),
            "start_list_rows": len(start_list_payload.get("start_lists", []) or []),
            "trinews_start_list_rows": len(start_list_payload.get("trinews_start_lists", []) or []),
        },
    }


# ============================================================
# Fast sample/API test helpers for the simplified rebuild UI
# ============================================================
# Keep start-list discovery intentionally small so preview/test runs do not sit
# for minutes trying every possible table signature.
START_LIST_CANDIDATE_TABLES = [
    "start_lists",
    "race_start_lists",
    "race_entries",
    "entries",
    "race_participants",
    "participants",
]
START_LIST_FILTER_CANDIDATES = [
    ("race_id", "id"),
    ("event_hub_id", "event_hub_id"),
    ("race_slug", "slug"),
]


def _sample_summary_row(name: str, status: str, rows: int = 0, note: Optional[str] = None) -> Dict[str, Any]:
    return {"Pull": name, "Status": status, "Rows": int(rows or 0), "Note": note or ""}


def test_api_pulls(
    api_key: str,
    athlete_query: str = "Hanne De Vet",
    race_slug: str = "t100-triathlon-world-tour-spain-2026",
    limit: int = 10,
) -> Dict[str, Any]:
    """Small read-only API test used by the Streamlit UI.

    It intentionally limits each pull to a handful of rows and never writes to
    Supabase. This is the safe first step before a fresh rebuild.
    """
    if not _clean(api_key):
        raise ValueError("TriNews API key is required.")
    limit = max(1, min(int(limit or 10), 25))
    samples: Dict[str, Any] = {}
    summary: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    # 1) Athletes sample
    status, data = _get_optional(api_key, "athletes", {"select": "*", "is_pro": "eq.true", "limit": limit, "order": "full_name.asc"})
    rows = data if isinstance(data, list) else []
    samples["athletes_sample"] = rows[:limit] if rows else data
    summary.append(_sample_summary_row("/athletes?is_pro=true", "ok" if status == 200 else f"error {status}", len(rows), "Pro athlete sample"))
    if status != 200:
        errors.append({"pull": "athletes_sample", "status": status, "error": str(data)[:500]})

    # 2) Search athlete + direct athlete profile + athlete results.
    athlete_row = None
    athlete_id = None
    if _clean(athlete_query):
        try:
            athlete_row, resolve_log = resolve_athlete(api_key, athlete_query)
            samples["athlete_resolve"] = [{"resolve_log": resolve_log, "athlete": athlete_row}]
            athlete_id = _clean((athlete_row or {}).get("id") or (athlete_row or {}).get("athlete_id"))
            summary.append(_sample_summary_row("search_athletes + /athletes?id", "ok" if athlete_id else "no_match", 1 if athlete_id else 0, athlete_id or "No athlete id found"))
        except Exception as e:
            errors.append({"pull": "athlete_resolve", "status": "exception", "error": str(e)[:500]})
            summary.append(_sample_summary_row("search_athletes + /athletes?id", "error", 0, str(e)[:180]))

    if athlete_id:
        status, data = _get_optional(api_key, "results", {"select": "*", "athlete_id": f"eq.{athlete_id}", "limit": limit, "order": "created_at.desc"})
        rows = data if isinstance(data, list) else []
        samples["athlete_results"] = rows[:limit] if rows else data
        summary.append(_sample_summary_row("/results?athlete_id=...", "ok" if status == 200 else f"error {status}", len(rows), "Recent results for test athlete"))
        if status != 200:
            errors.append({"pull": "athlete_results", "status": status, "error": str(data)[:500]})

    # 3) Races sample / exact race.
    race_row = None
    race_id = None
    if _clean(race_slug):
        status, data = _get_optional(api_key, "races", {"select": "*", "slug": f"eq.{race_slug}", "limit": 1})
        rows = data if isinstance(data, list) else []
        if rows:
            race_row = rows[0]
            race_id = _clean(race_row.get("id"))
        samples["race_lookup"] = rows if rows else data
        summary.append(_sample_summary_row("/races?slug=...", "ok" if status == 200 and rows else f"error {status}" if status != 200 else "no_match", len(rows), race_id or "No race id"))
        if status != 200:
            errors.append({"pull": "race_lookup", "status": status, "error": str(data)[:500]})

    if not race_id:
        status, data = _get_optional(api_key, "races", {"select": "*", "has_results": "eq.true", "limit": limit, "order": "date.desc"})
        rows = data if isinstance(data, list) else []
        samples["races_sample"] = rows[:limit] if rows else data
        if rows:
            race_row = rows[0]
            race_id = _clean(race_row.get("id"))
        summary.append(_sample_summary_row("/races?has_results=true", "ok" if status == 200 else f"error {status}", len(rows), race_id or "No race id"))
        if status != 200:
            errors.append({"pull": "races_sample", "status": status, "error": str(data)[:500]})

    # 4) Race results sample.
    if race_id:
        status, data = _get_optional(api_key, "results", {"select": "*", "race_id": f"eq.{race_id}", "limit": limit, "order": "placement.asc"})
        rows = data if isinstance(data, list) else []
        samples["race_results"] = rows[:limit] if rows else data
        summary.append(_sample_summary_row("/results?race_id=...", "ok" if status == 200 else f"error {status}", len(rows), "Clean leg times should be here"))
        if status != 200:
            errors.append({"pull": "race_results", "status": status, "error": str(data)[:500]})

    # 5) Start-list discovery sample.
    if race_row:
        try:
            attempts = probe_start_list_sources_for_race(api_key, race_row, limit=limit)
            samples["start_list_probe"] = attempts[:20]
            found = [a for a in attempts if a.get("status") == 200 and int(a.get("row_count") or 0) > 0]
            summary.append(_sample_summary_row("start-list source probe", "ok" if found else "not_found", found[0].get("row_count", 0) if found else 0, (f"{found[0].get('table')}.{found[0].get('filter_column')}" if found else "No non-empty public start-list source found in quick probe")))
        except Exception as e:
            errors.append({"pull": "start_list_probe", "status": "exception", "error": str(e)[:500]})
            summary.append(_sample_summary_row("start-list source probe", "error", 0, str(e)[:180]))

    return {"summary": summary, "samples": samples, "errors": errors}
