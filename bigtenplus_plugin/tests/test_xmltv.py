from datetime import datetime, timezone
from lxml import etree

from bigtenplus_plugin.xmltv_gen import (
    generate_xmltv,
    get_channel_id,
    _build_channel_id,
    _build_categories,
    _build_keywords,
    _format_xmltv_time,
)
from bigtenplus_plugin.playlist import PlaylistEntry


def make_entry(name: str) -> PlaylistEntry:
    return PlaylistEntry(
        name=name,
        stream_url="http://example.com/stream",
        tvg_name=name,
        group="USA|B1G+",
    )


def make_metadata(title: str, start: str, end: str) -> dict:
    return {
        "title": title,
        "short_name": title,
        "subtitle": "Georgia at Minnesota",
        "description": "",
        "start_time": start,
        "end_time": end,
        "sport": "Soccer (W)",
        "sport_abbrev": "",
        "sport_base": "Soccer",
        "league": "Soccer (W)",
        "league_abbrev": "",
        "category": "Soccer (W)",
        "subcategory": "",
        "gender": "Women",
        "genre": "NCAA Women's Soccer",
        "conference": "Big Ten",
        "network": "B1G+",
        "home_team": "Minnesota",
        "away_team": "Georgia",
        "duration_minutes": 150,
        "date": 2024,
        "is_studio": False,
        "image_url": "http://example.com/icon.png",
    }


def make_match(start="2024-01-15T20:00:00+00:00", end="2024-01-15T22:30:00+00:00"):
    entry = make_entry("Soccer (W) Georgia at Minnesota")
    metadata = make_metadata("Soccer (W) Georgia at Minnesota", start, end)
    return entry, metadata


def _root(matches=None):
    matches = matches if matches is not None else [make_match()]
    xml = generate_xmltv(matches)
    return etree.fromstring(xml.encode("utf-8"))


def test_three_programmes_per_channel():
    root = _root()
    assert len(root.findall("programme")) == 3


def test_upcoming_title_prefix():
    progs = _root().findall("programme")
    titles = [p.find("title").text for p in progs]
    assert titles[0] == "UPCOMING: B1G+: Soccer (W) Georgia at Minnesota"
    assert titles[1] == "B1G+: Soccer (W) Georgia at Minnesota"
    assert titles[2] == "ENDED: B1G+: Soccer (W) Georgia at Minnesota"


def test_title_prefix_on_all_programmes():
    progs = _root().findall("programme")
    assert progs[1].find("title").text.startswith("B1G+:")
    for prog in progs:
        assert "B1G+:" in prog.find("title").text


def test_categories_on_all_three_programmes():
    expected = ["Sports", "NCAA", "NCAA Women", "NCAA Women's Soccer", "Soccer (W)", "Big Ten"]
    for prog in _root().findall("programme"):
        cats = [c.text for c in prog.findall("category")]
        assert cats == expected


def test_categories_men():
    entry = make_entry("Soccer (M) Michigan at Iowa")
    metadata = make_metadata("Soccer (M) Michigan at Iowa", "2024-01-15T20:00:00+00:00", "2024-01-15T22:30:00+00:00")
    metadata["gender"] = "Men"
    metadata["genre"] = "NCAA Men's Soccer"
    metadata["home_team"] = "Iowa"
    metadata["away_team"] = "Michigan"
    root = _root([(entry, metadata)])
    cats = [c.text for c in root.findall("programme")[1].findall("category")]
    assert "NCAA Men" in cats
    assert "NCAA Men's Soccer" in cats


def test_categories_no_gender():
    entry = make_entry("Football Michigan at Ohio State")
    metadata = make_metadata("Football Michigan at Ohio State", "2024-01-15T20:00:00+00:00", "2024-01-15T23:30:00+00:00")
    metadata["gender"] = ""
    metadata["genre"] = "NCAA Football"
    metadata["sport_base"] = "Football"
    metadata["league"] = "Football"
    metadata["home_team"] = "Ohio State"
    metadata["away_team"] = "Michigan"
    root = _root([(entry, metadata)])
    cats = [c.text for c in root.findall("programme")[1].findall("category")]
    assert "NCAA" in cats
    assert "NCAA Football" in cats
    assert "NCAA Men" not in cats


