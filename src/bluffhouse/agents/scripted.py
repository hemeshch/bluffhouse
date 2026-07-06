"""Deterministic scripted bots: the control conditions and soak-testers.
They keep the whole harness testable without spending a single token."""

import random

from bluffhouse.agents.base import Agent
from bluffhouse.engine.deck import derive_seed
from bluffhouse.models import ActionType, AgentView, LegalActions, PokerAction

_FOLD = PokerAction(action=ActionType.FOLD)
_CHECK = PokerAction(action=ActionType.CHECK)
_CALL = PokerAction(action=ActionType.CALL)


class FoldBot(Agent):
    """Checks when free, otherwise folds."""

    def act(self, view: AgentView) -> PokerAction:
        return _CHECK if view.legal.can_check else _FOLD


class CheckCallBot(Agent):
    """Never folds, never raises."""

    def act(self, view: AgentView) -> PokerAction:
        if view.legal.can_check:
            return _CHECK
        if view.legal.can_call:
            return _CALL
        return _FOLD


class AllInBot(Agent):
    """Shoves at every opportunity. Exists to stress all-ins and side pots."""

    def act(self, view: AgentView) -> PokerAction:
        legal = view.legal
        if legal.can_raise:
            return PokerAction(action=ActionType.RAISE_TO, amount=legal.max_raise_to)
        if legal.can_call:
            return _CALL
        return _CHECK if legal.can_check else _FOLD


class RandomBot(Agent):
    """Seeded random legal play, biased toward small raises. Deterministic
    given (seed, agent_id), which is what makes whole-game replay exact."""

    def __init__(self, agent_id: str, seed: int):
        super().__init__(agent_id)
        self._rng = random.Random(derive_seed(seed, "bot", agent_id))

    def act(self, view: AgentView) -> PokerAction:
        legal = view.legal
        roll = self._rng.random()
        if legal.can_check:
            if legal.can_raise and roll < 0.25:
                return self._raise(legal)
            return _CHECK
        if roll < 0.35:
            return _FOLD
        if legal.can_raise and roll > 0.85:
            return self._raise(legal)
        if legal.can_call:
            return _CALL
        return _FOLD

    def _raise(self, legal: LegalActions) -> PokerAction:
        assert legal.min_raise_to is not None and legal.max_raise_to is not None
        span = legal.max_raise_to - legal.min_raise_to
        # cube the roll to favour small raises; the tail still shoves
        amount = legal.min_raise_to + int(span * self._rng.random() ** 3)
        return PokerAction(action=ActionType.RAISE_TO, amount=amount)
