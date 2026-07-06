"""Mode 5: the attention economy — committed budgets steering perception."""

from bluffhouse.agents import CheckCallBot
from bluffhouse.agents.base import Agent
from bluffhouse.harness import GameHarness
from bluffhouse.models import (
    AgentView,
    AttentionCommitted,
    AttentionPlan,
    CommunicationAction,
    Modality,
    TableConfig,
)
from bluffhouse.perception import PerceptionResolver

OBSERVERS = ["A", "B", "C", "D"]
TEXT = "check the river to me and I will show you why"


def rates(mode, attention, n=400, subtlety=0.0):
    """Fraction of resolutions where C notices A's whisper to B."""
    resolver = PerceptionResolver(11, mode)
    noticed = 0
    for hand in range(1, n + 1):
        receptions = resolver.resolve(
            modality=Modality.WHISPER, sender="A", targets=("B",), observers=OBSERVERS,
            text=TEXT, subtlety=subtlety, hand_no=hand, attention=attention,
        )
        if receptions["C"].outcome != "missed":
            noticed += 1
    return noticed / n


def plan(watch=None, table=None):
    watch = watch or {}
    if table is None:
        table = 1.0 - sum(watch.values())
    return AttentionPlan(watch_players=watch, track_table=table)


def test_watching_the_whisperer_beats_watching_nothing():
    passive = rates(5, {"C": plan()})                       # all attention on the table
    focused = rates(5, {"C": plan({"A": 0.8}, 0.2)})        # locked onto the sender
    elsewhere = rates(5, {"C": plan({"D": 0.9}, 0.1)})      # watching the wrong player
    assert focused > passive * 1.5
    # watching the wrong corner of the room costs you the whisper most of the time
    assert elsewhere < passive < focused
    assert elsewhere < 0.2


def test_watching_the_recipient_helps_too():
    passive = rates(5, {"C": plan()})
    on_target = rates(5, {"C": plan({"B": 0.9}, 0.1)})
    assert on_target > passive


def test_attention_rescues_subtle_signals_aimed_at_you():
    resolver_blind = PerceptionResolver(13, 5)
    resolver_watch = PerceptionResolver(13, 5)
    got_blind = got_watch = 0
    n = 400
    for hand in range(1, n + 1):
        kwargs = dict(
            modality=Modality.GESTURE, sender="A", targets=("B",), observers=OBSERVERS,
            text="scratches ear", subtlety=0.8, hand_no=hand,
        )
        if resolver_blind.resolve(**kwargs, attention={"B": plan()})["B"].outcome == "clear":
            got_blind += 1
        if resolver_watch.resolve(**kwargs, attention={"B": plan({"A": 0.9}, 0.1)})["B"].outcome == "clear":
            got_watch += 1
    assert got_watch > got_blind * 1.3


def test_mode4_ignores_attention():
    with_plan = rates(4, {"C": plan({"A": 0.9}, 0.1)})
    without = rates(4, None)
    assert with_plan == without  # attention only exists from mode 5


class Watcher(CheckCallBot):
    """Commits a fixed (possibly malformed) plan every street."""

    def __init__(self, agent_id, raw_plan):
        super().__init__(agent_id)
        self.raw_plan = raw_plan
        self.attend_calls = 0

    def attend(self, view: AgentView) -> AttentionPlan | None:
        self.attend_calls += 1
        return self.raw_plan


def run_game(agents, mode, hands=2, seed=9):
    config = TableConfig(seed=seed, num_hands=hands, agent_ids=[a.id for a in agents], mode=mode)
    return GameHarness(config, agents).run()


def test_attend_called_per_street_only_in_mode5():
    agents = [Watcher("A", None), Watcher("B", None), Watcher("C", None)]
    run_game(agents, mode=4)
    assert all(a.attend_calls == 0 for a in agents)

    agents = [Watcher("A", None), Watcher("B", None), Watcher("C", None)]
    result = run_game(agents, mode=5)
    committed = [e for e in result.log.events if isinstance(e, AttentionCommitted)]
    assert agents[0].attend_calls > 0
    assert len(committed) == sum(a.attend_calls for a in agents)
    # private: only the committing agent observes its own plan
    for event in committed:
        assert event.visible_to == (event.agent_id,)
    own = [o for o in result.observations["A"] if o.kind == "attention_committed"]
    assert own and all("your attention" in o.perceived_text for o in own)
    assert not any(
        o.kind == "attention_committed" and "B" == o.observer and "A" in o.perceived_text
        for o in result.observations["B"]
    )


def test_malformed_plans_are_repaired():
    # negative weight, self-watching, unknown player, bad sum — all normalized
    raw = AttentionPlan.model_construct(
        watch_players={"A": -0.5, "B": 2.0, "ZZ": 1.0}, track_table=2.0
    )
    agents = [Watcher("A", raw), CheckCallBot("B"), CheckCallBot("C")]
    result = run_game(agents, mode=5, hands=1)
    event = next(
        e for e in result.log.events
        if isinstance(e, AttentionCommitted) and e.agent_id == "A"
    )
    assert set(event.watch) == {"B"}  # self and unknown dropped, negative gone
    assert abs(sum(event.watch.values()) + event.table - 1.0) < 1e-9


def test_mode5_deterministic():
    def make():
        return [
            Watcher("A", AttentionPlan(watch_players={"B": 0.7}, track_table=0.3)),
            CheckCallBot("B"),
            CheckCallBot("C"),
        ]
    a = run_game(make(), mode=5, hands=3, seed=17)
    b = run_game(make(), mode=5, hands=3, seed=17)
    assert a.log.to_jsonl() == b.log.to_jsonl()


class WhisperAndWatch(CheckCallBot):
    """A whispers to B every preflop; C watches A intently."""

    def attend(self, view):
        if view.you == "C":
            return AttentionPlan(watch_players={"A": 0.9}, track_table=0.1)
        return None

    def communicate(self, view):
        if view.you == "A" and view.table.street == "preflop":
            return CommunicationAction(
                sender="A", target=["B"], modality=Modality.WHISPER,
                content="collusion", surface_form=TEXT,
            )
        return None


def test_focused_watcher_intercepts_through_the_harness():
    agents = [WhisperAndWatch("A"), WhisperAndWatch("B"), WhisperAndWatch("C")]
    config = TableConfig(seed=23, num_hands=100, agent_ids=["A", "B", "C"], mode=5)
    result = GameHarness(config, agents).run()
    fragments = [
        o for o in result.observations["C"]
        if o.kind == "message_sent" and "All you catch" in o.perceived_text
    ]
    # ~0.46 notice probability per whisper while locked on (measured 39/100
    # on this seed); the point is it lands far above the passive ~0.23
    assert len(fragments) >= 30