def test_keywords_on_all_three_programmes():
    expected = [
        "NCAA",
        "NCAA Women",
        "NCAA Women's Soccer",
        "Soccer",
        "Soccer (W)",
        "Big Ten",
        "Georgia",
        "Minnesota",
    ]
    for prog in _root().findall("programme"):
        keywords = [k.text for k in prog.findall("keyword")]
        assert keywords == expected


def test_date_on_all_three_programmes():
    for prog in _root().findall("programme"):
        assert prog.find("date") is not None
        assert prog.find("date").text == "2024"


def test_length_on_all_three_programmes():
    for prog in _root().findall("programme"):
        length = prog.find("length")
        assert length is not None
        assert length.get("units") == "minutes"
        assert length.text == "150"


def test_subtitle_on_all_three_programmes():
    for prog in _root().findall("programme"):
        assert prog.find("sub-title") is not None
        assert prog.find("sub-title").text == "Georgia at Minnesota"


def test_no_subtitle_when_metadata_missing():
    entry, metadata = make_match()
    del metadata["subtitle"]
    root = _root([(entry, metadata)])
    for prog in root.findall("programme"):
        assert prog.find("sub-title") is None


def test_desc_on_all_three_programmes():
    for prog in _root().findall("programme"):
        assert prog.find("desc") is not None


def test_desc_content():
    prog = _root().findall("programme")[1]
    desc = prog.find("desc").text
    assert "NCAA Women's Soccer" in desc
    assert "Georgia at Minnesota" in desc
    assert "Big Ten" in desc


def test_upcoming_ends_at_real_start():
    progs = _root().findall("programme")
    assert progs[0].get("stop") == progs[1].get("start")


def test_ended_starts_at_real_end():
    progs = _root().findall("programme")
    assert progs[1].get("stop") == progs[2].get("start")


def test_real_programme_no_prefix():
    progs = _root().findall("programme")
    title = progs[1].find("title").text
    assert not title.startswith("UPCOMING:")
    assert not title.startswith("ENDED:")


def test_no_programmes_when_real_times_missing():
    entry, metadata = make_match()
    del metadata["start_time"]
    del metadata["end_time"]
    root = _root([(entry, metadata)])
    assert len(root.findall("programme")) == 0


def test_only_live_on_middle_programme():
    progs = _root().findall("programme")
    assert progs[0].find("live") is None
    assert progs[1].find("live") is not None
    assert progs[2].find("live") is None


def test_no_new_tag_anywhere():
    assert len(_root().findall(".//new")) == 0


def test_no_premiere_tag():
    assert len(_root().findall(".//premiere")) == 0


def test_no_live_when_studio():
    entry, metadata = make_match()
    metadata["is_studio"] = True
    root = _root([(entry, metadata)])
    progs = root.findall("programme")
    assert progs[1].find("live") is None
    assert progs[1].find("new") is None


def test_icons_on_all_three_programmes():
    prog_icons = _root().findall(".//programme/icon")
    assert len(prog_icons) == 3


def test_no_icons_when_image_url_missing():
    entry, metadata = make_match()
    del metadata["image_url"]
    root = _root([(entry, metadata)])
    assert len(root.findall(".//programme/icon")) == 0


def test_channel_icon_when_tvg_logo_present():
    entry = PlaylistEntry(
        name="Soccer (W) Georgia at Minnesota",
        stream_url="http://example.com/stream",
        tvg_logo="http://example.com/logo.png",
        tvg_name="Soccer (W) Georgia at Minnesota",
        group="USA|B1G+",
    )
    metadata = make_metadata("Soccer (W) Georgia at Minnesota", "2024-01-15T20:00:00+00:00", "2024-01-15T22:30:00+00:00")
    root = _root([(entry, metadata)])
    ch_icons = root.findall(".//channel/icon")
    assert len(ch_icons) == 1
    assert ch_icons[0].get("src") == "http://example.com/logo.png"


