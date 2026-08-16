from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bigtenplus_plugin.engine import (
    get_b1g_days,
    merged_settings,
    refresh_channels_dvr,
    run_once,
    validate_settings,
)
from bigtenplus_plugin.state import State


def test_get_b1g_days_today():
    days = get_b1g_days({"b1g_date": "today", "look_ahead_days": 0})
    assert days == [datetime.now(ZoneInfo("US/Eastern")).strftime("%Y-%m-%d")]


def test_get_b1g_days_look_ahead_distinct():
    days = get_b1g_days({"b1g_date": "today", "look_ahead_days": 2})
    assert len(days) == 3
    assert len(set(days)) == 3


def test_get_b1g_days_look_ahead_values():
    now_et = datetime.now(ZoneInfo("US/Eastern"))
    expected = [
        now_et.strftime("%Y-%m-%d"),
        (now_et + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]
    assert get_b1g_days({"b1g_date": "today", "look_ahead_days": 1}) == expected


def test_get_b1g_days_explicit_date():
    assert get_b1g_days({"b1g_date": "2026-08-01"}) == ["2026-08-01"]


def test_merged_settings_defaults():
    merged = merged_settings({})
    assert merged["channel_number_start"] == 900
    assert merged["min_similarity"] == 0.85
    assert merged["look_ahead_days"] == 1
    assert merged["auto_refresh"] is True
    assert merged["channels_dvr_enabled"] is False
    assert merged["channels_dvr_base_url"] == ""
    assert merged["channels_dvr_m3u_source"] == ""
    assert merged["channels_dvr_epg_lineup"] == ""
    assert merged["keyword"] == "BIG10+"
    assert merged["default_duration_hours"] == 3
    assert merged["soccer_duration_hours"] == 2.5
    assert merged["baseball_duration_hours"] == 3.5
    assert merged["gymnastics_dual_duration_hours"] == 2
    assert merged["gymnastics_multi_duration_hours"] == 3.5


def test_merged_settings_overrides():
    merged = merged_settings({"look_ahead_days": 3, "auto_refresh": False})
    assert merged["look_ahead_days"] == 3
    assert merged["auto_refresh"] is False
    assert merged["keyword"] == "BIG10+"


def test_validate_settings_without_django():
    result = validate_settings({})
    assert result["status"] == "error"
    assert any("Dispatcharr" in e for e in result["errors"])


def test_validate_settings_channels_dvr_requires_config():
    result = validate_settings({"channels_dvr_enabled": True})
    assert any("channels_dvr_base_url" in e for e in result["errors"])
    assert any("channels_dvr_m3u_source" in e for e in result["errors"])

    result = validate_settings(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr:8089",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert not any("channels_dvr" in e.lower() for e in result["errors"])


def b1g_streams_for_day(day_iso: str) -> list[dict]:
    d = datetime.strptime(day_iso, "%Y-%m-%d")
    dow = d.strftime("%a")
    name = (
        f"BIG10+ 01: Soccer (W) Georgia at Minnesota {dow} @ "
        f"{d.strftime('%b')} {d.day} 01:00PM ET"
    )
    return [
        {
            "id": 1,
            "name": name,
            "url": "http://example.com/stream",
            "tvg_id": None,
            "logo_url": None,
            "channel_group": None,
        }
    ]


def b1g_event_for_day(day_iso: str) -> dict:
    start = datetime.fromisoformat(f"{day_iso}T17:00:00+00:00")
    end = start + timedelta(minutes=150)
    return {
        "title": "Soccer (W) Georgia at Minnesota",
        "short_name": "Soccer (W) Georgia at Minnesota",
        "subtitle": "",
        "description": "",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "start_timestamp": int(start.timestamp()),
        "end_timestamp": int(end.timestamp()),
        "sport": "Soccer (W)",
        "league": "Soccer (W)",
        "category": "Soccer (W)",
        "subcategory": "",
        "is_studio": False,
        "image_url": "",
        "id": "1",
    }


def patch_state(monkeypatch, tmp_path):
    state = State(base_dir=str(tmp_path / "state"))
    monkeypatch.setattr("bigtenplus_plugin.engine.State", lambda: state)
    return state


def patch_schedule_fetch(monkeypatch, schedule_func):
    monkeypatch.setattr("bigtenplus_plugin.engine.fetch_bigtenplus_schedule", schedule_func)


def patch_sync(monkeypatch, streams):
    monkeypatch.setattr("bigtenplus_plugin.sync.list_streams", lambda: streams)
    monkeypatch.setattr(
        "bigtenplus_plugin.sync.sync_to_dispatcharr",
        lambda matches, settings, **kwargs: {"associated": len(matches)},
    )


def test_run_once_skips_when_nothing_changed(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])

    first = run_once({})
    assert first["status"] == "ok"
    assert first["matches"] == 1

    second = run_once({})
    assert second["status"] == "skipped"


def test_run_once_skips_but_refreshes_channels_dvr(monkeypatch, tmp_path):
    from bigtenplus_plugin import engine

    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])
    monkeypatch.setattr(
        engine,
        "refresh_channels_dvr",
        lambda settings: {"status": "ok", "message": "refreshed"},
    )

    dvr_settings = {
        "channels_dvr_enabled": True,
        "channels_dvr_base_url": "http://dvr",
        "channels_dvr_m3u_source": "Platinum and EPG",
    }

    first = run_once(dvr_settings)
    assert first["status"] == "ok"
    assert first["channels_dvr"] == {"status": "ok", "message": "refreshed"}

    second = run_once(dvr_settings)
    assert second["status"] == "skipped"
    assert second["channels_dvr"] == {"status": "ok", "message": "refreshed"}


