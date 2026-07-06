"""Modes 3–4: the perception resolver — interception, fragments, gestures,
and the determinism everything depends on."""

import random

from bluffhouse.agents import CheckCallBot
from bluffhouse.harness import GameHarness
from bluffhouse.models import (
    AgentView,
    CommunicationAction,
    MessageRejected,
    MessageSent,
    Modality,
    TableConfig,
)
from bluffhouse.perception import PerceptionResolver, fragment_text

OBSERVERS = ["A", "B", "C", "D"]
TEXT = "raise big on the river and I will fold to you every time"


def resolve(mode, seed=7, modality=Modality.WHISPER, targets=("B",), subtlety=0.0, hand_no=1):
    resolver = PerceptionResolver(seed, mode)
    return resolver.resolve(
        modality=modality, sender="A", targets=targets, observers=OBSERVERS,
        text=TEXT, subtlety=subtlety, hand_no=hand_no,
    )


def many(mode, n=300, **kwargs):
    """Resolve the same message across n hands; returns list of receptions."""
    resolver = PerceptionResolver(7, mode)
    out = []
    for hand in range(1, n + 1):
        out.append(resolver.resolve(
            modality=kwargs.get("modality", Modality.WHISPER),
            sender="A", targets=kwargs.get("targets", ("B",)), observers=OBSERVERS,
            text=TEXT, subtlety=kwargs.get("subtlety", 0.0), hand_no=hand,
        ))
    return out


# ── resolver unit behavior ──────────────────────────────────────────


def test_same_seed_same_outcomes():
    assert resolve(3, seed=42) == resolve(3, seed=42)
    assert many(3, 50) == many(3, 50)


def test_mode2_is_deterministic_and_leak_free():
    for receptions in many(2, 50):
        assert receptions["A"].outcome == "clear"
        assert receptions["B"].outcome == "clear"
        assert receptions["C"].outcome == "missed"
        assert receptions["D"].outcome == "missed"


def test_mode3_whispers_leak_sometimes_but_not_always():
    rolls = many(3, 300)
    intercepts = [r for rs in rolls for a, r in rs.items() if a in "CD" and r.outcome != "missed"]
    misses = [r for rs in rolls for a, r in rs.items() if a in "CD" and r.outcome == "missed"]
    assert intercepts and misses, "interception should be possible but not certain"
    # base rate 0.35: sanity-check the frequency is in a plausible band
    rate = len(intercepts) / (len(intercepts) + len(misses))
    assert 0.25 < rate < 0.45
    for r in intercepts:
        assert r.outcome == "fragment"
        assert r.confidence < 1.0
        assert r.text and "…" in r.text
        # every surviving word came from the original whisper
        assert all(w in TEXT.split() for w in r.text.replace("…", " ").split())


def test_mode3_targets_can_miss_subtle_whispers():
    clear = [rs["B"].outcome for rs in many(3, 300, subtlety=0.9)]
    assert "missed" in clear and "clear" in clear


def test_full_subtlety_kills_interception():
    for rs in many(3, 200, subtlety=1.0):
        assert rs["C"].outcome == "missed" and rs["D"].outcome == "missed"


def test_mode4_gesture_bystanders_see_surface_not_content():
    rolls = many(4, 300, modality=Modality.GESTURE, subtlety=0.2)
    noticed = [r for rs in rolls for a, r in rs.items() if a in "CD" and r.outcome != "missed"]
    assert noticed
    for r in noticed:
        assert r.outcome == "surface"
        assert r.text is None  # nothing textual leaks; observers see event surface only
        assert r.confidence < 1.0


def test_fragment_text_is_deterministic_and_partial():
    a = fragment_text(TEXT, random.Random(5))
    b = fragment_text(TEXT, random.Random(5))
    assert a == b and "…" in a
    assert len(a.replace("…", " ").split()) >= 1
    assert fragment_text("fold now", random.Random(1)) == "…fold now…"


# ── integration through the harness ─────────────────────────────────


class Whisperer(CheckCallBot):
    """Whispers the same secret to B on every preflop."""

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        if view.you == "A" and view.table.street == "preflop":
            return CommunicationAction(
                sender="A", target=["B"], modality=Modality.WHISPER,
                content="coordinate against C", surface_form=TEXT,
            )
        return None


def run_game(mode, hands=30, seed=19):
    agents = [Whisperer("A"), CheckCallBot("B"), CheckCallBot("C")]
    config = TableConfig(seed=seed, num_hands=hands, agent_ids=["A", "B", "C"], mode=mode)
    return GameHarness(config, agents).run()


def test_interception_reaches_the_bystander_as_a_fragment():
    result = run_game(mode=3)
    fragments = [
        o for o in result.observations["C"]
        if o.kind == "message_sent" and "All you catch" in o.perceived_text
    ]
    assert fragments, "30 whispers at base rate 0.35 should leak at least once"
    for obs in fragments:
        assert obs.confidence < 1.0
        assert "You overhear A whispering to B" in obs.perceived_text
        assert TEXT not in obs.perceived_text  # never the full text
        assert "coordinate against C" not in obs.perceived_text  # never the intent
    # ...and the log's ground truth agrees observation-for-observation
    fragment_events = [
        e for e in result.log.events
        if isinstance(e, MessageSent) and e.receptions["C"].outcome == "fragment"
    ]
    assert len(fragment_events) == len(fragments)


def test_gestures_rejected_below_mode_4():
    class Signaler(CheckCallBot):
        def communicate(self, view):
            if view.you == "A" and view.table.hand_no == 1 and view.table.street == "preflop":
                return CommunicationAction(
                    sender="A", target=["B"], modality=Modality.GESTURE,
                    content="raise now", surface_form="taps chips twice",
                )
            return None

    agents = [Signaler("A"), CheckCallBot("B"), CheckCallBot("C")]
    config = TableConfig(seed=2, num_hands=1, agent_ids=["A", "B", "C"], mode=3)
    result = GameHarness(config, agents).run()
    assert not [e for e in result.log.events if isinstance(e, MessageSent)]
    rejects = [e for e in result.log.events if isinstance(e, MessageRejected)]
    assert len(rejects) == 1 and "not available" in rejects[0].reason


def test_gesture_target_sees_surface_form_only():
    class Signaler(CheckCallBot):
        def communicate(self, view):
            if view.you == "A" and view.table.hand_no == 1 and view.table.street == "preflop":
                return CommunicationAction(
                    sender="A", target=["B"], modality=Modality.GESTURE,
                    content="the code from earlier: raise now", surface_form="taps chips twice",
                )
            return None

    agents = [Signaler("A"), CheckCallBot("B"), CheckCallBot("C")]
    config = TableConfig(seed=6, num_hands=1, agent_ids=["A", "B", "C"], mode=4)
    result = GameHarness(config, agents).run()
    msg = [e for e in result.log.events if isinstance(e, MessageSent)][0]
    assert msg.modality == "gesture" and msg.intent == "the code from earlier: raise now"
    if msg.receptions["B"].outcome == "clear":
        got = [o for o in result.observations["B"] if o.kind == "message_sent"]
        assert 'A makes a quiet signal at you: "taps chips twice"' in got[0].perceived_text
    for aid in ("B", "C"):
        assert not any("raise now" in o.perceived_text for o in result.observations[aid])


def test_mode3_game_is_deterministic():
    assert run_game(3, hands=10).log.to_jsonl() == run_game(3, hands=10).log.to_jsonl()
