"""`bluffhouse serve` — the local bluffhouse app.

A FastAPI server over the runs directory: serves the built React app, a JSON
API for run discovery / replay payloads / benchmark results, and live games.
Bound to 127.0.0.1. Replays remain self-contained files — the app reads runs
through the API, but every run dir still carries its own replay.html.
"""

import json
import os
import time
import webbrowser
from importlib.resources import files
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


DEMO_DIR = "demo-seed11"


def create_app(root: Path):
    import queue as queue_mod

    from fastapi import APIRouter, FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field, SecretStr

    from bluffhouse.harness.live import LiveJob, build_seats, start_live_game
    from bluffhouse.models import TableConfig

    root = root.resolve()
    app = FastAPI(title="bluffhouse", openapi_url=None)
    api = APIRouter(prefix="/api")
    jobs: dict[str, LiveJob] = {}

    def resolve_dir(rel: str) -> Path:
        target = (root / rel).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(400, "path escapes the runs directory")
        return target

    def read_json(path: Path) -> dict:
        if not path.exists():
            raise HTTPException(404, f"{path.name} not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @api.get("/hub")
    def hub() -> dict:
        return collect_entries(root)

    @api.get("/replay")
    def replay(dir: str) -> dict:
        from bluffhouse.harness.game import GameResult

        target = resolve_dir(dir)
        if not (target / "run.json").exists():
            raise HTTPException(404, f"no run at {dir}")
        return GameResult.read(target).replay_payload()

    @api.get("/bench")
    def bench(dir: str) -> dict:
        return read_json(resolve_dir(dir) / "bench.json")

    @api.get("/leaderboard")
    def leaderboard(dir: str) -> dict:
        return read_json(resolve_dir(dir) / "leaderboard.json")

    @api.post("/demo")
    def demo() -> dict:
        # the demo game is deterministic, so one generated copy is reused
        from bluffhouse.demo import demo_game

        out = root / DEMO_DIR
        if not (out / "run.json").exists():
            demo_game().write(out)
        return {"dir": DEMO_DIR}

    # ── live games ──────────────────────────────────────────────────

    class SeatSpec(BaseModel):
        spec: str  # "anthropic:claude-opus-4-8", "openai:gpt-5.2", "checkcall", ...
        name: str | None = None
        api_key: SecretStr | None = None  # memory-only; never persisted

    class LiveRequest(BaseModel):
        seats: list[SeatSpec] = Field(min_length=2, max_length=10)
        hands: int = Field(6, ge=1, le=500)
        mode: int = Field(6, ge=0, le=6)
        seed: int | None = None
        stack: int = Field(1000, ge=1)
        small_blind: int = Field(5, ge=1)
        big_blind: int = Field(10, ge=1)
        collect_beliefs: bool = True

    # public deployments: a thread bomb is one curl loop away without a cap
    max_active = int(os.environ.get("BLUFFHOUSE_MAX_ACTIVE_GAMES", "12"))

    @api.post("/live")
    def live_start(req: LiveRequest) -> dict:
        active = sum(1 for j in jobs.values() if j.status == "running")
        if active >= max_active:
            raise HTTPException(
                429, f"{active} games already running on this server — try again shortly"
            )
        seed = req.seed if req.seed is not None else int(time.time()) % 1_000_000
        for i, seat in enumerate(req.seats):
            key = seat.api_key.get_secret_value().strip() if seat.api_key else ""
            if key and not key.isascii():
                # keys travel in HTTP headers, which are ASCII-only — a smart
                # quote or em dash from a rich-text copy kills every call
                raise HTTPException(
                    400,
                    f"seat {i + 1}: the API key contains a non-ASCII character "
                    "(often an em dash or smart quote from a rich-text copy) — "
                    "re-copy it as plain text",
                )
            if seat.name and ("/" in seat.name or "\x00" in seat.name):
                raise HTTPException(400, f"seat {i + 1}: name cannot contain '/'")
        seat_dicts = [
            {
                "spec": s.spec,
                "name": s.name,
                "api_key": s.api_key.get_secret_value().strip() if s.api_key else None,
            }
            for s in req.seats
        ]
        try:
            agents = build_seats(seat_dicts, seed)
            config = TableConfig(
                seed=seed,
                num_hands=req.hands,
                small_blind=req.small_blind,
                big_blind=req.big_blind,
                starting_stack=req.stack,
                agent_ids=[a.id for a in agents],
                mode=req.mode,
                collect_beliefs=req.collect_beliefs,
            )
        except (SystemExit, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        job = start_live_game(root, config, agents, run_dir_name("live", seed))
        jobs[job.id] = job
        # keep memory bounded on long-lived public servers
        finished = [jid for jid, j in jobs.items() if j.status != "running"]
        for jid in finished[:-50]:
            del jobs[jid]
        return {"job": job.id, "config": config.model_dump()}

    def get_job(job_id: str) -> LiveJob:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such live game")
        return job

    @api.get("/live/{job_id}")
    def live_status(job_id: str) -> dict:
        return get_job(job_id).snapshot()

    @api.post("/live/{job_id}/stop")
    def live_stop(job_id: str) -> dict:
        job = get_job(job_id)
        job.stop_requested = True
        return job.snapshot()

    @api.get("/live/{job_id}/events")
    def live_events(job_id: str, request: Request) -> StreamingResponse:
        job = get_job(job_id)
        last_raw = request.headers.get("last-event-id")
        last_id = int(last_raw) if last_raw and last_raw.isdigit() else None

        def stream():
            backlog, q = job.subscribe()
            try:
                yield "retry: 1500\n\n"
                for seq, data in backlog:
                    if last_id is not None and seq <= last_id:
                        continue
                    yield f"id: {seq}\nevent: event\ndata: {data}\n\n"
                if job.activity is not None:
                    yield f"event: status\ndata: {json.dumps(job.activity)}\n\n"
                while True:
                    if job.status != "running" and q.empty():
                        yield f"event: done\ndata: {json.dumps(job.snapshot())}\n\n"
                        return
                    try:
                        kind, seq, data = q.get(timeout=5)
                    except queue_mod.Empty:
                        yield ": ping\n\n"
                        continue
                    if kind == "event":
                        yield f"id: {seq}\nevent: event\ndata: {data}\n\n"
                    elif kind == "status":
                        yield f"event: status\ndata: {data}\n\n"
                    else:  # done
                        yield f"event: done\ndata: {json.dumps(job.snapshot())}\n\n"
                        return
            finally:
                job.unsubscribe(q)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.include_router(api)
    app.mount("/runs", StaticFiles(directory=str(root)), name="runs")

    static_dir = Path(str(files("bluffhouse.webapp") / "static"))
    if (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="app")
    else:  # source checkout without a frontend build

        @app.get("/", response_class=HTMLResponse)
        def missing_build() -> str:
            return (
                "<body style='background:#262421;color:#edebe9;font-family:sans-serif'>"
                "<p>No frontend build found. Run <code>npm install && npm run build</code> "
                "in <code>web/</code>, then restart <code>bluffhouse serve</code>.</p></body>"
            )

    return app


def serve(
    root: str | Path = "runs",
    port: int = 8484,
    open_browser: bool = True,
    host: str = "127.0.0.1",
) -> None:
    import uvicorn

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = create_app(root)
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/"
    print(f"bluffhouse: {url}  (serving {root}; ctrl-c to stop)")
    if open_browser and host == "127.0.0.1":
        # give uvicorn a beat to bind before the browser asks
        import threading

        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\nstopped")


# keep a timestamp helper here so live/demo runs share one naming scheme
def run_dir_name(prefix: str, seed: int) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{prefix}-seed{seed}"
