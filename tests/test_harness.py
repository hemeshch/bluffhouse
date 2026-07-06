"""Harness behavior: action repair, observation privacy, busts and rotation."""

from bluffhouse.agents import AllInBot, CheckCallBot, RandomBot
from bluffhouse.agents.base import Agent
from bluffhouse.harness import GameHarness
from bluffhouse.models import (
    ActionRepaired,
    ActionType,
    AgentView,
    GameEnded,
    HandEnded,
    HandStarted,
    HoleCardsDealt,
    PokerAction,
    TableConfig,
)


class StubAgent(Agent):
    """Plays a scripted queue of actions, then falls back to check/call."""

    def __init__(self, agent_id: str, queue: list[PokerAction] | None = None):
        super().__init__(agent_id)
        self.queue = list(queue or [])

    def act(self, view: AgentView) -> PokerAction:
        if self.queue:
            return self.queue.pop(0)
        if view.legal.can_check:
            return PokerAction(action=ActionType.CHECK)
        if view.legal.can_call:
            return PokerAction(action=ActionType.CALL)
        return PokerAction(action=ActionType.FOLD)


def test_free_fold_repaired_to_check():
    # Heads-up hand 1: B is the button/small blind and acts first preflop.
    agents = [
        StubAgent("A", [PokerAction(action=ActionType.FOLD)]),  # BB open-folds
        StubAgent("B", [PokerAction(action=ActionType.CALL)]),
    ]
    config = TableConfig(seed=1, num_hands=1, agent_ids=["A", "B"])
    result = GameHarness(config, agents).run()

    repairs = [e for e in result.log.events if isinstance(e, ActionRepaired)]
    assert len(repairs) == 1
    repair = repairs[0]
    assert repair.agent_id == "A"
    assert repair.submitted.action is ActionType.FOLD
    assert repair.applied.action is ActionType.CHECK
    assert repair.visible_to == ("A",)
    # the repair notice reached only the offending agent
    assert any(o.perceived_text.startswith("Your action 'fold'") for o in result.observations["A"])
    assert not any("was not legal" in o.perceived_text for o in result.observations["B"])


def test_illegal_raise_amount_clamped():
    agents = [
        StubAgent("A"),
        StubAgent("B"),
        StubAgent("C", [PokerAction(action=ActionType.RAISE_TO, amount=1)]),
        StubAgent("D"),
    ]
    config = TableConfig(seed=2, num_hands=1, agent_ids=["A", "B", "C", "D"])
    result = GameHarness(config, agents).run()

    repairs = [e for e in result.log.events if isinstance(e, ActionRepaired)]
    assert len(repairs) == 1
    assert repairs[0].agent_id == "C"
    assert repairs[0].applied.action is ActionType.RAISE_TO
    assert repairs[0].applied.amount == 20  # min raise over the big blind


def test_hole_cards_stay_private():
    ids = ["A", "B", "C", "D"]
    config = TableConfig(seed=5, num_hands=3, agent_ids=ids)
    result = GameHarness(config, [CheckCallBot(a) for a in ids]).run()

    events_by_id = {e.event_id: e for e in result.log.events}
    for aid in ids:
        deal_obs = [
            o for o in result.observations[aid]
            if isinstance(events_by_id[o.source_event_id], HoleCardsDealt)
        ]
        assert len(deal_obs) == 3  # one per hand, own cards only
        for obs in deal_obs:
            assert events_by_id[obs.source_event_id].agent_id == aid
            assert obs.perceived_text.startswith("You are dealt")


def test_busts_rotation_and_early_end():
    # Tiny stacks and violent bots: busts, short blinds, heads-up endgames.
    ids = ["A", "B", "C", "D"]
    for seed in (1, 2, 3):
        agents = [AllInBot("A"), CheckCallBot("B"), RandomBot("C", seed), RandomBot("D", seed)]
        config = TableConfig(seed=seed, num_hands=60, starting_stack=150, agent_ids=ids)
        result = GameHarness(config, agents).run()

        total = 4 * 150
        assert sum(result.final_stacks.values()) == total
        for event in result.log.events:
            if isinstance(event, HandStarted):
                assert all(v > 0 for v in event.stacks.values()), "busted player was dealt in"
            if isinstance(event, HandEnded):
                assert sum(event.stacks.values()) == total
        ended = [e for e in result.log.events if isinstance(e, GameEnded)]
        assert len(ended) == 1
        alive = sum(1 for v in result.final_stacks.values() if v > 0)
        if ended[0].hands_played < 60:
            assert alive == 1, "game stopped early but more than one player remains"