def test_channel_no_icon_when_tvg_logo_missing():
    root = _root()
    assert len(root.findall(".//channel/icon")) == 0


def test_channel_id_format():
    entry = make_entry("Soccer (W) Georgia @ Minnesota")
    cid = get_channel_id(entry)
    assert cid.startswith("B1G+")
    assert "Soccer" in cid or "Georgia" in cid


def test_build_channel_id():
    entry = PlaylistEntry(name="Test Channel!", stream_url="http://example.com")
    cid = _build_channel_id(entry, prefix="B1G+")
    assert "Test_Channel_" in cid


def test_format_xmltv_time():
    formatted = _format_xmltv_time("2024-01-15T20:00:00+00:00")
    assert "20240115" in formatted
    assert "-0" in formatted or "+0" in formatted


def test_empty_matches():
    xml = generate_xmltv([])
    assert "<tv" in xml
    assert "<channel" not in xml


def test_multiple_channels_each_have_three():
    e1, m1 = make_match("2024-01-15T18:00:00+00:00", "2024-01-15T20:30:00+00:00")
    e2 = make_entry("Soccer (W) Purdue Fort Wayne at Purdue")
    m2 = make_metadata("Soccer (W) Purdue Fort Wayne at Purdue", "2024-01-15T22:30:00+00:00", "2024-01-16T01:00:00+00:00")
    root = _root([(e1, m1), (e2, m2)])
    assert len(root.findall("channel")) == 2
    assert len(root.findall("programme")) == 6


def test_pt_offset_in_all_programmes():
    for prog in _root().findall("programme"):
        s = prog.get("start")
        e = prog.get("stop")
        assert "-0" in s or "+0" in s
        assert "-0" in e or "+0" in e


def test_programmes_use_stop_attribute_not_end():
    progs = _root().findall("programme")
    assert len(progs) == 3
    for prog in progs:
        assert prog.get("start") is not None
        assert prog.get("stop") is not None
        assert prog.get("end") is None


def test_icon_src_is_not_double_escaped():
    entry, metadata = make_match()
    url = "https://artwork.api.bigtenplus.com/x/default?width=640&apikey=KEY&timestamp=1"
    metadata["image_url"] = url
    xml = generate_xmltv([(entry, metadata)])
    assert "&amp;apikey" in xml, "raw XML must have single-escaped &amp;"
    assert "&amp;amp;" not in xml, "raw XML must NOT have double-escaped &amp;amp;"
    root = etree.fromstring(xml.encode("utf-8"))
    for icon in root.findall(".//programme/icon"):
        assert icon.get("src") == url, f"expected '{url}', got '{icon.get('src')}'"


def test_title_special_chars_round_trip():
    entry, metadata = make_match()
    metadata["title"] = "A & B <C>"
    metadata["short_name"] = "A & B <C>"
    metadata["image_url"] = ""
    root = _root([(entry, metadata)])
    for prog in root.findall("programme"):
        t = prog.find("title").text
        assert "&amp;" not in t, f"parsed title text must not contain &amp;: {t!r}"
        assert "&" in t, f"parsed title must contain raw &: {t!r}"


def test_build_categories_order():
    categories = _build_categories(make_metadata("X", "2024-01-15T20:00:00+00:00", "2024-01-15T22:30:00+00:00"))
    assert categories == ["Sports", "NCAA", "NCAA Women", "NCAA Women's Soccer", "Soccer (W)", "Big Ten"]


def test_build_keywords_deduplicates():
    metadata = make_metadata("X", "2024-01-15T20:00:00+00:00", "2024-01-15T22:30:00+00:00")
    keywords = _build_keywords(metadata)
    assert len(keywords) == len(set(keywords))
    assert keywords[0] == "NCAA"