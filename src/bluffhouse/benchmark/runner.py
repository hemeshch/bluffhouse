"""The benchmark runner: duplicate poker for language models.

Entrants rotate through anonymized seats (P1..Pn) across R rotations of the
SAME seeded game — every rotation deals identical cards to identical seats,
so every entrant eventually holds every hand from every position. Seat
labels anonymize the models: prompts never reveal who is who, only the
bench records the mapping.
"""

import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bluffhouse.agents.base import Agent
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.models import TableConfig

AgentBuilder = Callable[[str, str, int], Agent]  # (spec, seat_id, seed) -> Agent


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    weight = idx - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def _bootstrap_ci(
    values: list[float],
    *,
    iterations: int = 1000,
    seed: int = 0,
) -> tuple[float, float]:
    if len(values) <= 1:
        point = values[0] if values else 0.0
        return point, point
    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(_mean(sample))
    return _percentile(means, 0.025), _percentile(means, 0.975)


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
        dims = [
            "poker",
            "poker_quality",
            "belief_accuracy",
            "detection",
            "information_control",
            "cover",
            "discipline",
        ]
        present = set().union(
            *(card["dimensions"].keys() for card in self.scorecards.values())
        )
        dims += [d for d in ("deception", "manipulation") if d in present]
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
        (out / "bench.json").write_text(
            json.dumps(self.summary(), indent=2) + "\n",
            encoding="utf-8",
        )
        for r, result in enumerate(self.rotations):
            result.write(out / f"rotation-{r}")
        return out

    @classmethod
    def read(cls, bench_dir: str | Path) -> "BenchmarkResult":
        out = Path(bench_dir)
        summary = json.loads((out / "bench.json").read_text(encoding="utf-8"))
        rotations = []
        for r in range(len(summary["seatings"])):
            run_json = out / f"rotation-{r}" / "run.json"
            if run_json.exists():
                rotations.append(GameResult.read(run_json.parent))
        return cls(
            seed=summary["seed"],
            num_hands=summary["num_hands"],
            mode=summary["mode"],
            entrants=summary["entrants"],
            seatings=summary["seatings"],
            scorecards=summary["scorecards"],
            rotations=rotations,
        )


def _seating_for(labels: list[str], seats: list[str], rotation: int) -> dict[str, str]:
    n = len(labels)
    return {seats[(e + rotation) % n]: labels[e] for e in range(n)}


def _run_rotation(
    rotation: int,
    specs: list[str],
    labels: list[str],
    seats: list[str],
    builder: AgentBuilder,
    seed: int,
    num_hands: int,
    mode: int,
    small_blind: int,
    big_blind: int,
    starting_stack: int,
    out_dir: Path | None,
) -> tuple[int, GameResult, dict[str, str]]:
    seating = _seating_for(labels, seats, rotation)
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
    result = GameHarness(config, agents).run()
    if out_dir is not None:
        result.write(out_dir / f"rotation-{rotation}")
    return rotation, result, seating


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
    parallel: int | None = None,
    out_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
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

    checkpoint_dir = Path(out_dir) if out_dir is not None else None
    if checkpoint_dir is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
    resume_path = Path(resume_dir) if resume_dir is not None else None

    results: list[GameResult | None] = [None] * total_rotations
    seatings = [_seating_for(labels, seats, r) for r in range(total_rotations)]
    for rotation in range(total_rotations):
        base_dir = resume_path or checkpoint_dir
        run_dir = base_dir / f"rotation-{rotation}" if base_dir else None
        if run_dir is not None and (run_dir / "run.json").exists():
            results[rotation] = GameResult.read(run_dir)

    missing = [r for r, result in enumerate(results) if result is None]
    workers = len(missing) if parallel is None else parallel
    workers = max(1, min(workers, len(missing) or 1))

    def run_one(rotation: int) -> tuple[int, GameResult, dict[str, str]]:
        return _run_rotation(
            rotation=rotation,
            specs=specs,
            labels=labels,
            seats=seats,
            builder=builder,
            seed=seed,
            num_hands=num_hands,
            mode=mode,
            small_blind=small_blind,
            big_blind=big_blind,
            starting_stack=starting_stack,
            out_dir=checkpoint_dir or resume_path,
        )

    if missing and workers == 1:
        for rotation in missing:
            r, result, seating = run_one(rotation)
            results[r] = result
            seatings[r] = seating
    elif missing:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_one, rotation) for rotation in missing]
            for future in as_completed(futures):
                r, result, seating = future.result()
                results[r] = result
                seatings[r] = seating

    completed = [result for result in results if result is not None]
    if len(completed) != total_rotations:
        raise RuntimeError("benchmark finished with missing rotations")

    paired = list(zip(completed, seatings))
    bench = BenchmarkResult(
        seed=seed,
        num_hands=num_hands,
        mode=mode,
        entrants=labels,
        seatings=seatings,
        scorecards=build_scorecards(paired),
        rotations=completed,
    )
    if checkpoint_dir is not None or resume_path is not None:
        out = checkpoint_dir or resume_path
        assert out is not None
        (out / "bench.json").write_text(
            json.dumps(bench.summary(), indent=2) + "\n",
            encoding="utf-8",
        )
    return bench


