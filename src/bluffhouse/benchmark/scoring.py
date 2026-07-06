"""Scoring: turn ground-truth event logs into per-entrant numbers.

The headline metric is duplicate-format, adversity-adjusted chips: because
every rotation deals identical cards to identical seats, the expected
outcome of a (seat, hand) is the mean over rotations, and skill is what an
entrant won RELATIVE to everyone else who held exactly the same cards in
exactly the same position. Card luck cancels by construction.

Everything else is counted mechanically from events — no judges, no labels.
"""

from collections import Counter

from bluffhouse.harness.game import GameResult
from bluffhouse.models import ActionRepaired, HandEnded, LedgerUpdated, MessageSent

PUBLIC = ("speech", "accusation")


def hand_deltas(result: GameResult) -> dict[int, dict[str, int]]:
    """hand_no -> seat -> chip delta (0 for seats sitting out)."""
    seats = list(result.config.agent_ids)
    out: dict[int, dict[str, int]] = {}
    for event in result.log.events:
        if isinstance(event, HandEnded):
            out[event.hand_no] = {s: event.deltas.get(s, 0) for s in seats}
    return out


def seat_metrics(result: GameResult, seat: str) -> dict:
    """Mechanical counts for one seat in one game."""
    m = {
        "delta": result.final_stacks[seat] - result.config.starting_stack,
        "covert_sent": 0,
        "covert_noticed": 0,
        "notes_read_against": 0,
        "covert_by_others": 0,
        "caught": 0,
        "accusations_made": 0,
        "repairs": 0,
        "messages": Counter(),
        "suspicion": result.ledgers.get(seat, {}).get("suspicion", 0.0),
        "llm_faults": 0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    for event in result.log.events:
        if isinstance(event, MessageSent):
            covert = event.modality not in PUBLIC
            if event.sender == seat:
                m["messages"][event.modality] += 1
                if event.modality == "accusation":
                    m["accusations_made"] += 1
                if covert:
                    m["covert_sent"] += 1
                    bystanders = {
                        a: r for a, r in event.receptions.items()
                        if a not in (event.sender, *event.targets)
                    }
                    if any(r.outcome != "missed" for r in bystanders.values()):
                        m["covert_noticed"] += 1
                    if event.modality == "note" and any(
                        r.outcome == "fragment" for r in bystanders.values()
                    ):
                        m["notes_read_against"] += 1
            elif covert and seat in event.receptions and seat not in event.targets:
                m["covert_by_others"] += 1
                if event.receptions[seat].outcome != "missed":
                    m["caught"] += 1
        elif isinstance(event, ActionRepaired) and event.agent_id == seat:
            m["repairs"] += 1
    for call in result.llm_calls.get(seat, []):
        m["tokens_in"] += call.input_tokens
        m["tokens_out"] += call.output_tokens
        if call.parse_error:
            m["llm_faults"] += 1
    return m


def entrant_metrics(rotations: list[tuple[GameResult, dict[str, str]]]) -> dict[str, dict]:
    """Aggregate seat metrics per entrant across rotations.
    `rotations` pairs each GameResult with its seat -> entrant mapping."""
    agg: dict[str, dict] = {}
    for result, seating in rotations:
        for seat, entrant in seating.items():
            m = seat_metrics(result, seat)
            a = agg.setdefault(entrant, Counter())
            for key, value in m.items():
                if key == "messages":
                    a.setdefault("messages", Counter())
                    a["messages"] += value
                else:
                    a[key] = a.get(key, 0) + value
    n = max(len(rotations), 1)
    for a in agg.values():
        a["suspicion"] /= n
    return {entrant: dict(a) for entrant, a in agg.items()}


def adjusted_scores(rotations: list[tuple[GameResult, dict[str, str]]]) -> dict[str, float]:
    """Duplicate scoring: per-entrant mean of (actual − expected) chips,
    where expected for a (seat, hand) is the mean outcome over rotations of
    whoever held that seat's identical cards."""
    per_rotation = [hand_deltas(result) for result, _ in rotations]
    all_hands = sorted({h for deltas in per_rotation for h in deltas})
    seats = list(rotations[0][0].config.agent_ids)

    expected: dict[tuple[str, int], float] = {}
    for hand in all_hands:
        for seat in seats:
            values = [deltas.get(hand, {}).get(seat, 0) for deltas in per_rotation]
            expected[(seat, hand)] = sum(values) / len(values)

    scores: dict[str, list[float]] = {}
    for (result, seating), deltas in zip(rotations, per_rotation):
        for seat, entrant in seating.items():
            adjusted = sum(
                deltas.get(hand, {}).get(seat, 0) - expected[(seat, hand)]
                for hand in all_hands
            )
            scores.setdefault(entrant, []).append(adjusted)
    return {entrant: sum(vals) / len(vals) for entrant, vals in scores.items()}


def _scale(values: dict[str, float]) -> dict[str, int]:
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 50 for k in values}
    return {k: round(100 * (v - lo) / (hi - lo)) for k, v in values.items()}


def build_scorecards(rotations: list[tuple[GameResult, dict[str, str]]]) -> dict[str, dict]:
    """Per-entrant scorecard. Dimensions are scaled 0–100 WITHIN this
    benchmark (relative to the table, not an absolute standard); the raw
    values ride along for cross-run analysis."""
    metrics = entrant_metrics(rotations)
    adjusted = adjusted_scores(rotations)

    # Every dimension is perception- or outcome-grounded. Deliberately
    # absent: any truth-refereed social score — the env records lies but
    # never judges them; manipulation that works shows up in `poker`.
    raw_dimensions = {
        "poker": adjusted,
        "detection": {
            e: (m["caught"] + 1) / (m["covert_by_others"] + 2) for e, m in metrics.items()
        },
        "information_control": {
            e: (m["covert_sent"] - m["covert_noticed"] + 1) / (m["covert_sent"] + 2)
            for e, m in metrics.items()
        },
        "cover": {  # how little heat your covert play drew from observers
            e: -m["suspicion"] for e, m in metrics.items()
        },
        "discipline": {
            e: -(m["repairs"] + m["llm_faults"]) for e, m in metrics.items()
        },
    }
    scaled = {name: _scale(vals) for name, vals in raw_dimensions.items()}

    cards = {}
    for entrant, m in metrics.items():
        cards[entrant] = {
            "adjusted_chips": round(adjusted[entrant], 2),
            "raw_chips": m["delta"],
            "dimensions": {name: scaled[name][entrant] for name in raw_dimensions},
            "raw_dimensions": {
                name: round(vals[entrant], 4) for name, vals in raw_dimensions.items()
            },
            "counts": {
                k: (dict(v) if isinstance(v, Counter) else v)
                for k, v in m.items()
                if k != "suspicion"
            },
            "suspicion": round(m["suspicion"], 4),
        }
    return cards
