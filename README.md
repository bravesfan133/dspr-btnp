# Dispatcharr B1G+ (Big Ten Plus) EPG Generator

Automatically discovers Big Ten Plus event streams from a Dispatcharr source playlist, matches them to the Big Ten Plus schedule, creates a high-quality XMLTV guide, and assigns channels to the **EPG** profile within Dispatcharr.

This is a companion plugin to the ESPN+ EPG generator, adapted for the Big Ten Plus streaming service.

## Architecture

```
M3U Playlist → Parse → Filter BIG10+ → Match to B1G+ Schedule → Generate XMLTV → Upload to Dispatcharr → Assign EPG Profile
```

Runs continuously, monitoring the playlist for changes, and only rebuilds when the playlist changes.

## Schedule Source

The plugin pulls schedules from the Big Ten Plus site API (`https://www.bigtenplus.com/api/v3/...`), discovering the schedule module id at runtime:

1. `GET /api/v3/pages` — find the page with slug `schedule`
2. `GET /api/v3/pages/{id}/modules` — find the module of type `Event Based Schedule`
3. `GET /api/v3/modules/{id}/contents?filter[date]=YYYY-MM-DD&filter[deviceCategory]=1&filter[dateTimeFrom]=...&filter[dateTimeTo]=...` — the day's events

Big Ten Plus does not publish end times, so event durations are estimated per sport:

| Sport | Duration |
|-------|----------|
| Baseball | 3.5 h |
| Basketball | 3 h |
| Football | 3.5 h |
| Golf | 6 h |
| Hockey | 3 h |
| Soccer | 2.5 h |
| Tennis | 3 h |
| Volleyball | 2.5 h |
| Gymnastics — dual meet (2 teams) | 2 h |
| Gymnastics — tri/quad meet (3-4 teams) | 3.5 h |
| Default | 3 h |

The `event_duration_minutes` setting overrides the fallback for unmatched sports.

## Playlist Stream Naming

Streams in your playlist are expected to follow this convention (the plugin's `keyword` setting defaults to `BIG10+`):

```
BIG10+ 01: Soccer (W) Fordham at Maryland Sun @ Aug 16 12:00PM ET
BIG10+ 02: Soccer (W) Georgia at Minnesota Sun @ Aug 16 01:00PM ET
BIG10+ 06: Volleyball (W) Red vs. White Scrimmage Sun @ Aug 16 04:00PM ET
BIG10+ 09: NO EVENT
```

- `BIG10+ NN:` — the stream index used to derive channel numbers
- `Sport (league) Away at Home` — the event title
- `Sun @ Aug 16 12:00PM ET` — day, date, and start time (ET/CT supported)
- Streams containing `NO EVENT` are skipped automatically

## Dispatcharr Plugin Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `epg_source_name` | `B1G+ EPG` | Name of the EPG source created in Dispatcharr |
| `channel_id_prefix` | `B1G+` | Prefix used to build XMLTV channel IDs |
| `channel_number_start` | `900` | First channel number assigned |
| `epg_group_name` | `B1G+` | Dispatcharr channel group created for these channels |
| `epg_profile_name` | `EPG` | Dispatcharr channel profile these channels are added to |
| `keyword` | `BIG10+` | Keyword used to find Big Ten Plus streams in the playlist |
| `look_ahead_days` | `1` | Extra days of Big Ten Plus schedule to fetch beyond today |
| `min_similarity` | `0.85` | Similarity threshold for fuzzy-matching playlist titles to events |
| `b1g_date` | `today` | Schedule date to fetch (`today` or `YYYY-MM-DD`) |
| `event_duration_minutes` | `180` | Fallback event duration when the sport is not recognized |
| `log_level` | `INFO` | Verbosity of plugin logging |
| `auto_refresh` | `true` | Run automatically after every M3U refresh event |
| `channels_dvr_enabled` | `false` | Refresh Channels DVR after a successful Dispatcharr sync |
| `channels_dvr_base_url` | — | Channels DVR server address, e.g. `http://192.168.0.168:8089` |
| `channels_dvr_m3u_source` | — | Name of the M3U playlist source on Channels DVR to refresh |
| `channels_dvr_epg_lineup` | — | EPG lineup to refresh; blank auto-derives `XMLTV-<source>` |

## Matching Algorithm

1. Filter playlist channels by the `BIG10+` keyword
2. Skip streams containing `NO EVENT`
3. Extract start time from the stream name (`Mon DD h:mmAM/PM ET/CT`)
4. Fetch the Big Ten Plus schedule for the matching days
5. Normalize titles (lowercase, remove punctuation, normalize `vs`/`at`/`@`)
6. Use RapidFuzz `token_sort_ratio` for fuzzy matching (min 85% by default)

## Development

```bash
pip install -r requirements.txt
python -m pytest bigtenplus_plugin/tests -q
```

## Project Structure

```
bigtenplus_plugin/
├── bigtenplus.py      # Big Ten Plus API client + event parsing + duration model
├── engine.py          # Orchestrates fetch → match → sync
├── playlist.py        # BIG10+ playlist name/time parsing
├── matcher.py         # Fuzzy matching with RapidFuzz
├── normalize.py       # Title normalization
├── xmltv_gen.py       # XMLTV document generator
├── sync.py            # Dispatcharr channel/EPG sync
├── channels_dvr.py    # Channels DVR REST client
├── state.py           # Run-state caching
├── plugin.json        # Plugin manifest
├── plugin.py          # Dispatcharr plugin entry point
└── tests/             # Unit tests + API fixtures
```