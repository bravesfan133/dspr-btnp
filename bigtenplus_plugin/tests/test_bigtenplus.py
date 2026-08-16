import json
from datetime import datetime, timedelta
from pathlib import Path

from bigtenplus_plugin.bigtenplus import (
    build_durations_from_settings,
    build_event_title,
    build_genre_name,
    count_event_teams,
    detect_gender,
    detect_sport_base,
    discover_schedule_module,
    fetch_bigtenplus_schedule,
    get_day_bounds,
    get_duration_minutes,
    _parse_event,
)

FIXTURE = Path(__file__).parent / "fixtures" / "events_2026-08-16.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def make_event(category3="Soccer (W)", home="Minnesota", away="Georgia", start=None):
    return {
        "id": 123,
        "title": "",
        "startTime": start or "2026-08-16T17:00:00+00:00",
        "endTime": None,
        "category3": {"name": category3},
        "homeCompetitor": {"name": home},
        "awayCompetitor": {"name": away},
        "metadata": [],
        "contents": [],
        "images": [],
    }


def test_parse_real_day_payload():
    fixture = load_fixture()
    events = [_parse_event(ev) for ev in fixture["data"]]
    assert len(events) == 7
    assert all(e is not None for e in events)

    soccer = next(
        e for e in events if e["id"] == str(
            next(ev["id"] for ev in fixture["data"] if (ev["homeCompetitor"] or {}).get("name") == "Maryland")
        )
    )
    assert soccer["title"] == "Soccer (W) Fordham at Maryland"
    assert soccer["start_time"].startswith("2026-08-16T16:00:00")
    assert soccer["sport"] == "Soccer (W)" == soccer["league"]
    assert soccer["gender"] == "Women"
    assert soccer["sport_base"] == "Soccer"
    assert soccer["genre"] == "NCAA Women's Soccer"
    assert soccer["home_team"] == "Maryland"
    assert soccer["away_team"] == "Fordham"
    assert soccer["conference"] == "Big Ten"
    assert soccer["duration_minutes"] == 150
    assert soccer["date"] == 2026
    assert soccer["subtitle"] == "Fordham at Maryland"


def test_parse_scrimmage_uses_editorial_title():
    fixture = load_fixture()
    scrimmage = next(
        ev for ev in fixture["data"] if not ev.get("homeCompetitor")
    )
    event = _parse_event(scrimmage)
    assert event["title"] == "Volleyball (W) Nebraska Red vs. White Scrimmage"


def test_build_event_title_home_away():
    ev = make_event(home="Maryland", away="Fordham")
    assert build_event_title(ev) == "Soccer (W) Fordham at Maryland"


def test_build_event_title_missing_competitors():
    ev = {
        "category3": {"name": "Volleyball (W)"},
        "homeCompetitor": None,
        "awayCompetitor": None,
        "contents": [
            {
                "editorial": {
                    "translations": {"en": {"title": "Nebraska Red vs. White Scrimmage"}}
                }
            }
        ],
    }
    assert build_event_title(ev) == "Volleyball (W) Nebraska Red vs. White Scrimmage"


def test_detect_gender_from_metadata():
    ev = make_event(category3="Soccer (W)")
    ev["metadata"] = [{"field": {"name": "gender"}, "name": "Women"}]
    assert detect_gender(ev) == "Women"


def test_detect_gender_from_suffix():
    assert detect_gender(make_event(category3="Basketball (M)")) == "Men"
    assert detect_gender(make_event(category3="Soccer (W)")) == "Women"
    assert detect_gender(make_event(category3="Football")) == ""


def test_detect_sport_base_from_metadata():
    ev = make_event(category3="Soccer (W)")
    ev["metadata"] = [{"field": {"name": "sports"}, "name": "Soccer"}]
    assert detect_sport_base(ev) == "Soccer"


def test_detect_sport_base_strips_suffix():
    assert detect_sport_base(make_event(category3="Ice Hockey (W)")) == "Ice Hockey"
    assert detect_sport_base(make_event(category3="Baseball")) == "Baseball"


def test_build_genre_name():
    assert build_genre_name("Women", "Soccer") == "NCAA Women's Soccer"
    assert build_genre_name("Men", "Basketball") == "NCAA Men's Basketball"
    assert build_genre_name("", "Volleyball") == "NCAA Volleyball"
    assert build_genre_name("", "") == "NCAA"


def test_duration_soccer():
    assert get_duration_minutes(make_event(category3="Soccer (W)")) == 150


def test_duration_baseball():
    assert get_duration_minutes(make_event(category3="Baseball")) == 210


def test_duration_football():
    assert get_duration_minutes(make_event(category3="Football")) == 210


def test_duration_basketball():
    assert get_duration_minutes(make_event(category3="Basketball (M)")) == 180


def test_duration_golf():
    assert get_duration_minutes(make_event(category3="Golf (M)")) == 360


def test_duration_hockey():
    assert get_duration_minutes(make_event(category3="Ice Hockey (W)")) == 180


def test_duration_tennis():
    assert get_duration_minutes(make_event(category3="Tennis (W)")) == 180


