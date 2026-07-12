"""The product wrapper: demo command, serve API, belief opt-out, judge resilience."""

import json

from fastapi.testclient import TestClient

from bluffhouse.benchmark import judge_run, run_benchmark
from bluffhouse.demo import demo_game
from bluffhouse.harness.cli import main
from bluffhouse.harness.serve import collect_entries, create_app
from bluffhouse.llm import LLMClient, LLMError, MockClient
from bluffhouse.models import BeliefsUpdated, MessageSent, TableConfig
from test_benchmark import Believer, builder


# ── demo ────────────────────────────────────────────────────────────


def test_demo_game_delivers_the_full_drama(tmp_path):
    result = demo_game()
    messages = [e for e in result.log.events if isinstance(e, MessageSent)]
    modalities = {m.modality for m in messages}
    assert {"whisper", "note", "accusation", "speech"} <= modalities
    # the mock LLM reports beliefs and they land as env-only events
    beliefs = [e for e in result.log.events if isinstance(e, BeliefsUpdated)]
    assert any(e.agent_id == "Claude" for e in beliefs)
    # deterministic: same demo every time
    assert demo_game().log.to_jsonl() == result.log.to_jsonl()

    out = result.write(tmp_path / "demo")
    assert (out / "replay.html").exists()


def test_demo_cli_writes_and_respects_no_open(tmp_path, capsys):
    main(["demo", "--out", str(tmp_path), "--no-open"])
    printed = capsys.readouterr().out
    assert "replay:" in printed
    demo_dirs = list(tmp_path.iterdir())
    assert len(demo_dirs) == 1
    assert (demo_dirs[0] / "replay.html").exists()


# ── serve API ───────────────────────────────────────────────────────


def test_hub_lists_runs_and_benches(tmp_path):
    demo_game().write(tmp_path / "demo-1")
    run_benchmark(
        ["random", "checkcall"], builder, seed=3, num_hands=2,
        out_dir=tmp_path / "bench-1",
    )

    entries = collect_entries(tmp_path)
    assert [r["name"] for r in entries["runs"]] == ["demo-1"]
    assert [b["name"] for b in entries["benches"]] == ["bench-1"]
    # bench rotations are not double-listed as standalone runs
    assert all("rotation" not in r["name"] for r in entries["runs"])

    client = TestClient(create_app(tmp_path))
    hub = client.get("/api/hub").json()
    assert [r["name"] for r in hub["runs"]] == ["demo-1"]
    assert hub["benches"][0]["rows"][0][0] in ("random#0", "checkcall#1")
    # raw run files are served under /runs/
    assert client.get("/runs/demo-1/replay.html").status_code == 200


def test_api_hub_handles_empty_directory(tmp_path):
    client = TestClient(create_app(tmp_path))
    hub = client.get("/api/hub").json()
    assert hub == {"sweeps": [], "benches": [], "runs": []}


def test_api_replay_serves_payload_and_guards_traversal(tmp_path):
    result = demo_game()
    result.write(tmp_path / "demo-1")
    client = TestClient(create_app(tmp_path))

    payload = client.get("/api/replay", params={"dir": "demo-1"}).json()
    assert set(payload) == {"run", "events", "observations", "llm", "judgments"}
    assert len(payload["events"]) == len(result.log.events)
    assert payload["run"]["seed"] == result.config.seed

    assert client.get("/api/replay", params={"dir": "../demo-1"}).status_code == 400
    assert client.get("/api/replay", params={"dir": "nope"}).status_code == 404


def test_api_demo_generates_once_and_reuses(tmp_path):
    client = TestClient(create_app(tmp_path))
    first = client.post("/api/demo").json()
    assert (tmp_path / first["dir"] / "run.json").exists()
    again = client.post("/api/demo").json()
    assert again == first
    assert client.get("/api/replay", params={"dir": first["dir"]}).status_code == 200


# ── live games over SSE ─────────────────────────────────────────────


