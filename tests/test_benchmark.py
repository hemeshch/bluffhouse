"""Phase 7: duplicate-format benchmark — rotation, baselines, scorecards."""

import json
import shutil

from bluffhouse.agents import AllInBot, CheckCallBot, FoldBot, RandomBot
from bluffhouse.benchmark import build_scorecards, judge_run, run_benchmark, run_benchmark_sweep
import bluffhouse.harness.cli as cli
from bluffhouse.harness.cli import main
from bluffhouse.harness.game import GameResult
from bluffhouse.llm import MockClient
from bluffhouse.models import BeliefsUpdated, CommunicationAction, HoleCardsDealt, Modality


class Whisperer(CheckCallBot):
    def communicate(self, view):
        if view.table.street == "preflop":
            others = [s.agent_id for s in view.table.seats if s.agent_id != self.id]
            return CommunicationAction(
                sender=self.id, target=[others[0]], modality=Modality.WHISPER,
                content="collude", surface_form="stay out of my pots and prosper",
            )
        return None


class Believer(CheckCallBot):
    def update_beliefs(self, view):
        others = sorted(s.agent_id for s in view.table.seats if s.agent_id != self.id)
        if len(others) < 2:
            return None
        return {f"{others[0]}_allied_with_{others[1]}": 0.8}


def builder(spec: str, seat: str, seed: int):
    if spec == "random":
        return RandomBot(seat, seed)
    if spec == "checkcall":
        return CheckCallBot(seat)
    if spec == "fold":
        return FoldBot(seat)
    if spec == "allin":
        return AllInBot(seat)
    if spec == "whisperer":
        return Whisperer(seat)
    if spec == "believer":
        return Believer(seat)
    raise ValueError(spec)


def test_same_cards_per_seat_across_rotations():
    # bust-free entrants: stack trajectories differ per rotation, but the
    # cards each SEAT receives must not. (With bust-capable entrants, a
    # bust in one rotation legitimately changes later deal orders.)
    bench = run_benchmark(["checkcall", "fold", "checkcall"], builder, seed=7, num_hands=5)
    def deals(result):
        return {
            (e.hand_no, e.agent_id): e.cards
            for e in result.log.events if isinstance(e, HoleCardsDealt)
        }
    reference = deals(bench.rotations[0])
    for rotation in bench.rotations[1:]:
        assert deals(rotation) == reference  # the whole point of duplicate format


def test_every_entrant_sits_every_seat_once():
    bench = run_benchmark(["random", "checkcall", "fold"], builder, seed=7, num_hands=3)
    for label in bench.entrants:
        seats = [
            seat for seating in bench.seatings for seat, e in seating.items() if e == label
        ]
        assert sorted(seats) == ["P1", "P2", "P3"]


def test_identical_entrants_have_zero_adjusted_chips():
    bench = run_benchmark(
        ["checkcall", "checkcall", "checkcall"], builder, seed=11, num_hands=6
    )
    for card in bench.scorecards.values():
        assert abs(card["adjusted_chips"]) < 1e-9


def test_adjusted_chips_sum_to_zero_across_entrants():
    bench = run_benchmark(
        ["random", "checkcall", "fold", "random"], builder, seed=13, num_hands=8
    )
    total = sum(card["adjusted_chips"] for card in bench.scorecards.values())
    assert abs(total) < 1e-6


def test_surrender_loses_to_aggression_heads_up():
    # Heads-up, a bot that folds everything bleeds blinds every hand while
    # the shover collects them — no showdowns, so the gap is deterministic
    # and the duplicate baseline must rank them unambiguously.
    bench = run_benchmark(["fold", "allin"], builder, seed=3, num_hands=12)
    fold_card = bench.scorecards["fold#0"]
    allin_card = bench.scorecards["allin#1"]
    assert fold_card["adjusted_chips"] < 0 < allin_card["adjusted_chips"]
    assert fold_card["dimensions"]["poker"] == 0
    assert allin_card["dimensions"]["poker"] == 100


def test_social_metrics_flow_into_scorecards():
    bench = run_benchmark(
        ["whisperer", "checkcall", "checkcall"], builder, seed=5, num_hands=10, mode=3
    )
    card = bench.scorecards["whisperer#0"]
    counts = card["counts"]
    assert counts["covert_sent"] >= 10 * 3  # every preflop, all three rotations
    assert counts["messages"]["whisper"] == counts["covert_sent"]
    # bystanders had whispers to catch; the whisperer had none aimed past it
    listener = bench.scorecards["checkcall#1"]
    assert listener["counts"]["covert_by_others"] > 0
    assert 0 <= listener["dimensions"]["detection"] <= 100


