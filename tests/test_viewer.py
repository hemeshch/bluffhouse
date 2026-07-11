"""Replay generation: every run writes a self-contained replay.html."""

from bluffhouse.agents import CheckCallBot, LLMAgent
from bluffhouse.harness import GameHarness
from bluffhouse.harness.game import GameResult
from bluffhouse.llm import MockClient
from bluffhouse.models import TableConfig
from bluffhouse.viewer import render_replay


def run_result(tmp_path):
    client = MockClient(fallback=lambda req: '{"reasoning": "pot odds", "action": "call"}')
    agents = [LLMAgent("A", client), CheckCallBot("B")]
    config = TableConfig(seed=4, num_hands=2, agent_ids=["A", "B"])
    result = GameHarness(config, agents).run()
    return result, result.write(tmp_path / "run")


def test_write_produces_all_artifacts(tmp_path):
    _, out = run_result(tmp_path)
    assert (out / "events.jsonl").exists()
    assert (out / "observations" / "A.jsonl").exists()
    assert (out / "llm" / "A.jsonl").exists()  # transcripts now written by the harness
    assert not (out / "llm" / "B.jsonl").exists()  # bots have no transcript
    assert (out / "run.json").exists()
    assert (out / "replay.html").exists()


def test_game_result_reads_written_artifacts(tmp_path):
    result, out = run_result(tmp_path)
    loaded = GameResult.read(out)
    assert loaded.config == result.config
    assert loaded.final_stacks == result.final_stacks
    assert loaded.hands_played == result.hands_played
    assert [e.model_dump() for e in loaded.log.events] == [
        e.model_dump() for e in result.log.events
    ]
    assert loaded.observations.keys() == result.observations.keys()
    assert loaded.llm_calls.keys() == result.llm_calls.keys()


def test_replay_embeds_run_data(tmp_path):
    result, out = run_result(tmp_path)
    html = (out / "replay.html").read_text(encoding="utf-8")
    assert "/*__BLUFFHOUSE_DATA__*/ null" not in html  # marker replaced
    assert '"hand_started"' in html and '"hole_cards_dealt"' in html
    assert "pot odds" in html  # llm reasoning rides along (inner quotes get escaped)
    assert "</script>" in html  # page intact


def test_render_replay_escapes_script_closers():
    html = render_replay({"run": {"note": "</script><script>alert(1)"}, "events": []})
    assert "<\\/script>" in html
    assert "</script><script>alert(1)" not in html
