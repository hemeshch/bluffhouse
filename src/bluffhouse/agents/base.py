from abc import ABC, abstractmethod

from bluffhouse.models import (
    AgentView,
    AttentionPlan,
    CommunicationAction,
    Observation,
    PokerAction,
)


class Agent(ABC):
    """A player at the table.

    The harness pushes observations as they happen and, per street:
    attend() (mode 5+, before anything happens), communicate() (mode 1+,
    before betting), then act() on the agent's turns. An agent never
    touches ground truth — its entire world is the observations it received
    and the AgentView it is handed.
    """

    def __init__(self, agent_id: str):
        self.id = agent_id

    def observe(self, observation: Observation) -> None:
        """Receive one subjective observation. Default: ignore it."""

    def attend(self, view: AgentView) -> AttentionPlan | None:
        """Commit this street's attention budget before anything happens.
        Default: no plan — passive, table-wide attention."""
        return None

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        """Optional table talk before betting on each street. Default:
        stay silent."""
        return None

    @abstractmethod
    def act(self, view: AgentView) -> PokerAction: ...