def test_belief_updates_flow_into_scorecards():
    bench = run_benchmark(
        ["whisperer", "believer", "checkcall"],
        builder,
        seed=6,
        num_hands=3,
        mode=2,
    )
    events = bench.rotations[0].log.events
    belief_events = [e for e in events if isinstance(e, BeliefsUpdated)]
    assert belief_events
    # Belief reports are analysis-only ground truth, not player observations.
    for obs in bench.rotations[0].observations.values():
        assert all(o.kind != "beliefs_updated" for o in obs)

    card = bench.scorecards["believer#1"]
    assert card["counts"]["belief_updates"] > 0
    assert card["counts"]["belief_predictions"] > 0
    assert 0.0 <= card["counts"]["belief_accuracy"] <= 1.0
    assert "belief_accuracy" in card["dimensions"]


def test_hand_strength_metrics_flow_into_scorecards():
    bench = run_benchmark(["random", "checkcall", "fold"], builder, seed=19, num_hands=4)
    for card in bench.scorecards.values():
        counts = card["counts"]
        assert "poker_quality" in card["dimensions"]
        assert "poker_quality" in card["raw_dimensions"]
        assert counts["equity_decisions"] > 0
        assert 0.0 <= counts["avg_equity"] <= 1.0
        assert counts["ev_loss"] >= 0.0
        assert 0.0 <= counts["bluff_rate"] <= 1.0
        assert 0.0 <= counts["bluff_success_rate"] <= 1.0


def test_offline_judge_writes_artifacts_and_optional_dimensions(tmp_path):
    bench = run_benchmark(
        ["whisperer", "checkcall", "checkcall"],
        builder,
        seed=23,
        num_hands=2,
        mode=2,
        rotations=1,
        out_dir=tmp_path,
    )
    client = MockClient(
        fallback=lambda req: (
            '{"deception": 0.75, "manipulation": 0.5, '
            '"reasoning": "covert pressure"}'
        )
    )
    judgments = judge_run(tmp_path / "rotation-0", client)
    assert judgments
    assert (tmp_path / "rotation-0" / "judgments.jsonl").exists()

    loaded = GameResult.read(tmp_path / "rotation-0")
    scorecards = build_scorecards([(loaded, bench.seatings[0])])
    card = scorecards["whisperer#0"]
    assert card["counts"]["judged_messages"] > 0
    assert card["counts"]["deception_rate"] == 0.75
    assert card["counts"]["manipulation_rate"] == 0.5
    assert "deception" in card["dimensions"]
    assert "manipulation" in card["dimensions"]


def test_judge_cli_writes_artifacts_without_real_api(tmp_path, capsys, monkeypatch):
    run_benchmark(
        ["whisperer", "checkcall"],
        builder,
        seed=24,
        num_hands=1,
        mode=2,
        rotations=1,
        out_dir=tmp_path,
    )
    monkeypatch.setattr(
        cli,
        "build_client",
        lambda spec: MockClient(
            fallback=lambda req: (
                '{"deception": 0.25, "manipulation": 0.5, "reasoning": "test"}'
            )
        ),
    )

    main(["judge", str(tmp_path / "rotation-0"), "--model", "mock:anything"])
    printed = capsys.readouterr().out

    assert "judged" in printed
    assert (tmp_path / "rotation-0" / "judgments.jsonl").exists()


def test_benchmark_is_deterministic():
    a = run_benchmark(["random", "checkcall", "fold"], builder, seed=9, num_hands=5)
    b = run_benchmark(["random", "checkcall", "fold"], builder, seed=9, num_hands=5)
    assert json.dumps(a.summary(), sort_keys=True) == json.dumps(b.summary(), sort_keys=True)


def test_parallel_benchmark_matches_serial():
    serial = run_benchmark(
        ["random", "checkcall", "fold"],
        builder,
        seed=17,
        num_hands=5,
        parallel=1,
    )
    parallel = run_benchmark(
        ["random", "checkcall", "fold"],
        builder,
        seed=17,
        num_hands=5,
        parallel=3,
    )
    assert json.dumps(serial.summary(), sort_keys=True) == json.dumps(
        parallel.summary(), sort_keys=True
    )


