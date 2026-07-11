"""`bluffhouse serve` — a tiny local hub over the runs directory.

Scans for runs, benches, and sweeps, renders one index page with
click-through links to every replay and leaderboard, and serves the files.
stdlib only, bound to 127.0.0.1; the hub regenerates on every page load so
new runs appear on refresh. Replays stay self-contained files — the hub is
navigation, not a dependency.
"""

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def collect_entries(root: Path) -> dict:
    """Everything worth linking under `root`, newest first."""
    sweeps, benches, runs = [], [], []
    bench_dirs: set[Path] = set()

    for leaderboard in sorted(root.rglob("leaderboard.json"), reverse=True):
        data = json.loads(leaderboard.read_text(encoding="utf-8"))
        top = sorted(
            data.get("leaderboard", {}).items(),
            key=lambda kv: -kv[1]["mean_adjusted_chips"],
        )
        sweeps.append({
            "name": str(leaderboard.parent.relative_to(root)) or ".",
            "seeds": data.get("seeds", []),
            "mode": data.get("mode"),
            "rows": [
                (entrant, row["mean_adjusted_chips"], row["ci95"])
                for entrant, row in top
            ],
        })

    for bench_json in sorted(root.rglob("bench.json"), reverse=True):
        bench_dir = bench_json.parent
        bench_dirs.add(bench_dir)
        data = json.loads(bench_json.read_text(encoding="utf-8"))
        ranked = sorted(
            data.get("scorecards", {}).items(),
            key=lambda kv: -kv[1]["adjusted_chips"],
        )
        replays = sorted(
            p.relative_to(root).as_posix()
            for p in bench_dir.glob("rotation-*/replay.html")
        )
        benches.append({
            "name": str(bench_dir.relative_to(root)) or ".",
            "seed": data.get("seed"),
            "mode": data.get("mode"),
            "hands": data.get("num_hands"),
            "rows": [(e, card["adjusted_chips"]) for e, card in ranked],
            "replays": replays,
        })

    for run_json in sorted(root.rglob("run.json"), reverse=True):
        run_dir = run_json.parent
        if any(parent in bench_dirs for parent in run_dir.parents):
            continue  # listed under its bench
        data = json.loads(run_json.read_text(encoding="utf-8"))
        config = data.get("config", {})
        replay = run_dir / "replay.html"
        runs.append({
            "name": str(run_dir.relative_to(root)) or ".",
            "seed": config.get("seed"),
            "mode": config.get("mode"),
            "hands": data.get("hands_played"),
            "stacks": data.get("final_stacks", {}),
            "replay": replay.relative_to(root).as_posix() if replay.exists() else None,
        })

    return {"sweeps": sweeps, "benches": benches, "runs": runs}


