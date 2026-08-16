import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BIGTENPLUS_API_BASE = "https://www.bigtenplus.com/api/v3"
EASTERN = ZoneInfo("America/New_York")
SCHEDULE_PAGE_SLUG = "schedule"
SCHEDULE_MODULE_TYPE = "Event Based Schedule"

DEFAULT_PAGE_LIMIT = 100
MAX_PAGES = 10

DURATION_HOURS_BY_SPORT = {
    "baseball": 3.5,
    "basketball": 3,
    "football": 3.5,
    "golf": 6,
    "hockey": 3,
    "soccer": 2.5,
    "tennis": 3,
    "volleyball": 2.5,
}

DURATION_SETTING_KEYS = (
    "default_duration_hours",
    "baseball_duration_hours",
    "basketball_duration_hours",
    "football_duration_hours",
    "golf_duration_hours",
    "hockey_duration_hours",
    "soccer_duration_hours",
    "tennis_duration_hours",
    "volleyball_duration_hours",
    "gymnastics_dual_duration_hours",
    "gymnastics_multi_duration_hours",
)

EXTRA_COMPETITORS_FIELD = "extra competitors"

_module_id_cache: Optional[int] = None


def _get(url: str, timeout: float = 30.0) -> Optional[dict]:
    import requests

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Big Ten Plus API request failed: GET {url}: {e}")
        return None


def discover_schedule_module(
    timeout: float = 30.0,
    cache: bool = True,
) -> Optional[int]:
    """Find the 'Event Based Schedule' module id used by the schedule page.

    Resolves /api/v3/pages -> schedule page id -> /api/v3/pages/{id}/modules
    -> the module whose type is 'Event Based Schedule'.
    """
    global _module_id_cache
    if cache and _module_id_cache is not None:
        return _module_id_cache

    pages = _get(f"{BIGTENPLUS_API_BASE}/pages", timeout=timeout)
    if pages is None:
        return None
    page_list = (pages or {}).get("data") or []
    schedule_page = next(
        (p for p in page_list if (p or {}).get("slug") == SCHEDULE_PAGE_SLUG), None
    )
    if schedule_page is None:
        logger.warning("Could not locate the 'schedule' page in /api/v3/pages")
        return None
    page_id = schedule_page.get("id")
    if page_id is None:
        return None

    params = urlencode({"filter[deviceCategory]": 1})
    modules = _get(
        f"{BIGTENPLUS_API_BASE}/pages/{page_id}/modules?{params}",
        timeout=timeout,
    )
    if modules is None:
        return None
    module_list = (modules or {}).get("data") or []
    for mod in module_list:
        mod_type = ((mod or {}).get("type") or {})
        if mod_type.get("name") == SCHEDULE_MODULE_TYPE:
            module_id = mod.get("id")
            if module_id is not None:
                if cache:
                    _module_id_cache = module_id
                logger.info(f"Discovered Big Ten Plus schedule module id={module_id}")
                return module_id
    logger.warning("Could not locate an 'Event Based Schedule' module")
    return None


def get_day_bounds(day_iso: str) -> tuple[datetime, datetime]:
    """ET day bounds for a YYYY-MM-DD day, converted to aware UTC datetimes."""
    day = datetime.strptime(day_iso, "%Y-%m-%d").replace(tzinfo=EASTERN)
    return day.astimezone(timezone.utc), (day + timedelta(days=1)).astimezone(
        timezone.utc
    )


def count_event_teams(ev: dict) -> int:
    """Count competitors including those listed under 'extra competitors' metadata."""
    count = 0
    if ev.get("homeCompetitor"):
        count += 1
    if ev.get("awayCompetitor"):
        count += 1
    for meta in ev.get("metadata") or []:
        field = (meta or {}).get("field") or {}
        if (field.get("name") or "").lower() == EXTRA_COMPETITORS_FIELD:
            count += 1
    return count


def _hours_setting(settings: dict, key: str, default: float) -> float:
    try:
        value = float(settings.get(key))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return default