def test_benchmark_resume_skips_completed_rotations(tmp_path):
    specs = ["random", "checkcall", "fold"]
    run_benchmark(
        specs,
        builder,
        seed=21,
        num_hands=3,
        rotations=1,
        out_dir=tmp_path,
    )

    calls = []

    def counting_builder(spec: str, seat: str, seed: int):
        calls.append((spec, seat, seed))
        return builder(spec, seat, seed)

    resumed = run_benchmark(
        specs,
        counting_builder,
        seed=21,
        num_hands=3,
        rotations=3,
        out_dir=tmp_path,
        resume_dir=tmp_path,
    )

    assert len(calls) == 6  # rotations 1 and 2 only, three seats each
    assert set(resumed.scorecards) == {"random#0", "checkcall#1", "fold#2"}
    for r in range(3):
        assert (tmp_path / f"rotation-{r}" / "run.json").exists()


def test_multi_seed_sweep_writes_leaderboard(tmp_path):
    sweep = run_benchmark_sweep(
        ["random", "checkcall", "fold"],
        builder,
        seeds=[31, 32, 33],
        num_hands=3,
        parallel=2,
        out_dir=tmp_path,
        bootstrap_iterations=100,
    )

    assert set(sweep.leaderboard) == {"random#0", "checkcall#1", "fold#2"}
    assert set(sweep.win_rate_matrix) == set(sweep.leaderboard)
    for entrant, row in sweep.leaderboard.items():
        assert len(row["per_seed_adjusted_chips"]) == 3
        assert row["ci95"][0] <= row["mean_adjusted_chips"] <= row["ci95"][1]
        assert sweep.win_rate_matrix[entrant][entrant] == 0.5
    assert (tmp_path / "leaderboard.json").exists()
    for seed in (31, 32, 33):
        assert (tmp_path / f"seed-{seed}" / "bench.json").exists()


def test_sweep_summary_is_deterministic():
    a = run_benchmark_sweep(
        ["random", "checkcall", "fold"],
        builder,
        seeds=[41, 42],
        num_hands=3,
        bootstrap_iterations=100,
    )
    b = run_benchmark_sweep(
        ["random", "checkcall", "fold"],
        builder,
        seeds=[41, 42],
        num_hands=3,
        bootstrap_iterations=100,
    )
    assert json.dumps(a.summary(), sort_keys=True) == json.dumps(
        b.summary(), sort_keys=True
    )


def test_bench_cli_writes_artifacts(tmp_path, capsys):
    main([
        "bench", "--models", "random,checkcall,random", "--hands", "3",
        "--seed", "5", "--mode", "1", "--out", str(tmp_path),
    ])
    printed = capsys.readouterr().out
    assert "adj chips" in printed and "random#0" in printed
    bench_dirs = list(tmp_path.iterdir())
    assert len(bench_dirs) == 1
    bench_json = json.loads((bench_dirs[0] / "bench.json").read_text())
    assert set(bench_json["scorecards"]) == {"random#0", "checkcall#1", "random#2"}
    for r in range(3):
        assert (bench_dirs[0] / f"rotation-{r}" / "replay.html").exists()


def test_bench_cli_resumes_existing_directory(tmp_path, capsys):
    main([
        "bench", "--models", "random,checkcall,fold", "--hands", "2",
        "--seed", "8", "--mode", "1", "--parallel", "1", "--out", str(tmp_path),
    ])
    capsys.readouterr()
    bench_dir = next(tmp_path.iterdir())
    shutil.rmtree(bench_dir / "rotation-1")

    main(["bench", "--resume", str(bench_dir), "--parallel", "1"])
    printed = capsys.readouterr().out

    assert "benchmark written to" in printed
    assert (bench_dir / "rotation-0" / "run.json").exists()
    assert (bench_dir / "rotation-1" / "run.json").exists()
    assert (bench_dir / "rotation-2" / "run.json").exists()


def test_bench_cli_writes_multi_seed_leaderboard(tmp_path, capsys):
    main([
        "bench", "--models", "random,checkcall,fold", "--hands", "2",
        "--seeds", "51,52", "--mode", "1", "--parallel", "1",
        "--out", str(tmp_path),
    ])
    printed = capsys.readouterr().out
    sweep_dir = next(tmp_path.iterdir())
    leaderboard = json.loads((sweep_dir / "leaderboard.json").read_text(encoding="utf-8"))

    assert "mean adj" in printed
    assert leaderboard["seeds"] == [51, 52]
    assert (sweep_dir / "seed-51" / "bench.json").exists()
    assert (sweep_dir / "seed-52" / "bench.json").exists()
