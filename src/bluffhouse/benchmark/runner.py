"""The benchmark runner: duplicate poker for language models.

Entrants rotate through anonymized seats (P1..Pn) across R rotations of the
SAME seeded game — every rotation deals identical cards to identical seats,
so every entrant eventually holds every hand from every position. Seat
labels anonymize the models: prompts never reveal who is who, only the
bench records the mapping.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bluffhouse.agents.base import Agent
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.models import TableConfig

AgentBuilder = Callable[[str, str, int], Agent]  # (spec, seat_id, seed) -> Agent


@dataclass
class BenchmarkResult:
    seed: int
    num_hands: int
    mode: int
    entrants: list[str]  # unique labels, e.g. "anthropic:claude-opus-4-8#0"
    seatings: list[dict[str, str]]  # per rotation: seat -> entrant label
    scorecards: dict[str, dict]
    rotations: list[GameResult] = field(repr=False, default_factory=list)

    def table(self) -> str:
        """The scorecard as a printable table, best adjusted chips first."""
        dims = ["poker", "detection", "information_control", "cover", "discipline"]
        head = ["entrant", "adj chips", "raw"] + [d.replace("_", " ")[:12] for d in dims]
        rows = [head]
        ranked = sorted(
            self.scorecards.items(), key=lambda kv: -kv[1]["adjusted_chips"]
        )
        for entrant, card in ranked:
            rows.append(
                [entrant, f"{card['adjusted_chips']:+.1f}", f"{card['raw_chips']:+d}"]
                + [str(card["dimensions"][d]) for d in dims]
            )
        widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
        lines = []
        for i, row in enumerate(rows):
            lines.append("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)))
            if i == 0:
                lines.append("  ".join("-" * w for w in widths))
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "seed": self.seed,
            "num_hands": self.num_hands,
            "mode": self.mode,
            "entrants": self.entrants,
            "seatings": self.seatings,
            "scorecards": self.scorecards,
        }

    def write(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "bench.json").write_text(json.dumps(self.summary(), indent=2) + "\n")
        for r, result in enumerate(self.rotations):
            result.write(out / f"rotation-{r}")
        return out


def run_benchmark(
    specs: list[str],
    builder: AgentBuilder,
    seed: int = 42,
    num_hands: int = 20,
    mode: int = 0,
    rotations: int | None = None,
    small_blind: int = 5,
    big_blind: int = 10,
    starting_stack: int = 1000,
) -> BenchmarkResult:
    """Play `rotations` copies of the same seeded game (default: one per
    entrant, so everyone sits everywhere once). Agents are built FRESH per
    rotation — no memory carries across rotations."""
    from bluffhouse.benchmark.scoring import build_scorecards

    n = len(specs)
    if n < 2:
        raise ValueError("a benchmark needs at least two entrants")
    labels = [f"{spec}#{i}" for i, spec in enumerate(specs)]
    seats = [f"P{i + 1}" for i in range(n)]
    total_rotations = n if rotations is None else rotations

    results: list[GameResult] = []
    seatings: list[dict[str, str]] = []
    for rotation in range(total_rotations):
        seating = {
            seats[(e + rotation) % n]: labels[e] for e in range(n)
        }
        agents = []
        for seat in seats:
            entrant = seating[seat]
            spec = specs[labels.index(entrant)]
            agents.append(builder(spec, seat, seed))
        config = TableConfig(
            seed=seed,
            num_hands=num_hands,
            small_blind=small_blind,
            big_blind=big_blind,
            starting_stack=starting_stack,
            agent_ids=seats,
            mode=mode,
        )
        results.append(GameHarness(config, agents).run())
        seatings.append(seating)

    paired = list(zip(results, seatings))
    return BenchmarkResult(
        seed=seed,
        num_hands=num_hands,
        mode=mode,
        entrants=labels,
        seatings=seatings,
        scorecards=build_scorecards(paired),
        rotations=results,
    )
