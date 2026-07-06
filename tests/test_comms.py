"""Modes 1–2: table talk, whispers, privacy, and rule enforcement."""

from bluffhouse.agents import CheckCallBot, LLMAgent
from bluffhouse.harness import GameHarness
from bluffhouse.llm import MockClient
from bluffhouse.models import (
    AgentView,
    CommunicationAction,
    MessageRejected,
    MessageSent,
    Modality,
    TableConfig,
    Visibility,
)


class Talker(CheckCallBot):
    """Check-call bot with a scripted mouth: speaks per (hand, street)."""

    def __init__(self, agent_id: str, script: dict | None = None):
        super().__init__(agent_id)
        self.script = dict(script or {})
        self.comm_phases_seen = 0

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        self.comm_phases_seen += 1
        return self.script.pop((view.table.hand_no, view.table.street), None)


def speech(sender, text, intent=""):
    return CommunicationAction(
        sender=sender, target="all", modality=Modality.SPEECH,
        content=intent, surface_form=text,
    )


def whisper(sender, to, text, intent=""):
    return CommunicationAction(
        sender=sender, target=to, modality=Modality.WHISPER,
        content=intent, surface_form=text,
    )


def run(agents, mode, hands=1, seed=3):
    config = TableConfig(
        seed=seed, num_hands=hands, agent_ids=[a.id for a in agents], mode=mode
    )
    return GameHarness(config, agents).run()


def events_of(result, cls):
    return [e for e in result.log.events if isinstance(e, cls)]


def texts(result, aid):
    return [o.perceived_text for o in result.observations[aid]]


def test_mode0_never_asks_anyone_to_talk():
    agents = [Talker("A"), Talker("B"), Talker("C")]
    run(agents, mode=0)
    assert all(a.comm_phases_seen == 0 for a in agents)


def test_mode1_speech_reaches_everyone():
    agents = [
        Talker("A", {(1, "preflop"): speech("A", "I never bluff.", intent="setting up a later bluff")}),
        Talker("B"), Talker("C"),
    ]
    result = run(agents, mode=1)

    sent = events_of(result, MessageSent)
    assert len(sent) == 1
    msg = sent[0]
    assert msg.modality == "speech" and msg.street == "preflop"
    assert all(r.outcome == "clear" for r in msg.receptions.values())
    assert msg.intent == "setting up a later bluff"

    assert 'A says: "I never bluff."' in texts(result, "B")
    assert 'A says: "I never bluff."' in texts(result, "C")
    assert 'You say: "I never bluff."' in texts(result, "A")


def test_mode2_whisper_reaches_only_target():
    agents = [
        Talker("A", {(1, "preflop"): whisper("A", ["B"], "fold and I'll split it with you")}),
        Talker("B"), Talker("C"),
    ]
    result = run(agents, mode=2)

    msg = events_of(result, MessageSent)[0]
    assert msg.modality == "whisper"
    assert msg.visibility is Visibility.ENV  # receptions, not visibility, gate access
    assert msg.receptions["A"].outcome == "clear"  # sender
    assert msg.receptions["B"].outcome == "clear"  # target
    assert msg.receptions["C"].outcome == "missed"  # mode 2: no interception

    assert 'A whispers to you: "fold and I\'ll split it with you"' in texts(result, "B")
    assert 'You whisper to B: "fold and I\'ll split it with you"' in texts(result, "A")
    assert not any("split it with you" in t for t in texts(result, "C"))


def test_mode1_whisper_dropped_not_broadcast():
    agents = [
        Talker("A", {(1, "preflop"): whisper("A", ["B"], "psst — you and me?")}),
        Talker("B"), Talker("C"),
    ]
    result = run(agents, mode=1)

    assert events_of(result, MessageSent) == []
    rejected = events_of(result, MessageRejected)
    assert len(rejected) == 1 and rejected[0].visible_to == ("A",)
    assert any(t.startswith("Your message was not delivered") for t in texts(result, "A"))
    # crucially: the failed whisper leaked to nobody
    assert not any("psst" in t for t in texts(result, "B") + texts(result, "C"))


def test_whisper_to_nonsense_target_rejected():
    agents = [
        Talker("A", {(1, "preflop"): whisper("A", ["Z", "A"], "hello?")}),
        Talker("B"),
    ]
    result = run(agents, mode=2)
    assert events_of(result, MessageSent) == []
    assert len(events_of(result, MessageRejected)) == 1


def test_intent_never_reaches_observations():
    secret = "intent-marker-a9f3"
    agents = [
        Talker("A", {(1, "preflop"): whisper("A", ["B"], "nice pot", intent=secret)}),
        Talker("B"), Talker("C"),
    ]
    result = run(agents, mode=2)
    assert events_of(result, MessageSent)[0].intent == secret  # ground truth keeps it
    for aid in ("A", "B", "C"):
        assert not any(secret in t for t in texts(result, aid))


def test_comm_phase_runs_once_per_street_and_determinism_holds():
    def make():
        return [
            Talker("A", {(1, "preflop"): speech("A", "morning all"), (1, "flop"): speech("A", "nice flop")}),
            Talker("B"), Talker("C"),
        ]
    r1, r2 = run(make(), mode=1, hands=2, seed=11), run(make(), mode=1, hands=2, seed=11)
    assert r1.log.to_jsonl() == r2.log.to_jsonl()
    streets = [e.street for e in events_of(r1, MessageSent)]
    assert streets == ["preflop", "flop"]


def test_llm_agent_talks_and_stays_silent():
    def reply(req):
        prompt = req.messages[-1]["content"]
        if "Table talk" in prompt:
            if "preflop" in prompt and "Hand 1" in prompt:
                return '{"message": "big cards coming, careful", "channel": "speech", "intent": "seed doubt"}'
            return '{"message": null}'
        return '{"action": "call"}' if "call (" in prompt else '{"action": "check"}'

    llm = LLMAgent("A", MockClient(fallback=reply))
    result = run([llm, CheckCallBot("B")], mode=1, hands=1, seed=5)

    sent = events_of(result, MessageSent)
    assert [(m.sender, m.text, m.intent) for m in sent] == [("A", "big cards coming, careful", "seed doubt")]
    comm_calls = [c for c in llm.transcript if c.phase == "comm"]
    assert len(comm_calls) >= 1
    assert all(c.parse_error is None for c in comm_calls)
    # comm decisions must not disturb the reasoning↔action mapping
    action_calls = [c for c in llm.transcript if c.phase == "action"]
    assert len({c.decision_id for c in action_calls} & {c.decision_id for c in comm_calls}) == 0
