from datetime import datetime
from zoneinfo import ZoneInfo

from bigtenplus_plugin.playlist import (
    event_ends_after,
    extract_b1g_datetime,
    extract_display_title,
    filter_by_keyword,
    filter_entries_by_day,
    PlaylistEntry,
)


def test_extract_datetime_evening():
    name = "BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.tzinfo.key == "US/Eastern"
    assert dt.hour == 13
    assert dt.minute == 0
    assert dt.month == 8


def test_extract_datetime_morning():
    name = "BIG10+ 03: Football Michigan at Ohio State Sat @ Sep 12 10:30AM ET"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.month == 9
    assert dt.day == 12


def test_extract_datetime_noon():
    name = "BIG10+ 04: Basketball (M) Purdue at Indiana Wed @ Jan 7 12:00PM ET"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.hour == 12
    assert dt.minute == 0


def test_extract_datetime_midnight():
    name = "BIG10+ 05: Volleyball (W) Nebraska at Wisconsin Fri @ Oct 9 12:00AM ET"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.hour == 0
    assert dt.minute == 0


def test_extract_datetime_central_time():
    name = "BIG10+ 06: Hockey Minnesota at Wisconsin Sat @ Nov 14 07:00PM CT"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.tzinfo.key == "US/Central"
    assert dt.hour == 19


def test_extract_datetime_no_tz_defaults_eastern():
    name = "BIG10+ 06: Hockey Minnesota at Wisconsin Sat @ Nov 14 07:00PM"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.tzinfo.key == "US/Eastern"


def test_no_big10_prefix():
    assert extract_b1g_datetime("Some other channel") is None


def test_missing_time():
    assert extract_b1g_datetime("BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16") is None


def test_missing_date():
    assert extract_b1g_datetime("BIG10+ 02: Soccer (W) Georgia at Minnesota 01:00PM ET") is None


def test_extract_display_title_with_weekday():
    name = "BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET"
    title = extract_display_title(name)
    assert title == "Soccer (W) Georgia at Minnesota"


def test_extract_display_title_without_weekday():
    name = "BIG10+ 02: Soccer (W) Georgia at Minnesota @ Aug 16 01:00PM ET"
    title = extract_display_title(name)
    assert title == "Soccer (W) Georgia at Minnesota"


def test_extract_display_title_scrimmage():
    name = "BIG10+ 06: Volleyball (W) Red vs. White Scrimmage Sun @ Aug 16 04:00PM ET"
    title = extract_display_title(name)
    assert title == "Volleyball (W) Red vs. White Scrimmage"


def test_et_conversion():
    name = "BIG10+ 01: Soccer (W) Fordham at Maryland Sun @ Aug 16 12:00PM ET"
    dt = extract_b1g_datetime(name)
    assert dt is not None
    assert dt.tzinfo.key == "US/Eastern"
    assert dt.day == 16
    assert dt.hour == 12
    assert dt.minute == 0


def make_entry(name: str) -> PlaylistEntry:
    entry = PlaylistEntry(name=name, stream_url="http://example.com/stream")
    entry.start_time = extract_b1g_datetime(name)
    return entry


def test_filter_entries_by_day_keeps_target_days():
    today = make_entry("BIG10+ 01: Soccer (W) Fordham at Maryland Sun @ Aug 16 12:00PM ET")
    tomorrow = make_entry("BIG10+ 02: Soccer (W) Georgia at Minnesota Mon @ Aug 17 01:00PM ET")
    entries = [today, tomorrow]
    filtered = filter_entries_by_day(entries, ["2026-08-16", "2026-08-17"])
    assert filtered == [today, tomorrow]


def test_filter_entries_by_day_drops_off_day():
    yesterday = make_entry("BIG10+ 01: Soccer (W) Fordham at Maryland Sat @ Aug 15 12:00PM ET")
    today = make_entry("BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET")
    filtered = filter_entries_by_day([yesterday, today], ["2026-08-16"])
    assert filtered == [today]


def test_filter_entries_by_day_drops_undated():
    undated = PlaylistEntry(name="BIG10+ 3: Some Event", stream_url="http://example.com/stream")
    today = make_entry("BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET")
    filtered = filter_entries_by_day([undated, today], ["2026-08-16"])
    assert filtered == [today]


def test_filter_by_keyword():
    e1 = make_entry("BIG10+ 01: Soccer (W) Fordham at Maryland Sun @ Aug 16 12:00PM ET")
    e2 = PlaylistEntry(name="ESPN+ 1: NBA Lakers at Celtics", stream_url="http://example.com")
    filtered = filter_by_keyword([e1, e2], keyword="BIG10+")
    assert filtered == [e1]


def make_event(start: datetime, end: datetime) -> dict:
    return {"start_time": start.isoformat(), "end_time": end.isoformat()}


def test_event_ends_after_crosses_boundary():
    eastern = ZoneInfo("US/Eastern")
    boundary = datetime(2026, 8, 1, 0, 0, tzinfo=eastern)
    start = datetime(2026, 7, 31, 23, 30, tzinfo=eastern)
    end = datetime(2026, 8, 1, 1, 0, tzinfo=eastern)
    assert event_ends_after([make_event(start, end)], start, boundary) is True


def test_event_ends_after_ends_before_boundary():
    eastern = ZoneInfo("US/Eastern")
    boundary = datetime(2026, 8, 1, 0, 0, tzinfo=eastern)
    start = datetime(2026, 7, 31, 18, 0, tzinfo=eastern)
    end = datetime(2026, 7, 31, 20, 0, tzinfo=eastern)
    assert event_ends_after([make_event(start, end)], start, boundary) is False


def test_event_ends_after_no_matching_start_time():
    eastern = ZoneInfo("US/Eastern")
    boundary = datetime(2026, 8, 1, 0, 0, tzinfo=eastern)
    event_start = datetime(2026, 7, 31, 18, 0, tzinfo=eastern)
    event_end = datetime(2026, 8, 1, 1, 0, tzinfo=eastern)
    query_start = datetime(2026, 7, 31, 19, 0, tzinfo=eastern)
    assert event_ends_after([make_event(event_start, event_end)], query_start, boundary) is False


def test_event_ends_after_missing_end_time():
    eastern = ZoneInfo("US/Eastern")
    boundary = datetime(2026, 8, 1, 0, 0, tzinfo=eastern)
    start = datetime(2026, 7, 31, 23, 30, tzinfo=eastern)
    event = {"start_time": start.isoformat(), "end_time": None}
    assert event_ends_after([event], start, boundary) is False


def test_event_ends_after_empty_events():
    eastern = ZoneInfo("US/Eastern")
    boundary = datetime(2026, 8, 1, 0, 0, tzinfo=eastern)
    start = datetime(2026, 7, 31, 23, 30, tzinfo=eastern)
    assert event_ends_after([], start, boundary) is False