def test_run_once_runs_when_matches_change(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    calls = {"n": 0}

    def schedule(day_iso, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return [b1g_event_for_day(day_iso)]
        ev = b1g_event_for_day(day_iso)
        start = datetime.fromisoformat(ev["start_time"]) + timedelta(hours=1)
        return [dict(ev, start_time=start.isoformat(), start_timestamp=int(start.timestamp()))]

    patch_schedule_fetch(monkeypatch, schedule)

    assert run_once({})["status"] == "ok"
    second = run_once({})
    assert second["status"] == "ok"
    assert second["matches"] == 1


def test_run_once_force_runs_even_when_unchanged(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])

    assert run_once({})["status"] == "ok"
    assert run_once({})["status"] == "skipped"
    assert run_once({}, force=True)["status"] == "ok"


def test_run_once_dry_run_does_not_record_hash(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    state = patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])

    assert run_once({}, dry_run=True)["status"] == "ok"
    assert run_once({}, dry_run=True)["status"] == "ok"
    assert state.load_hash() is None


def test_run_once_dry_run_matches(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])

    result = run_once({}, dry_run=True)
    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["matches"] == 1


def test_run_once_no_matches(monkeypatch, tmp_path):
    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [])

    result = run_once({})
    assert result["status"] == "ok"
    assert result["matches"] == 0
    assert result["message"] == "No matches found"
    assert "days" in result


def test_refresh_channels_dvr_skips_when_disabled(monkeypatch):
    monkeypatch.setattr("bigtenplus_plugin.engine.refresh_m3u_source", lambda *a, **k: True)
    monkeypatch.setattr("bigtenplus_plugin.engine.refresh_epg_lineup", lambda *a, **k: True)
    result = refresh_channels_dvr({"channels_dvr_enabled": False})
    assert result["status"] == "skipped"


def test_refresh_channels_dvr_skips_without_source(monkeypatch):
    monkeypatch.setattr("bigtenplus_plugin.engine.refresh_m3u_source", lambda *a, **k: True)
    monkeypatch.setattr("bigtenplus_plugin.engine.refresh_epg_lineup", lambda *a, **k: True)
    result = refresh_channels_dvr(
        {"channels_dvr_enabled": True, "channels_dvr_base_url": "http://dvr"}
    )
    assert result["status"] == "skipped"


