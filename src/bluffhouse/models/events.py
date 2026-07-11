"""The ground-truth event stream.

Every state change in a game is a typed, immutable event. The event log is
the single source of truth: agent observations, scoring, and the replay
viewer are all projections of it. Events carry a visibility marker that
mode-0 projection uses directly; later modes replace the marker with the
perception resolver for communication events.
"""

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from bluffhouse.models.actions import ActionType, PokerAction

Street = Literal["preflop", "flop", "turn", "river"]


class Visibility(str, Enum):
    PUBLIC = "public"  # every agent observes it
    PRIVATE = "private"  # only agents in visible_to observe it
    ENV = "env"  # ground-truth bookkeeping; no agent observes it


class BaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Stamped by the EventLog on emit.
    seq: int = 0
    event_id: str = ""
    hand_no: int
    visibility: Visibility = Visibility.PUBLIC
    visible_to: tuple[str, ...] = ()


class GameStarted(BaseEvent):
    type: Literal["game_started"] = "game_started"
    hand_no: int = 0
    agent_ids: tuple[str, ...]
    starting_stack: int
    small_blind: int
    big_blind: int
    num_hands: int
    mode: int


class HandStarted(BaseEvent):
    type: Literal["hand_started"] = "hand_started"
    button: str
    # Agents in action order for this hand: seat_order[0] posts the small blind.
    seat_order: tuple[str, ...]
    stacks: dict[str, int]


class BlindPosted(BaseEvent):
    type: Literal["blind_posted"] = "blind_posted"
    agent_id: str
    blind: Literal["small", "big"]
    amount: int


class HoleCardsDealt(BaseEvent):
    type: Literal["hole_cards_dealt"] = "hole_cards_dealt"
    visibility: Visibility = Visibility.PRIVATE
    agent_id: str
    cards: tuple[str, str]


class ActionTaken(BaseEvent):
    type: Literal["action_taken"] = "action_taken"
    agent_id: str
    street: Street
    action: ActionType
    # call: chips added; raise_to: total wager reached. None for fold/check.
    amount: int | None = None
    all_in: bool = False


class ActionRepaired(BaseEvent):
    """The agent submitted something illegal; the harness applied a legal
    substitute. Visible to the offending agent only — being sloppy is
    private, but it is on the record for scoring."""

    type: Literal["action_repaired"] = "action_repaired"
    visibility: Visibility = Visibility.PRIVATE
    agent_id: str
    submitted: PokerAction
    applied: PokerAction
    reason: str


class AttentionCommitted(BaseEvent):
    """An agent's attention budget for one street, committed before any
    communication happens. Private: only the committing agent observes it
    (as a reminder of where it chose to look); the weights feed the
    perception resolver's notice probabilities."""

    type: Literal["attention_committed"] = "attention_committed"
    visibility: Visibility = Visibility.PRIVATE
    agent_id: str
    street: Street
    watch: dict[str, float] = {}
    table: float = 1.0


class Reception(BaseModel):
    """One observer's ground-truth perception outcome for one message,
    rolled by the seeded resolver at emit time and recorded here so the
    event log alone reproduces every subjective world.

    clear    — received faithfully (target, or public speech)
    fragment — intercepted a corrupted piece of a whisper (`text`)
    surface  — noticed a signal's surface form but not its meaning
    missed   — never noticed it happened
    """

    model_config = ConfigDict(frozen=True)

    outcome: Literal["clear", "fragment", "surface", "missed"]
    confidence: float = 1.0
    text: str | None = None  # the corrupted fragment, when outcome=fragment


class MessageSent(BaseEvent):
    """A communication that actually happened. `text` is the surface form —
    the words said, or what a gesture looks like. `intent` is what the
    sender declared it MEANS — env-only ground truth that never reaches
    another agent; the gap between the two is how deception stays
    measurable. Who actually noticed is decided by the perception resolver
    and recorded in `receptions`, so visibility is ENV: observations are
    minted from receptions, never from the event itself."""

    type: Literal["message_sent"] = "message_sent"
    visibility: Visibility = Visibility.ENV
    sender: str
    modality: Literal[
        "speech", "whisper", "gesture", "eye_contact", "chip_signal", "note", "accusation"
    ]
    targets: tuple[str, ...] = ()  # speech: empty = the whole table; accusation: the accused
    text: str
    intent: str | None = None
    subtlety: float = 0.0
    distraction: float = 0.0  # public theater covering covert moves this street
    street: Street
    receptions: dict[str, Reception] = {}


class LedgerUpdated(BaseEvent):
    """Env-side bookkeeping of the suspicion an agent's covert actions have
    drawn — and ONLY from moments an actual observer noticed (a seen note
    pass, an intercepted whisper). The environment records social truth but
    never referees it: lies and accusations carry only the weight other
    agents give them. Pure scoring instrumentation — agents never observe
    this; their beliefs must come from what they saw."""

    type: Literal["ledger_updated"] = "ledger_updated"
    visibility: Visibility = Visibility.ENV
    agent_id: str
    suspicion: float
    delta_suspicion: float = 0.0
    reason: str


class BeliefsUpdated(BaseEvent):
    """An agent's structured private belief report for offline analysis.
    Env-only: the benchmark may score it later, but no agent observes it."""

    type: Literal["beliefs_updated"] = "beliefs_updated"
    visibility: Visibility = Visibility.ENV
    agent_id: str
    street: Street
    beliefs: dict[str, float]


class MessageRejected(BaseEvent):
    """The agent tried to communicate outside the table's rules (wrong
    channel for the mode, no target, empty message). The message is dropped
    — never downgraded to a more public channel — and only the sender
    learns why."""

    type: Literal["message_rejected"] = "message_rejected"
    visibility: Visibility = Visibility.PRIVATE
    sender: str
    reason: str


class BoardDealt(BaseEvent):
    type: Literal["board_dealt"] = "board_dealt"
    street: Street
    cards: tuple[str, ...]
    board: tuple[str, ...]


class ShowdownReveal(BaseEvent):
    type: Literal["showdown_reveal"] = "showdown_reveal"
    agent_id: str
    cards: tuple[str, str]


class PotAwarded(BaseEvent):
    type: Literal["pot_awarded"] = "pot_awarded"
    agent_id: str
    amount: int


class HandEnded(BaseEvent):
    type: Literal["hand_ended"] = "hand_ended"
    stacks: dict[str, int]
    deltas: dict[str, int]


class GameEnded(BaseEvent):
    type: Literal["game_ended"] = "game_ended"
    hand_no: int = 0
    hands_played: int
    stacks: dict[str, int]


GameEvent = Annotated[
    Union[
        GameStarted,
        HandStarted,
        BlindPosted,
        HoleCardsDealt,
        ActionTaken,
        ActionRepaired,
        AttentionCommitted,
        MessageSent,
        MessageRejected,
        BeliefsUpdated,
        LedgerUpdated,
        BoardDealt,
        ShowdownReveal,
        PotAwarded,
        HandEnded,
        GameEnded,
    ],
    Field(discriminator="type"),
]