def test_live_game_streams_and_writes(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.post("/api/live", json={
        "seats": [{"spec": "checkcall"}, {"spec": "fold"}, {"spec": "random", "name": "Rando"}],
        "hands": 2, "mode": 0, "seed": 7,
    })
    assert resp.status_code == 200
    started = resp.json()
    assert started["config"]["agent_ids"] == ["checkcall-1", "fold-2", "Rando"]
    job = started["job"]

    events, done = [], None
    with client.stream("GET", f"/api/live/{job}/events") as stream:
        kind = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                kind = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
                if kind == "event":
                    events.append(data)
                elif kind == "done":
                    done = data
                    break

    assert done and done["status"] == "done" and done["run_dir"]
    assert (tmp_path / done["run_dir"] / "replay.html").exists()
    types = {e["type"] for e in events}
    assert {"game_started", "hand_started", "action_taken", "hand_ended", "game_ended"} <= types
    snap = client.get(f"/api/live/{job}").json()
    assert snap["status"] == "done"
    assert snap["events"] == len(events)
    # the finished live run shows up in the hub like any other
    hub = client.get("/api/hub").json()
    assert any(r["name"] == done["run_dir"] for r in hub["runs"])


def test_live_wrapper_preserves_llm_transcripts(tmp_path):
    from bluffhouse.agents import CheckCallBot, LLMAgent
    from bluffhouse.harness.live import start_live_game

    client = MockClient(fallback=lambda req: '{"reasoning": "ok", "action": "call"}')
    agents = [LLMAgent("A", client), CheckCallBot("B")]
    config = TableConfig(seed=9, num_hands=1, agent_ids=["A", "B"], mode=0)
    job = start_live_game(tmp_path, config, agents, "live-test")
    job.thread.join(timeout=30)
    assert job.status == "done"
    # the _Watched wrapper must pass the inner seat's transcript through
    assert (tmp_path / "live-test" / "llm" / "A.jsonl").exists()


def test_live_stop_writes_partial_run(tmp_path):
    import time

    from bluffhouse.agents import CheckCallBot
    from bluffhouse.harness.live import start_live_game

    class Slow(CheckCallBot):
        def act(self, view):
            time.sleep(0.05)
            return super().act(view)

    agents = [Slow("A"), Slow("B")]
    config = TableConfig(seed=3, num_hands=50, agent_ids=["A", "B"], mode=0)
    job = start_live_game(tmp_path, config, agents, "stopped-run")
    time.sleep(0.3)
    job.stop_requested = True
    job.thread.join(timeout=30)

    assert job.status == "stopped"
    assert job.run_dir == "stopped-run"
    out = tmp_path / "stopped-run"
    assert (out / "events.jsonl").exists()
    assert (out / "replay.html").exists()
    # partial: fewer hands than configured actually completed
    run = json.loads((out / "run.json").read_text())
    assert run["hands_played"] < 50


def test_live_rejects_bad_specs(tmp_path):
    client = TestClient(create_app(tmp_path))
    bad = client.post("/api/live", json={
        "seats": [{"spec": "nonsense"}, {"spec": "fold"}], "mode": 0,
    })
    assert bad.status_code == 400
    too_few = client.post("/api/live", json={"seats": [{"spec": "fold"}]})
    assert too_few.status_code == 422
    # keys ride in ASCII-only HTTP headers — reject rich-text paste damage early
    mangled_key = client.post("/api/live", json={
        "seats": [
            {"spec": "anthropic:claude-sonnet-5", "api_key": "sk-ant—mangled"},
            {"spec": "fold"},
        ],
    })
    assert mangled_key.status_code == 400
    assert "non-ASCII" in mangled_key.json()["detail"]


# ── belief opt-out ──────────────────────────────────────────────────


def test_no_beliefs_flag_suppresses_belief_phase(tmp_path):
    from bluffhouse.agents import CheckCallBot
    from bluffhouse.harness import GameHarness

    def play(collect):
        agents = [Believer("A"), CheckCallBot("B"), CheckCallBot("C")]
        config = TableConfig(
            seed=5, num_hands=2, agent_ids=["A", "B", "C"],
            mode=2, collect_beliefs=collect,
        )
        return GameHarness(config, agents).run()

    with_beliefs = play(True)
    without = play(False)
    assert any(isinstance(e, BeliefsUpdated) for e in with_beliefs.log.events)
    assert not any(isinstance(e, BeliefsUpdated) for e in without.log.events)


def test_bench_no_beliefs_flag():
    bench = run_benchmark(
        ["whisperer", "believer", "checkcall"], builder, seed=6, num_hands=2,
        mode=2, collect_beliefs=False,
    )
    for rotation in bench.rotations:
        assert not any(isinstance(e, BeliefsUpdated) for e in rotation.log.events)
    assert bench.scorecards["believer#1"]["counts"]["belief_updates"] == 0


# ── judge resilience ────────────────────────────────────────────────


class FlakyClient(LLMClient):
    """Fails on every second call."""

    model = "flaky"

    def __init__(self):
        self.calls = 0
        self._inner = MockClient(
            fallback=lambda req: '{"deception": 0.5, "manipulation": 0.5, "reasoning": "ok"}'
        )

    def complete(self, request):
        self.calls += 1
        if self.calls % 2 == 0:
            raise LLMError("provider is down")
        return self._inner.complete(request)


def test_judge_survives_provider_failures(tmp_path):
    result = demo_game()
    run_dir = result.write(tmp_path / "run")
    judgments = judge_run(run_dir, FlakyClient())

    messages = [e for e in result.log.events if isinstance(e, MessageSent)]
    assert len(judgments) == len(messages)  # nothing dropped
    errored = [j for j in judgments if j["parse_error"]]
    clean = [j for j in judgments if not j["parse_error"]]
    assert errored and clean
    assert all("provider is down" in j["parse_error"] for j in errored)
    # the file still landed, complete
    lines = (run_dir / "judgments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(messages)
    json.loads(lines[0])