def build_durations_from_settings(settings: dict) -> dict:
    """Convert plugin settings into a sport-keyed duration map (hours)."""
    return {
        "default": _hours_setting(settings, "default_duration_hours", 3),
        "baseball": _hours_setting(settings, "baseball_duration_hours", 3.5),
        "basketball": _hours_setting(settings, "basketball_duration_hours", 3),
        "football": _hours_setting(settings, "football_duration_hours", 3.5),
        "golf": _hours_setting(settings, "golf_duration_hours", 6),
        "hockey": _hours_setting(settings, "hockey_duration_hours", 3),
        "soccer": _hours_setting(settings, "soccer_duration_hours", 2.5),
        "tennis": _hours_setting(settings, "tennis_duration_hours", 3),
        "volleyball": _hours_setting(settings, "volleyball_duration_hours", 2.5),
        "gymnastics_dual": _hours_setting(
            settings, "gymnastics_dual_duration_hours", 2
        ),
        "gymnastics_multi": _hours_setting(
            settings, "gymnastics_multi_duration_hours", 3.5
        ),
    }


def get_duration_minutes(ev: dict, durations: Optional[dict] = None) -> int:
    """Estimate event duration from the sport name and competitor count.

    Uses the per-sport duration map (hours), falling back to built-in
    defaults; gymnastics depends on the number of competing teams
    (dual meet = 2 teams, tri/quad = 3-4 teams).
    """
    durations = durations or {}
    sport = (((ev.get("category3") or {}).get("name")) or "").lower()

    if "gymnastics" in sport:
        teams = count_event_teams(ev)
        if teams <= 2:
            return int(durations.get("gymnastics_dual", 2) * 60)
        return int(durations.get("gymnastics_multi", 3.5) * 60)

    for key in DURATION_HOURS_BY_SPORT:
        if key in sport:
            hours = durations.get(key, DURATION_HOURS_BY_SPORT[key])
            return int(hours * 60)

    return int(durations.get("default", 3) * 60)


def _metadata_values(ev: dict, field_name: str) -> list[str]:
    """Collect metadata entry names whose field matches `field_name`."""
    results = []
    for meta in ev.get("metadata") or []:
        field = (meta or {}).get("field") or {}
        if (field.get("name") or "").lower() == field_name.lower():
            name = (meta.get("name") or "").strip()
            if name:
                results.append(name)
    return results


def detect_gender(ev: dict) -> str:
    for value in _metadata_values(ev, "gender"):
        v = value.strip().lower()
        if v in ("men", "male", "m"):
            return "Men"
        if v in ("women", "female", "w"):
            return "Women"
    name = (((ev.get("category3") or {}).get("name")) or "")
    match = re.search(r"\((M|W)\)\s*$", name)
    if match:
        return "Men" if match.group(1).upper() == "M" else "Women"
    return ""


def detect_sport_base(ev: dict) -> str:
    values = _metadata_values(ev, "sports")
    if values:
        return values[0]
    name = (((ev.get("category3") or {}).get("name")) or "")
    return re.sub(r"\s*\((?:M|W)\)\s*$", "", name).strip()


def detect_conference(ev: dict) -> str:
    values = _metadata_values(ev, "conference rights")
    return values[0] if values else ""


def detect_network(ev: dict) -> str:
    values = _metadata_values(ev, "network")
    if not values:
        values = _metadata_values(ev, "televised")
    return values[0] if values else ""


def build_genre_name(gender: str, sport_base: str) -> str:
    """Gracenote-style genre, e.g. 'NCAA Women's Soccer'."""
    gender = (gender or "").strip()
    sport_base = (sport_base or "").strip()
    if gender and sport_base:
        return f"NCAA {gender}'s {sport_base}"
    if sport_base:
        return f"NCAA {sport_base}"
    return "NCAA"


def _editorial_title(ev: dict) -> str:
    contents = ev.get("contents") or []
    for content in contents:
        editorial = (content or {}).get("editorial") or {}
        translations = editorial.get("translations") or {}
        en = translations.get("en") or {}
        title = (en.get("title") or "").strip()
        if title:
            return title
    return ""


