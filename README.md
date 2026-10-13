# Internet Speed Report

Live page: **https://adamaziz1979.github.io/internet_speed_report/**

Home network speed test history for Adam Aziz, measured on the local machine and
published here.

## Why the tests do not run in Actions

A GitHub Actions runner is a VM in a datacentre. Running `speedtest` there measures
Azure's network to a speedtest server, which has nothing to do with the home line in
Sydney. The numbers would be fast, stable and meaningless.

So the work is split:

| Stage | Where | What |
|---|---|---|
| Measure | Local Windows machine | Scheduled task runs `run.py`, appends to `speed-history.csv` |
| Transport | Local machine | Pushes `speed-history.csv` to this repo |
| Render | GitHub Actions | `build_report.py` turns the CSV into `index.html` |
| Serve | GitHub Pages | Publishes `index.html` |

## Files

| File | Purpose |
|---|---|
| `speed-history.csv` | The master log. Append-only, never rotated. Pushed from the local machine. |
| `build_report.py` | Renders the CSV into `index.html`. Standard library only, no dependencies. |
| `.github/workflows/publish.yml` | Builds and deploys on push of the CSV, daily at 22:00 UTC, or on demand. |

## CSV columns

```
timestamp_local, timestamp_utc, download_mbps, upload_mbps, ping_ms,
duration_s, server_id, server_name, server_country, isp, samples
```

Each row is the average of 3 back-to-back tests from one scheduled run.
`duration_s` is how long those 3 tests took, normally about 65 seconds.
`server_id` records which server was actually used, so server drift stays visible
in the data rather than silent.

## Server selection

Tests only ever run against a **Sydney metro server**, within 60 km of the connection.
If the list has none, the run is skipped and nothing is recorded: a gap is better than a
Brisbane reading filed as though it were a Sydney one.

Servers are filtered on distance, not city name, because Chatswood and Fairlight are
Sydney metro but are not labelled "Sydney". No server ID is hardcoded; eligible servers
are sorted deterministically so the same one is reused run after run while it exists, and
the next takes over when it leaves the list.

Readings before 14 October 2026 predate this rule and may show Melbourne, Perth or
Moorooka. Their throughput is not comparable with the Sydney readings.

## Collection schedule

4x daily when active: 9am, 12pm, 3pm, 7pm (Sydney time). A reading counts toward a
slot average only if it landed within 15 minutes of the slot; late catch-up runs are
reported as off-slot so they cannot quietly distort the averages.

## What the report guards against

`build_report.py` does not simply average whatever is in the CSV:

- **Implausible pings are excluded.** Speedtest returns a 3,600,000 ms sentinel when
  a host is unreachable, and that gets averaged into a real reading. Anything over
  1,000 ms is dropped from every ping figure and flagged on the page.
- **Degraded runs are flagged** where fewer than 3 samples completed.
- **Server drift is called out** when readings span multiple test servers, because
  throughput against a server hundreds of kilometres away is not comparable with a
  nearby one.
- **Stale data is called out** when the newest reading is more than a day old, rather
  than presenting old numbers as current.

## Known issues with the collector

These sit on the local side, not here:

1. The `speedtest-cli` library in use is legacy and unmaintained. Its server list has
   been shrinking and latency probes return unreachable sentinels. Moving to Ookla's
   official CLI is the durable fix.
2. ~~Hardcoded server IDs rot.~~ Fixed 14 Oct 2026. A pin to server `30430` took
   collection to zero for four days in August 2026 once that server left the list.
   No ID is hardcoded now; servers are chosen by distance each run.
3. ~~Auto-selected servers drifted as far as Perth and Brisbane.~~ Fixed 14 Oct 2026 by
   the 60 km Sydney constraint. The report still warns about comparability because the
   historical rows taken against distant servers remain in the data.
