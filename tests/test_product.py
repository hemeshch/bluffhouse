"""The product wrapper: demo command, serve hub, belief opt-out, judge resilience."""

import json

from bluffhouse.benchmark import judge_run, run_benchmark
from bluffhouse.demo import demo_game
from bluffhouse.harness.cli import main
from bluffhouse.harness.serve import collect_entries, render_hub
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


# ── serve hub ───────────────────────────────────────────────────────


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

    html = render_hub(tmp_path)
    assert "demo-1/replay.html" in html
    assert "bench-1/rotation-0/replay.html" in html
    assert "random#0" in html


def test_hub_handles_empty_directory(tmp_path):
    html = render_hub(tmp_path)
    assert "bluffhouse demo" in html  # the nudge, not a crash


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
