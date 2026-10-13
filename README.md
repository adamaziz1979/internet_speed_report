# Internet Speed Report

Placeholder. The HTML report has not been built yet.

## What this repo is for

Publishing a readable report of home network speed test history for
**Adam Aziz**, collected on the local machine by a scheduled Windows task.

## Data source

| | |
|---|---|
| Collector | `my-workflows (automations)/live/speed-test/run.py` |
| Master log | `speed-history.csv` (append-only, never rotated) |
| Cadence | 4x daily when active: 9am, 12pm, 3pm, 7pm |
| Method | Each row is the average of 3 back-to-back tests |

## Current status

Collection is **paused**. The scheduled task was disabled on 25 August 2026
and no data has been recorded since.

Three known issues remain open on the collector:

1. The `speedtest-cli` library in use is legacy and unmaintained. Its server
   list has been shrinking and latency probes return unreachable sentinels.
2. One stored row carries an invalid ping of 1,800,000 ms (an unreachable
   sentinel averaged into a real reading).
3. Auto-selected servers have drifted to Perth and Brisbane, hundreds to
   thousands of kilometres away, which makes throughput figures
   non-comparable against the earlier Sydney baseline.

These should be resolved before the published report is treated as a fair
picture of the connection.
