import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from zoneinfo import ZoneInfo

from .playlist import PlaylistEntry

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
TITLE_PREFIX = "B1G+:"
UPCOMING_PREFIX = "UPCOMING: "
ENDED_PREFIX = "ENDED: "
ENDED_HORIZON_HOURS = 3


def _format_xmltv_time(dt_str: Optional[str]) -> str:
    if not dt_str:
        return ""
    try:
        from dateutil import parser as dateparser
        dt = dateparser.parse(dt_str)
        dt = dt.astimezone(PACIFIC)
        return dt.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        return dt_str


def _build_channel_id(entry: PlaylistEntry, prefix: str = "B1G+") -> str:
    name_clean = "".join(c if c.isalnum() else "_" for c in entry.name)
    return f"{prefix}.{name_clean}"


def _build_categories(metadata: dict) -> list[str]:
    categories = ["Sports", "NCAA"]
    gender = metadata.get("gender") or ""
    if gender:
        categories.append(f"NCAA {gender}")
    genre = metadata.get("genre") or ""
    if genre and genre not in categories:
        categories.append(genre)
    league = metadata.get("league") or ""
    if league and league not in categories:
        categories.append(league)
    conference = metadata.get("conference") or ""
    if conference and conference not in categories:
        categories.append(conference)
    return categories


def _build_keywords(metadata: dict) -> list[str]:
    keywords = []
    keywords.append("NCAA")
    gender = metadata.get("gender") or ""
    if gender:
        keywords.append(f"NCAA {gender}")
    genre = metadata.get("genre") or ""
    if genre:
        keywords.append(genre)
    sport_base = metadata.get("sport_base") or ""
    if sport_base:
        keywords.append(sport_base)
    league = metadata.get("league") or ""
    if league:
        keywords.append(league)
    conference = metadata.get("conference") or ""
    if conference:
        keywords.append(conference)
    away_team = metadata.get("away_team") or ""
    if away_team:
        keywords.append(away_team)
    home_team = metadata.get("home_team") or ""
    if home_team:
        keywords.append(home_team)
    return list(dict.fromkeys(keywords))


def _build_description(metadata: dict) -> str:
    parts = []
    genre = metadata.get("genre") or ""
    if genre:
        parts.append(genre)
    away_team = metadata.get("away_team") or ""
    home_team = metadata.get("home_team") or ""
    if away_team and home_team:
        parts.append(f"{away_team} at {home_team}")
    conference = metadata.get("conference") or ""
    if conference:
        parts.append(conference)
    return " — ".join(parts)


def _emit_programme(
    parent,
    channel_id: str,
    title: str,
    start_dt,
    end_dt,
    metadata: Optional[dict] = None,
    image_url: str = "",
    is_live: bool = False,
):
    prog = SubElement(parent, "programme")
    prog.set("channel", channel_id)
    prog.set("start", _format_xmltv_time(start_dt.isoformat()))
    prog.set("stop", _format_xmltv_time(end_dt.isoformat()))

    title_el = SubElement(prog, "title")
    title_el.set("lang", "en")
    title_el.text = title

    if image_url:
        icon_el = SubElement(prog, "icon")
        icon_el.set("src", image_url)

    metadata = metadata or {}

    subtitle = metadata.get("subtitle") or ""
    if subtitle:
        sub_el = SubElement(prog, "sub-title")
        sub_el.set("lang", "en")
        sub_el.text = subtitle

    desc_text = metadata.get("description") or _build_description(metadata)
    if desc_text:
        desc_el = SubElement(prog, "desc")
        desc_el.set("lang", "en")
        desc_el.text = desc_text

    date = metadata.get("date")
    if date:
        date_el = SubElement(prog, "date")
        date_el.text = str(date)

    duration = metadata.get("duration_minutes")
    if duration and int(duration) > 0:
        length_el = SubElement(prog, "length")
        length_el.set("units", "minutes")
        length_el.text = str(int(duration))

    for cat in _build_categories(metadata):
        cat_el = SubElement(prog, "category")
        cat_el.set("lang", "en")
        cat_el.text = cat

    for keyword in _build_keywords(metadata):
        kw_el = SubElement(prog, "keyword")
        kw_el.set("lang", "en")
        kw_el.text = keyword

    if is_live:
        SubElement(prog, "live")


def generate_xmltv(
    matches: list[tuple[PlaylistEntry, dict]],
    prefix: str = "B1G+",
) -> str:
    root = Element("tv")
    root.set("generator-info-name", "Dispatcharr B1G+ EPG Generator")

    for entry, metadata in matches:
        channel_id = _build_channel_id(entry, prefix)

        channel_el = SubElement(root, "channel")
        channel_el.set("id", channel_id)

        display_name = SubElement(channel_el, "display-name")
        display_name.text = entry.name

        if entry.tvg_logo:
            icon = SubElement(channel_el, "icon")
            icon.set("src", entry.tvg_logo)

        real_start_str = metadata.get("start_time") or ""
        real_end_str = metadata.get("end_time") or ""
        if not real_start_str or not real_end_str:
            continue

        try:
            from dateutil import parser as dateparser
            real_start = dateparser.parse(real_start_str).astimezone(PACIFIC)
            real_end = dateparser.parse(real_end_str).astimezone(PACIFIC)
            if real_end <= real_start:
                continue
        except Exception:
            continue

        real_title = f"{TITLE_PREFIX} {(metadata.get('short_name') or metadata.get('title') or entry.name).strip()}"
        image_url = metadata.get("image_url") or ""
        is_studio = metadata.get("is_studio", False)

        day_before = real_start - timedelta(days=1)
        upcoming_start_pt = day_before.replace(hour=0, minute=0, second=0, microsecond=0)

        if upcoming_start_pt < real_start:
            _emit_programme(
                root, channel_id,
                title=UPCOMING_PREFIX + real_title,
                start_dt=upcoming_start_pt,
                end_dt=real_start,
                metadata=metadata,
                image_url=image_url,
            )

        _emit_programme(
            root, channel_id,
            title=real_title,
            start_dt=real_start,
            end_dt=real_end,
            metadata=metadata,
            image_url=image_url,
            is_live=not is_studio,
        )

        ended_end_pt = real_end + timedelta(hours=ENDED_HORIZON_HOURS)
        _emit_programme(
            root, channel_id,
            title=ENDED_PREFIX + real_title,
            start_dt=real_end,
            end_dt=ended_end_pt,
            metadata=metadata,
            image_url=image_url,
        )

    rough_string = tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough_string.encode("utf-8"))
    pretty = reparsed.toprettyxml(indent="  ", encoding="utf-8")
    return pretty.decode("utf-8") if isinstance(pretty, bytes) else pretty


def get_channel_id(entry: PlaylistEntry, prefix: str = "B1G+") -> str:
    return _build_channel_id(entry, prefix)