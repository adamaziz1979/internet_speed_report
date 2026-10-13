"""Builds index.html from speed-history.csv.

Run by .github/workflows/publish.yml on every push of the CSV and on a daily
schedule. Pure stdlib, so the Action needs no pip install.

Measurement happens on Adam's machine, never here: a GitHub runner would measure
Azure's network, not the home line. This script only renders what was collected.
"""
import csv
import datetime
import html
import math
import os
import sys

CSV_PATH = os.environ.get("SPEED_CSV", "speed-history.csv")
OUT_PATH = os.environ.get("SPEED_OUT", "index.html")

SLOTS = [(9, "9am"), (12, "12pm"), (15, "3pm"), (19, "7pm")]
SLOT_TOLERANCE_MIN = 15
PING_MAX_PLAUSIBLE = 1000.0   # speedtest returns a 3,600,000 ms sentinel when unreachable
EXPECTED_SAMPLES = 3


def num(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def no_pad(text):
    """'05 Sep' -> '5 Sep'. Avoids %-d / %-I, which Windows strftime rejects."""
    return text[1:] if text.startswith("0") else text


def slot_for(ts):
    """Name the scheduled slot this reading belongs to, or None if it was off-slot."""
    for hour, label in SLOTS:
        target = ts.replace(hour=hour, minute=0, second=0, microsecond=0)
        if abs((ts - target).total_seconds()) <= SLOT_TOLERANCE_MIN * 60:
            return label
    return None


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        try:
            ts = datetime.datetime.fromisoformat((r.get("timestamp_local") or "").strip())
        except ValueError:
            continue

        ping = num(r.get("ping_ms"))
        samples = num(r.get("samples"))
        out.append({
            "ts": ts,
            "download": num(r.get("download_mbps")),
            "upload": num(r.get("upload_mbps")),
            "ping": ping,
            "ping_ok": ping is not None and 0 < ping < PING_MAX_PLAUSIBLE,
            "duration": num(r.get("duration_s")),
            "server": (r.get("server_name") or "").strip() or "unknown",
            "samples": samples,
            "degraded": samples is not None and samples < EXPECTED_SAMPLES,
            "slot": slot_for(ts),
        })
    out.sort(key=lambda d: d["ts"])
    return out


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def fmt(v, dp=2, dash="&mdash;"):
    return dash if v is None else f"{v:,.{dp}f}"


# ---------------------------------------------------------------- chart drawing

W, H = 760, 260
PAD_L, PAD_R, PAD_T, PAD_B = 56, 18, 18, 34


def nice_top(v):
    if not v or v <= 0:
        return 10.0
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 2, 2.5, 5, 10):
        if v <= mag * step:
            return mag * step
    return mag * 10