def _editorial_description(ev: dict) -> str:
    contents = ev.get("contents") or []
    for content in contents:
        editorial = (content or {}).get("editorial") or {}
        translations = editorial.get("translations") or {}
        en = translations.get("en") or {}
        description = (en.get("description") or "").strip()
        if description:
            return description
    return ""


def _event_image_url(ev: dict) -> str:
    images = ev.get("images") or []
    if images:
        url = (images[0] or {}).get("url")
        if url:
            return url
    contents = ev.get("contents") or []
    for content in contents:
        editorial = (content or {}).get("editorial") or {}
        for image in editorial.get("images") or []:
            url = (image or {}).get("url")
            if url:
                return url
    return ""


def build_event_title(ev: dict) -> str:
    """Build a canonical matchable title: '<sport> <away> at <home>'."""
    sport = (((ev.get("category3") or {}).get("name")) or "").strip()
    home = ((ev.get("homeCompetitor") or {}).get("name") or "").strip()
    away = ((ev.get("awayCompetitor") or {}).get("name") or "").strip()

    if away and home:
        title = f"{away} at {home}"
    else:
        title = _editorial_title(ev)

    parts = [part for part in (sport, title) if part]
    return " ".join(parts).strip()


def _parse_event(ev: dict, durations: Optional[dict] = None) -> Optional[dict]:
    start_str = ev.get("startTime")
    if not start_str:
        return None
    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    duration = get_duration_minutes(ev, durations)
    end_dt = start_dt + timedelta(minutes=duration)

    title = build_event_title(ev)
    if not title:
        return None

    home_team = ((ev.get("homeCompetitor") or {}).get("name") or "").strip()
    away_team = ((ev.get("awayCompetitor") or {}).get("name") or "").strip()
    gender = detect_gender(ev)
    sport_base = detect_sport_base(ev)
    league = (((ev.get("category3") or {}).get("name")) or "")
    genre = build_genre_name(gender, sport_base)

    if away_team and home_team:
        subtitle = f"{away_team} at {home_team}"
    else:
        subtitle = _editorial_title(ev)

    return {
        "title": title,
        "short_name": title,
        "subtitle": subtitle,
        "description": _editorial_description(ev),
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "start_timestamp": int(start_dt.timestamp()),
        "end_timestamp": int(end_dt.timestamp()),
        "sport": league,
        "sport_abbrev": "",
        "sport_base": sport_base,
        "league": league,
        "league_abbrev": "",
        "category": league,
        "subcategory": "",
        "gender": gender,
        "genre": genre,
        "conference": detect_conference(ev),
        "network": detect_network(ev),
        "home_team": home_team,
        "away_team": away_team,
        "duration_minutes": duration,
        "date": start_dt.year,
        "is_studio": False,
        "image_url": _event_image_url(ev),
        "id": str(ev.get("id") or ""),
    }


def fetch_bigtenplus_schedule(
    day_iso: str,
    module_id: Optional[int] = None,
    timeout: float = 30.0,
    durations: Optional[dict] = None,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """Fetch the Big Ten Plus schedule for a single YYYY-MM-DD day."""
    if module_id is None:
        module_id = discover_schedule_module(timeout=timeout)
    if module_id is None:
        logger.warning("No Big Ten Plus schedule module id available — skipping fetch")
        return []

    from_utc, to_utc = get_day_bounds(day_iso)
    parsed: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "filter[date]": day_iso,
            "filter[deviceCategory]": 1,
            "filter[dateTimeFrom]": from_utc.isoformat(),
            "filter[dateTimeTo]": to_utc.isoformat(),
            "limit": page_limit,
            "page": page,
        }
        url = (
            f"{BIGTENPLUS_API_BASE}/modules/{module_id}/contents?"
            f"{urlencode(params)}"
        )
        payload = _get(url, timeout=timeout)
        if payload is None:
            break
        data = payload.get("data") or []
        for ev in data:
            event = _parse_event(ev, durations)
            if event:
                parsed.append(event)

        meta = payload.get("meta") or {}
        last_page = meta.get("last_page")
        current_page = meta.get("current_page") or page
        if last_page is None or current_page >= int(last_page):
            break

    logger.info(f"Downloaded Big Ten Plus schedule: {len(parsed)} events (day={day_iso})")
    return parsed