def test_duration_volleyball():
    assert get_duration_minutes(make_event(category3="Volleyball (W)")) == 150


def test_duration_default():
    assert get_duration_minutes(make_event(category3="Cross Country")) == 180


def test_duration_default_override():
    assert get_duration_minutes(
        make_event(category3="Cross Country"), durations={"default": 4}
    ) == 240


def test_duration_override_per_sport():
    assert get_duration_minutes(
        make_event(category3="Soccer (W)"), durations={"soccer": 2}
    ) == 120


def test_build_durations_from_settings_defaults():
    durations = build_durations_from_settings({})
    assert durations["soccer"] == 2.5
    assert durations["baseball"] == 3.5
    assert durations["default"] == 3
    assert durations["gymnastics_dual"] == 2
    assert durations["gymnastics_multi"] == 3.5


def test_build_durations_from_settings_overrides():
    durations = build_durations_from_settings({"soccer_duration_hours": 2, "bad": "x"})
    assert durations["soccer"] == 2
    assert durations["baseball"] == 3.5


def test_duration_gymnastics_dual():
    ev = make_event(category3="Gymnastics (W)", home="Michigan", away="Iowa")
    assert get_duration_minutes(ev) == 120


def test_duration_gymnastics_tri():
    ev = make_event(category3="Gymnastics (W)", home="Michigan", away="Iowa")
    ev["metadata"] = [
        {"field": {"name": "extra competitors"}, "name": "Michigan State"},
        {"field": {"name": "extra competitors"}, "name": "Rutgers"},
    ]
    assert count_event_teams(ev) == 4
    assert get_duration_minutes(ev) == 210


def test_duration_gymnastics_dual_with_extra_schools():
    ev = make_event(category3="Gymnastics (W)", home="Michigan", away="Iowa")
    ev["metadata"] = [{"field": {"name": "extra competitors"}, "name": "Rutgers"}]
    assert count_event_teams(ev) == 3
    assert get_duration_minutes(ev) == 210


def test_day_bounds_are_utc():
    start, end = get_day_bounds("2026-08-16")
    assert start.tzinfo is not None and start.utcoffset().total_seconds() == 0
    assert (end - start) == timedelta(days=1)
    assert start.date().isoformat() == "2026-08-16" or "2026-08-15" == start.date().isoformat()


def test_discover_schedule_module(monkeypatch):
    pages = {"data": [{"id": 7285, "slug": "schedule"}]}
    modules = {
        "data": [
            {"id": 77, "type": {"name": "Something Else"}},
            {"id": 138951, "type": {"name": "Event Based Schedule"}},
        ]
    }
    responses = iter([pages, modules])

    def fake_get(url, timeout=30.0):
        return next(responses)

    monkeypatch.setattr("bigtenplus_plugin.bigtenplus._get", fake_get)
    assert discover_schedule_module(cache=False) == 138951


def test_discover_schedule_module_missing(monkeypatch):
    monkeypatch.setattr(
        "bigtenplus_plugin.bigtenplus._get",
        lambda url, timeout=30.0: {"data": []},
    )
    assert discover_schedule_module(cache=False) is None


def test_fetch_bigtenplus_schedule_uses_fixture(monkeypatch):
    fixture = load_fixture()

    def fake_get(url, timeout=30.0):
        return fixture

    monkeypatch.setattr("bigtenplus_plugin.bigtenplus._get", fake_get)
    events = fetch_bigtenplus_schedule("2026-08-16", module_id=138951)
    assert len(events) == 7
    assert all(e["end_timestamp"] > e["start_timestamp"] for e in events)


def test_fetch_bigtenplus_schedule_paginates(monkeypatch):
    fixture = load_fixture()
    meta = dict(fixture["meta"], current_page=1, last_page=2)
    page1 = dict(fixture, meta=meta, data=fixture["data"][:3])
    page2 = dict(fixture, meta=dict(fixture["meta"], current_page=2, last_page=2), data=fixture["data"][3:])
    responses = iter([page1, page2])

    def fake_get(url, timeout=30.0):
        return next(responses)

    monkeypatch.setattr("bigtenplus_plugin.bigtenplus._get", fake_get)
    events = fetch_bigtenplus_schedule("2026-08-16", module_id=1)
    assert len(events) == 7


def test_fetch_bigtenplus_schedule_returns_empty_on_error(monkeypatch):
    monkeypatch.setattr(
        "bigtenplus_plugin.bigtenplus._get",
        lambda url, timeout=30.0: None,
    )
    assert fetch_bigtenplus_schedule("2026-08-16", module_id=138951) == []


def test_parse_event_requires_start_time():
    ev = make_event()
    ev["startTime"] = None
    assert _parse_event(ev) is None
    ev2 = make_event()
    ev2["startTime"] = "not-a-date"
    assert _parse_event(ev2) is None


def test_parse_event_computes_end_from_duration():
    ev = make_event(category3="Soccer (W)")
    parsed = _parse_event(ev)
    start = datetime.fromisoformat(parsed["start_time"])
    end = datetime.fromisoformat(parsed["end_time"])
    assert (end - start) == timedelta(minutes=150)