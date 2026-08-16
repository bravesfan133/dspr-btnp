from datetime import datetime, timezone

from bigtenplus_plugin.matcher import match_events, extract_core_title
from bigtenplus_plugin.playlist import PlaylistEntry


def make_entry(name: str, start_time: datetime = None) -> PlaylistEntry:
    if start_time is None:
        start_time = datetime.now(timezone.utc)
    entry = PlaylistEntry(
        name=name,
        stream_url="http://example.com/stream",
        start_time=start_time,
    )
    return entry


def make_event(title: str, start_ts: int = 0) -> dict:
    return {
        "title": title,
        "short_name": title,
        "start_timestamp": start_ts,
        "end_timestamp": start_ts + 7200,
        "start_time": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "end_time": datetime.fromtimestamp(start_ts + 7200, tz=timezone.utc).isoformat(),
        "sport": "Soccer (W)",
        "league": "Soccer (W)",
        "is_studio": False,
    }


def test_exact_title_match():
    entry = make_entry(
        "BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET"
    )
    event = make_event("Soccer (W) Georgia at Minnesota")
    matches = match_events([entry], [event])
    assert len(matches) == 1
    assert matches[0][1]["title"] == event["title"]


def test_substring_match():
    entry = make_entry(
        "BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET"
    )
    event = make_event("Soccer (W) Georgia at Minnesota (Regular Season)")
    matches = match_events([entry], [event])
    assert len(matches) == 1


def test_case_insensitive_match():
    entry = make_entry(
        "BIG10+ 02: soccer (w) georgia at minnesota Sun @ Aug 16 01:00PM ET"
    )
    event = make_event("Soccer (W) Georgia at Minnesota")
    matches = match_events([entry], [event])
    assert len(matches) == 1


def test_no_start_time():
    entry = PlaylistEntry(
        name="BIG10+ 11: Some Event Sun @ Aug 16 12:00PM ET",
        stream_url="http://example.com/stream",
        start_time=None,
    )
    event = make_event("Some Event")
    matches = match_events([entry], [event])
    assert len(matches) == 1


def test_fuzzy_match_fallback():
    entry = make_entry(
        "BIG10+ 05: Volleyball (W) Red vs. White Scrimmage Sun @ Aug 16 04:00PM ET"
    )
    event1 = make_event("Volleyball (W) Nebraska Black vs. Gold Scrimmage")
    event2 = make_event("Volleyball (W) Red vs. White Scrimmage")
    matches = match_events([entry], [event1, event2])
    assert len(matches) == 1
    assert matches[0][1]["title"] == "Volleyball (W) Red vs. White Scrimmage"


def test_no_match():
    entry = make_entry(
        "BIG10+ 99: Basketball (M) Michigan at Ohio State Sun @ Aug 16 08:00PM ET"
    )
    event = make_event("Unrelated Show")
    matches = match_events([entry], [event])
    assert len(matches) == 0


def test_extract_core_title_basic():
    result = extract_core_title(
        "BIG10+ 27: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET"
    )
    assert result == "Soccer (W) Georgia at Minnesota"


def test_extract_core_title_no_prefix():
    result = extract_core_title("Just a regular name")
    assert result == "Just a regular name"


def test_extract_core_title_without_weekday():
    result = extract_core_title(
        "BIG10+ 123: Soccer (W) Georgia at Minnesota @ Aug 16 01:00PM ET"
    )
    assert result == "Soccer (W) Georgia at Minnesota"