@dataclass
class BenchmarkSweepResult:
    seeds: list[int]
    num_hands: int
    mode: int
    entrants: list[str]
    benches: list[BenchmarkResult] = field(repr=False)
    leaderboard: dict[str, dict]
    win_rate_matrix: dict[str, dict[str, float]]

    def table(self) -> str:
        head = ["entrant", "mean adj", "95% CI", "seed wins"]
        rows = [head]
        ranked = sorted(
            self.leaderboard.items(),
            key=lambda kv: -kv[1]["mean_adjusted_chips"],
        )
        for entrant, row in ranked:
            lo, hi = row["ci95"]
            rows.append([
                entrant,
                f"{row['mean_adjusted_chips']:+.1f}",
                f"[{lo:+.1f}, {hi:+.1f}]",
                str(row["seed_wins"]),
            ])
        widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
        lines = []
        for i, row in enumerate(rows):
            lines.append("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)))
            if i == 0:
                lines.append("  ".join("-" * w for w in widths))
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "seeds": self.seeds,
            "num_hands": self.num_hands,
            "mode": self.mode,
            "rotations": len(self.benches[0].seatings) if self.benches else 0,
            "entrants": self.entrants,
            "leaderboard": self.leaderboard,
            "win_rate_matrix": self.win_rate_matrix,
            "bench_dirs": [f"seed-{bench.seed}" for bench in self.benches],
        }

    def write(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "leaderboard.json").write_text(
            json.dumps(self.summary(), indent=2) + "\n",
            encoding="utf-8",
        )
        return out


def _aggregate_benches(
    benches: list[BenchmarkResult],
    *,
    bootstrap_iterations: int = 1000,
) -> tuple[dict[str, dict], dict[str, dict[str, float]]]:
    entrants = benches[0].entrants
    per_entrant = {
        entrant: [
            float(bench.scorecards[entrant]["adjusted_chips"])
            for bench in benches
        ]
        for entrant in entrants
    }
    seed_wins = {entrant: 0 for entrant in entrants}
    for bench in benches:
        best = max(card["adjusted_chips"] for card in bench.scorecards.values())
        winners = [
            entrant for entrant, card in bench.scorecards.items()
            if card["adjusted_chips"] == best
        ]
        for entrant in winners:
            seed_wins[entrant] += 1 / len(winners)

    leaderboard = {}
    for i, entrant in enumerate(entrants):
        values = per_entrant[entrant]
        ci = _bootstrap_ci(
            values,
            iterations=bootstrap_iterations,
            seed=10_000 + i,
        )
        leaderboard[entrant] = {
            "mean_adjusted_chips": round(_mean(values), 4),
            "ci95": [round(ci[0], 4), round(ci[1], 4)],
            "seed_wins": round(seed_wins[entrant], 4),
            "per_seed_adjusted_chips": [
                round(value, 4) for value in values
            ],
        }

    matrix: dict[str, dict[str, float]] = {}
    for a in entrants:
        matrix[a] = {}
        for b in entrants:
            if a == b:
                matrix[a][b] = 0.5
                continue
            score = 0.0
            for bench in benches:
                av = bench.scorecards[a]["adjusted_chips"]
                bv = bench.scorecards[b]["adjusted_chips"]
                score += 1.0 if av > bv else (0.5 if av == bv else 0.0)
            matrix[a][b] = round(score / len(benches), 4)
    return leaderboard, matrix


def run_benchmark_sweep(
    specs: list[str],
    builder: AgentBuilder,
    seeds: list[int],
    num_hands: int = 20,
    mode: int = 0,
    rotations: int | None = None,
    small_blind: int = 5,
    big_blind: int = 10,
    starting_stack: int = 1000,
    parallel: int | None = None,
    out_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
    bootstrap_iterations: int = 1000,
) -> BenchmarkSweepResult:
    if not seeds:
        raise ValueError("a benchmark sweep needs at least one seed")
    base_dir = Path(out_dir) if out_dir is not None else None
    resume_base = Path(resume_dir) if resume_dir is not None else None
    if base_dir is not None:
        base_dir.mkdir(parents=True, exist_ok=True)

    benches = []
    for seed in seeds:
        output_base = base_dir or resume_base
        seed_dir = output_base / f"seed-{seed}" if output_base else None
        bench = run_benchmark(
            specs,
            builder,
            seed=seed,
            num_hands=num_hands,
            mode=mode,
            rotations=rotations,
            small_blind=small_blind,
            big_blind=big_blind,
            starting_stack=starting_stack,
            parallel=parallel,
            out_dir=seed_dir,
            resume_dir=seed_dir if resume_base is not None else None,
        )
        benches.append(bench)

    leaderboard, matrix = _aggregate_benches(
        benches,
        bootstrap_iterations=bootstrap_iterations,
    )
    sweep = BenchmarkSweepResult(
        seeds=seeds,
        num_hands=num_hands,
        mode=mode,
        entrants=benches[0].entrants,
        benches=benches,
        leaderboard=leaderboard,
        win_rate_matrix=matrix,
    )
    if base_dir is not None or resume_base is not None:
        out = base_dir or resume_base
        assert out is not None
        sweep.write(out)
    return sweep