def test_refresh_channels_dvr_refreshes_m3u_and_derived_epg(monkeypatch):
    from bigtenplus_plugin import engine

    calls = []
    monkeypatch.setattr(engine.time, "sleep", lambda s: calls.append(s))
    monkeypatch.setattr(engine, "list_sources", lambda base_url: {"m3u_sources": []})
    monkeypatch.setattr(
        engine,
        "refresh_m3u_source",
        lambda base_url, source, device_id=None: calls.append(("m3u", source, device_id)) or True,
    )
    monkeypatch.setattr(
        engine,
        "refresh_epg_lineup",
        lambda base_url, lineup: calls.append(("epg", lineup)) or True,
    )

    result = refresh_channels_dvr(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert result["status"] == "ok"
    assert ("m3u", "Platinum and EPG", None) in calls
    assert ("epg", "XMLTV-Platinum and EPG") in calls
    assert 5 in calls


def test_refresh_channels_dvr_derives_lineup_from_source(monkeypatch):
    from bigtenplus_plugin import engine

    calls = []
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        engine,
        "list_sources",
        lambda base_url: {
            "m3u_sources": [
                {"name": "Platinum and EPG", "device_id": "M3U-PlatinumandEPG"}
            ],
            "device_to_lineup": {"M3U-PlatinumandEPG": "XMLTV-PlatinumandEPG"},
        },
    )
    monkeypatch.setattr(engine, "refresh_m3u_source", lambda *a, **k: True)
    monkeypatch.setattr(
        engine, "refresh_epg_lineup", lambda base_url, lineup: calls.append(lineup) or True
    )

    refresh_channels_dvr(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert calls == ["XMLTV-Platinum and EPG"]


def test_refresh_channels_dvr_uses_explicit_lineup(monkeypatch):
    from bigtenplus_plugin import engine

    calls = []
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)
    monkeypatch.setattr(engine, "list_sources", lambda base_url: {"m3u_sources": []})
    monkeypatch.setattr(engine, "refresh_m3u_source", lambda *a, **k: True)
    monkeypatch.setattr(
        engine, "refresh_epg_lineup", lambda base_url, lineup: calls.append(lineup) or True
    )

    refresh_channels_dvr(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
            "channels_dvr_epg_lineup": "XMLTV-MyCustom",
        }
    )
    assert calls == ["XMLTV-MyCustom"]


def test_refresh_channels_dvr_reports_partial_failure(monkeypatch):
    from bigtenplus_plugin import engine

    monkeypatch.setattr(engine.time, "sleep", lambda s: None)
    monkeypatch.setattr(engine, "list_sources", lambda base_url: {"m3u_sources": []})
    monkeypatch.setattr(engine, "refresh_m3u_source", lambda *a, **k: True)
    monkeypatch.setattr(engine, "refresh_epg_lineup", lambda *a, **k: False)

    result = refresh_channels_dvr(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert result["status"] == "error"
    assert "EPG" in result["message"]


def test_run_once_refreshes_channels_dvr_when_enabled(monkeypatch, tmp_path):
    from bigtenplus_plugin import engine

    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])
    monkeypatch.setattr(
        engine,
        "refresh_channels_dvr",
        lambda settings: {"status": "ok", "message": "refreshed"},
    )

    result = run_once(
        {
            "channels_dvr_enabled": True,
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert result["status"] == "ok"
    assert result["channels_dvr"] == {"status": "ok", "message": "refreshed"}


def test_run_once_skips_channels_dvr_when_disabled(monkeypatch, tmp_path):
    from bigtenplus_plugin import engine

    days = get_b1g_days({})
    streams = b1g_streams_for_day(days[0])
    patch_state(monkeypatch, tmp_path)
    patch_sync(monkeypatch, streams)
    patch_schedule_fetch(monkeypatch, lambda day_iso, **kwargs: [b1g_event_for_day(day_iso)])
    monkeypatch.setattr(engine, "refresh_channels_dvr", lambda settings: {"status": "ok"})

    result = run_once({})
    assert result["status"] == "ok"
    assert "channels_dvr" not in result


def test_test_channels_dvr_refresh(monkeypatch):
    from bigtenplus_plugin import engine

    captured = {}

    def fake_refresh_and_report(base_url, source_name, lineup_name=None):
        captured["args"] = (base_url, source_name, lineup_name)
        return {"status": "ok", "details": ["POST -> 200", "PUT -> 200"]}

    monkeypatch.setattr("bigtenplus_plugin.channels_dvr.refresh_and_report", fake_refresh_and_report)

    result = engine.test_channels_dvr_refresh(
        {
            "channels_dvr_base_url": "http://dvr",
            "channels_dvr_m3u_source": "Platinum and EPG",
        }
    )
    assert result["status"] == "ok"
    assert captured["args"] == ("http://dvr", "Platinum and EPG", "XMLTV-Platinum and EPG")


def test_test_channels_dvr_refresh_missing_source():
    from bigtenplus_plugin import engine

    result = engine.test_channels_dvr_refresh({"channels_dvr_base_url": "http://dvr"})
    assert result["status"] == "error"
    assert "M3U Source" in result["message"]