def render_hub(root: Path) -> str:
    e = _escape
    entries = collect_entries(root)
    sections = []

    if entries["sweeps"]:
        cards = []
        for sweep in entries["sweeps"]:
            rows = "".join(
                f"<tr><td>{e(entrant)}</td><td class='n'>{chips:+.1f}</td>"
                f"<td class='ci'>[{ci[0]:+.1f}, {ci[1]:+.1f}]</td></tr>"
                for entrant, chips, ci in sweep["rows"]
            )
            cards.append(
                f"<div class='card'><h3>{e(sweep['name'])}</h3>"
                f"<p class='meta'>sweep · mode {sweep['mode']} · seeds {e(', '.join(map(str, sweep['seeds'])))}</p>"
                f"<table><tr><th>entrant</th><th>mean adj</th><th>95% CI</th></tr>{rows}</table></div>"
            )
        sections.append("<h2>Leaderboards</h2>" + "".join(cards))

    if entries["benches"]:
        cards = []
        for bench in entries["benches"]:
            rows = "".join(
                f"<tr><td>{e(entrant)}</td><td class='n'>{chips:+.1f}</td></tr>"
                for entrant, chips in bench["rows"]
            )
            links = " ".join(
                f"<a href='/{e(replay)}'>rotation {i}</a>"
                for i, replay in enumerate(bench["replays"])
            )
            cards.append(
                f"<div class='card'><h3>{e(bench['name'])}</h3>"
                f"<p class='meta'>bench · mode {bench['mode']} · {bench['hands']} hands · seed {bench['seed']}</p>"
                f"<table><tr><th>entrant</th><th>adj chips</th></tr>{rows}</table>"
                f"<p class='links'>{links}</p></div>"
            )
        sections.append("<h2>Benchmarks</h2>" + "".join(cards))

    if entries["runs"]:
        cards = []
        for run in entries["runs"]:
            stacks = " · ".join(
                f"{e(aid)} {stack}"
                for aid, stack in sorted(run["stacks"].items(), key=lambda kv: -kv[1])
            )
            link = (
                f"<p class='links'><a href='/{e(run['replay'])}'>watch replay</a></p>"
                if run["replay"] else ""
            )
            cards.append(
                f"<div class='card'><h3>{e(run['name'])}</h3>"
                f"<p class='meta'>game · mode {run['mode']} · {run['hands']} hands · seed {run['seed']}</p>"
                f"<p class='meta'>{stacks}</p>{link}</div>"
            )
        sections.append("<h2>Games</h2>" + "".join(cards))

    if not sections:
        sections.append(
            "<p class='meta'>Nothing here yet. Try <code>bluffhouse demo</code> "
            "or <code>bluffhouse bench --models ...</code></p>"
        )

    body = "".join(sections)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bluffhouse</title>
<style>
  :root {{ --bg:#262421; --panel:#302E2B; --border:#3E3C39; --text:#EDEBE9;
           --muted:#A29F9B; --faint:#7C7975; --green:#81B64C; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); line-height:1.5;
         font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; }}
  header {{ padding:14px 26px; background:var(--panel); border-bottom:1px solid var(--border);
            display:flex; align-items:center; gap:12px; }}
  .wordmark {{ font-size:19px; font-weight:800; letter-spacing:-.02em; }}
  .tag {{ font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
          background:var(--green); color:#fff; padding:2px 7px; border-radius:5px; }}
  main {{ max-width:880px; margin:0 auto; padding:22px 26px 60px; }}
  h2 {{ font-size:12px; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
        color:var(--faint); margin:26px 0 10px; }}
  .card {{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
           padding:14px 18px; margin-bottom:12px; }}
  .card h3 {{ margin:0 0 2px; font-size:14.5px; font-weight:700; }}
  .meta {{ margin:2px 0; font-size:12.5px; color:var(--muted); }}
  table {{ border-collapse:collapse; margin:8px 0 2px; font-size:13px; }}
  th {{ text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.07em;
        color:var(--faint); padding:2px 18px 4px 0; }}
  td {{ padding:2px 18px 2px 0; color:var(--muted); }}
  td:first-child {{ color:var(--text); font-weight:600; }}
  .n {{ font-family:ui-monospace,Menlo,monospace; }}
  .ci {{ font-family:ui-monospace,Menlo,monospace; color:var(--faint); }}
  .links a {{ display:inline-block; background:var(--green); color:#fff; font-weight:700;
              font-size:12.5px; text-decoration:none; padding:6px 13px; border-radius:7px;
              margin:4px 8px 0 0; }}
  .links a:hover {{ filter:brightness(1.08); }}
  code {{ font-family:ui-monospace,Menlo,monospace; color:var(--green); }}
</style></head>
<body>
<header><span class="wordmark">bluffhouse</span><span class="tag">hub</span></header>
<main>{body}</main>
</body></html>"""


def _escape(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class _HubHandler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.path in ("/", "/index.html"):
            page = render_hub(Path(self.directory)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        super().do_GET()

    def log_message(self, format, *args):  # quiet
        pass


def serve(root: str | Path = "runs", port: int = 8484, open_browser: bool = True) -> None:
    root = Path(root).resolve()
    if not root.exists():
        raise SystemExit(f"{root} does not exist — run a game or bench first")
    handler = partial(_HubHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"bluffhouse hub: {url}  (serving {root}; ctrl-c to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
