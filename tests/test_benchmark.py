"""Phase 7: duplicate-format benchmark — rotation, baselines, scorecards."""

import json

from bluffhouse.agents import AllInBot, CheckCallBot, FoldBot, RandomBot
from bluffhouse.benchmark import run_benchmark
from bluffhouse.harness.cli import main
from bluffhouse.models import CommunicationAction, HoleCardsDealt, Modality


class Whisperer(CheckCallBot):
    def communicate(self, view):
        if view.table.street == "preflop":
            others = [s.agent_id for s in view.table.seats if s.agent_id != self.id]
            return CommunicationAction(
                sender=self.id, target=[others[0]], modality=Modality.WHISPER,
                content="collude", surface_form="stay out of my pots and prosper",
            )
        return None


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


def test_benchmark_is_deterministic():
    a = run_benchmark(["random", "checkcall", "fold"], builder, seed=9, num_hands=5)
    b = run_benchmark(["random", "checkcall", "fold"], builder, seed=9, num_hands=5)
    assert json.dumps(a.summary(), sort_keys=True) == json.dumps(b.summary(), sort_keys=True)


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