def line_chart(readings, series, unit, chart_id):
    """series: list of (key, label, css-var). One axis, one unit - never dual-axis."""
    pts = [r for r in readings if any(r[k] is not None for k, _, _ in series)]
    if not pts:
        return '<p class="empty">Not enough data to plot yet.</p>'

    t0, t1 = pts[0]["ts"].timestamp(), pts[-1]["ts"].timestamp()
    span = (t1 - t0) or 1.0
    top = nice_top(max(v for r in pts for v in
                       (r[k] for k, _, _ in series) if v is not None))

    def px(ts):
        return PAD_L + (ts.timestamp() - t0) / span * (W - PAD_L - PAD_R)

    def py(v):
        return H - PAD_B - (v / top) * (H - PAD_T - PAD_B)

    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
           f'aria-labelledby="{chart_id}-t">',
           f'<title id="{chart_id}-t">{html.escape(unit)} over time</title>']

    for i in range(5):
        v = top * i / 4
        y = py(v)
        out.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" class="ylab">{v:,.0f}</text>')

    for r, anchor in ((pts[0], "start"), (pts[-1], "end")):
        label = no_pad(r["ts"].strftime("%d %b"))
        out.append(f'<text x="{px(r["ts"]):.1f}" y="{H - 10}" class="xlab" '
                   f'text-anchor="{anchor}">{label}</text>')

    for key, label, var in series:
        vals = [r for r in pts if r[key] is not None]
        if not vals:
            continue
        d = " ".join(f'{"M" if i == 0 else "L"}{px(r["ts"]):.1f},{py(r[key]):.1f}'
                     for i, r in enumerate(vals))
        out.append(f'<path d="{d}" fill="none" stroke="var({var})" stroke-width="2" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
        for r in vals:
            tip = (f'{no_pad(r["ts"].strftime("%d %b %H:%M"))} - {label}: '
                   f'{fmt(r[key], dash="n/a")} {unit} (server {r["server"]})')
            out.append(f'<circle cx="{px(r["ts"]):.1f}" cy="{py(r[key]):.1f}" r="4.5" '
                       f'fill="var({var})" stroke="var(--surface-1)" stroke-width="2">'
                       f'<title>{html.escape(tip)}</title></circle>')
        last = vals[-1]
        out.append(f'<text x="{px(last["ts"]) - 8:.1f}" y="{py(last[key]) - 11:.1f}" '
                   f'class="dlab" text-anchor="end">{html.escape(label)}</text>')

    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------- styling

CSS = """
*{box-sizing:border-box}
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#f4f3f0;
--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#76756f;
--rule:#e3e2dd;--grid:#e9e8e3;--series-1:#2a78d6;--series-2:#eb6834;
--warn:#eda100;--bad:#e34948}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{
color-scheme:dark;--surface-1:#1a1a19;--surface-2:#242423;
--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#9a998f;
--rule:#333331;--grid:#2c2c2a;--series-1:#3987e5;--series-2:#d95926;
--warn:#c98500;--bad:#e66767}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;
--surface-2:#242423;--text-primary:#fff;--text-secondary:#c3c2b7;
--text-muted:#9a998f;--rule:#333331;--grid:#2c2c2a;--series-1:#3987e5;
--series-2:#d95926;--warn:#c98500;--bad:#e66767}
html,body{margin:0;background:var(--surface-1)}
body{font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
color:var(--text-primary);-webkit-text-size-adjust:100%}
.wrap{max-width:860px;margin:0 auto;padding:40px 16px 64px}
h1{font-size:1.6rem;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:1.05rem;margin:38px 0 10px;letter-spacing:-.005em}
.sub{color:var(--text-secondary);margin:0 0 26px;font-size:.92rem}
.meta{color:var(--text-secondary);margin:0 0 14px;font-size:.88rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.tile{background:var(--surface-2);border:1px solid var(--rule);border-radius:10px;
padding:14px 16px}
.tile .k{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--text-muted)}
.tile .v{font-size:1.85rem;font-weight:600;letter-spacing:-.02em;margin-top:2px}
.tile .u{font-size:.78rem;color:var(--text-secondary);font-weight:400;margin-left:3px}
.chart{width:100%;height:auto;display:block;margin:4px 0 2px}
.grid{stroke:var(--grid);stroke-width:1}
.ylab,.xlab{fill:var(--text-muted);font-size:11px}
.ylab{text-anchor:end}
.dlab{fill:var(--text-secondary);font-size:11.5px;font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:2px 0 0;padding:0;list-style:none;
font-size:.85rem;color:var(--text-secondary)}
.legend li{display:flex;align-items:center;gap:6px}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.88rem;margin-top:4px}
th,td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--rule);
white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--text-muted);font-weight:600}
td.bad{color:var(--bad);font-weight:600}
.note{background:var(--surface-2);border:1px solid var(--rule);
border-left:3px solid var(--warn);border-radius:8px;padding:14px 16px;margin:12px 0}
.note ul{margin:0;padding-left:20px}.note li{margin:6px 0}
.empty{color:var(--text-secondary);font-style:italic}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--rule);
color:var(--text-muted);font-size:.8rem}
footer p{margin:0 0 7px}
code{background:var(--surface-2);padding:1px 5px;border-radius:4px;font-size:.85em}
"""


def build(readings):
    gen = datetime.datetime.now(datetime.timezone.utc)
    body = []

    if not readings:
        body.append('<p class="empty">No readings recorded yet. The collector has not '
                    'written any rows to <code>speed-history.csv</code>.</p>')
        return page(body, readings, gen)

    latest = readings[-1]
    age_h = (datetime.datetime.now() - latest["ts"]).total_seconds() / 3600

    body.append("<h2>Latest reading</h2>")
    stamp = no_pad(latest["ts"].strftime("%d %B %Y, %I:%M %p")).replace("AM", "am").replace("PM", "pm")
    samples = "?" if latest["samples"] is None else int(latest["samples"])
    body.append(f'<p class="meta">{stamp} &middot; server {html.escape(latest["server"])} '
                f'&middot; {samples} of {EXPECTED_SAMPLES} samples</p>')

    body.append('<div class="tiles">')
    for key, label, unit, dp in (("download", "Download", "Mbps", 2),
                                 ("upload", "Upload", "Mbps", 2),
                                 ("duration", "Cycle time", "s", 1)):
        body.append(f'<div class="tile"><div class="k">{label}</div>'
                    f'<div class="v">{fmt(latest[key], dp)}'
                    f'<span class="u">{unit}</span></div></div>')
    if latest["ping_ok"]:
        ping_cell = f'{fmt(latest["ping"], 1)}<span class="u">ms</span>'
    else:
        ping_cell = '<span style="color:var(--bad)">invalid</span>'
    body.append(f'<div class="tile"><div class="k">Ping</div>'
                f'<div class="v">{ping_cell}</div></div>')
    body.append("</div>")

    body.append("<h2>Throughput over time</h2>")
    body.append(line_chart(readings,
                           [("download", "Download", "--series-1"),
                            ("upload", "Upload", "--series-2")],
                           "Mbps", "tput"))
    body.append('<ul class="legend">'
                '<li><span class="sw" style="background:var(--series-1)"></span>Download</li>'
                '<li><span class="sw" style="background:var(--series-2)"></span>Upload</li>'
                '</ul>')

    body.append("<h2>Ping over time</h2>")
    body.append(line_chart([r for r in readings if r["ping_ok"]],
                           [("ping", "Ping", "--series-1")], "ms", "ping"))

    body.append("<h2>Average by scheduled slot</h2>")
    rows = []
    for _, label in SLOTS:
        hit = [r for r in readings if r["slot"] == label]
        hit_ping = [r for r in hit if r["ping_ok"]]
        rows.append(f"<tr><td>{label}</td><td>{len(hit)}</td>"
                    f"<td>{fmt(mean([r['download'] for r in hit]))}</td>"
                    f"<td>{fmt(mean([r['upload'] for r in hit]))}</td>"
                    f"<td>{fmt(mean([r['ping'] for r in hit_ping]), 1)}</td></tr>")
    body.append('<div class="scroll"><table><thead><tr><th>Slot</th><th>Readings</th>'
                "<th>Down (Mbps)</th><th>Up (Mbps)</th><th>Ping (ms)</th>"
                "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")

    off = [r for r in readings if r["slot"] is None]
    if off:
        body.append(f'<p class="sub">{len(off)} of {len(readings)} readings were off-slot '
                    f'(manual or catch-up runs) and are excluded from the slot averages.</p>')

    body.append("<h2>All readings</h2>")
    rows = []
    for r in reversed(readings):
        ping_cell = (f'<td>{fmt(r["ping"], 1)}</td>' if r["ping_ok"]
                     else f'<td class="bad">{fmt(r["ping"], 0)}</td>')
        rows.append(f'<tr><td>{no_pad(r["ts"].strftime("%d %b %H:%M"))}</td>'
                    f'<td>{r["slot"] or "&mdash;"}</td>'
                    f'<td>{fmt(r["download"])}</td><td>{fmt(r["upload"])}</td>'
                    f'{ping_cell}<td>{fmt(r["duration"], 1)}</td>'
                    f'<td>{html.escape(r["server"])}</td>'
                    f'<td>{"&mdash;" if r["samples"] is None else int(r["samples"])}</td></tr>')
    body.append('<div class="scroll"><table><thead><tr><th>Time</th><th>Slot</th>'
                "<th>Down</th><th>Up</th><th>Ping</th><th>Cycle</th><th>Server</th>"
                "<th>Samples</th></tr></thead><tbody>"
                + "".join(rows) + "</tbody></table></div>")

    flags = []
    bad_ping = [r for r in readings if not r["ping_ok"]]
    if bad_ping:
        flags.append(f"<strong>{len(bad_ping)} reading(s) carry an implausible ping</strong> and "
                     f"are excluded from every ping figure on this page. Speedtest returns a "
                     f"3,600,000 ms sentinel when a host is unreachable, and that gets averaged "
                     f"into the result.")
    degraded = [r for r in readings if r["degraded"]]
    if degraded:
        flags.append(f"<strong>{len(degraded)} run(s) completed fewer than {EXPECTED_SAMPLES} "
                     f"samples</strong>, so those averages rest on less data than the rest.")
    servers = sorted({r["server"] for r in readings if r["server"] != "unknown"})
    if len(servers) > 1:
        flags.append(f"<strong>Readings span {len(servers)} different test servers</strong> "
                     f"({html.escape(', '.join(servers))}). Throughput measured against a server "
                     f"hundreds of kilometres away is not comparable with a nearby one, so an "
                     f"apparent slowdown may be the measurement moving rather than the line.")
    if age_h > 24:
        flags.append(f"<strong>The most recent reading is {age_h / 24:.1f} days old.</strong> "
                     f"Collection is paused or failing.")
    if flags:
        body.append("<h2>Read this before trusting the numbers</h2>")
        body.append('<div class="note"><ul><li>' + "</li><li>".join(flags) + "</li></ul></div>")

    return page(body, readings, gen)


def page(body, readings, gen):
    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Internet Speed Report</title>
<meta name="description" content="Home network speed test history for Adam Aziz.">
<style>{CSS}</style>
</head>
<body class="viz-root">
<div class="wrap">
<h1>Internet Speed Report</h1>
<p class="sub">Home network, TPG Internet. Measured locally 4x daily when active
(9am, 12pm, 3pm, 7pm). Each reading is the average of 3 back-to-back tests.</p>
{"".join(body)}
<footer>
<p>{len(readings)} reading(s) in <code>speed-history.csv</code>. Page built
{gen.strftime("%d %b %Y %H:%M")} UTC by <code>build_report.py</code> in GitHub Actions.</p>
<p>Tests run on the home machine, never on the runner: a GitHub runner would measure
its own datacentre network, not this connection.</p>
</footer>
</div>
</body>
</html>
"""


def main():
    readings = load(CSV_PATH)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(build(readings))
    print(f"wrote {OUT_PATH} from {len(readings)} reading(s) in {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
