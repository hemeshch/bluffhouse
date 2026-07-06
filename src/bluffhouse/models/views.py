from pydantic import BaseModel

from bluffhouse.models.actions import LegalActions
from bluffhouse.models.events import Street
from bluffhouse.models.observations import Observation


class SeatView(BaseModel):
    agent_id: str
    seat: int  # position in this hand's action order; 0 = small blind
    stack: int
    bet: int  # chips committed on the current street
    folded: bool
    all_in: bool


class TableView(BaseModel):
    """The public poker state — identical for every agent at the table."""

    hand_no: int
    street: Street | None
    board: tuple[str, ...]
    pot: int
    button: str
    small_blind: int
    big_blind: int
    seats: list[SeatView]
    to_act: str | None


class AgentView(BaseModel):
    """Everything one agent gets when asked to act or speak: its private
    cards, the public table, its legal actions (None during a communication
    phase), and the observations it personally accumulated. Never the
    ground truth."""

    you: str
    hole_cards: tuple[str, str]
    table: TableView
    legal: LegalActions | None = None
    observations: list[Observation]
    mode: int = 0
