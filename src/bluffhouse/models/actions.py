from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    # Covers both opening bets and raises; `amount` is the total wager to
    # reach this street, matching pokerkit's complete_bet_or_raise_to.
    RAISE_TO = "raise_to"


class PokerAction(BaseModel):
    """What an agent submits on its turn. Validated against LegalActions by
    the harness; anything illegal is repaired and the repair is logged."""

    action: ActionType
    amount: int | None = None

    def describe(self) -> str:
        if self.action is ActionType.RAISE_TO:
            return f"raise_to {self.amount}"
        return self.action.value


class LegalActions(BaseModel):
    """The action surface for the agent to act, as ground truth from the
    engine. `call_amount` is the additional chips needed to call."""

    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int = 0
    can_raise: bool
    min_raise_to: int | None = None
    max_raise_to: int | None = None


# ── Forward contracts (index.html §13) ─────────────────────────────────
# Defined now so every later mode is an extension, not a migration.
# Unused in mode 0.


class Modality(str, Enum):
    SPEECH = "speech"
    WHISPER = "whisper"
    GESTURE = "gesture"
    EYE_CONTACT = "eye_contact"
    NOTE = "note"
    CHIP_SIGNAL = "chip_signal"
    ACCUSATION = "accusation"


class CommunicationAction(BaseModel):
    """A communicative act. `content` is what the sender MEANT — ground
    truth, visible only to the environment. `surface_form` is what outsiders
    may observe. The gap between the two is how deception stays measurable
    without human labels."""

    sender: str
    target: list[str] | Literal["all"] = "all"
    modality: Modality
    content: str
    surface_form: str
    subtlety: float = Field(0.0, ge=0.0, le=1.0)
    deniability: float = Field(0.0, ge=0.0, le=1.0)
    sender_stealth: float = Field(0.0, ge=0.0, le=1.0)
    code_id: str | None = None
    distraction_power: float = Field(0.0, ge=0.0, le=1.0)


class AttentionPlan(BaseModel):
    """Where an agent points its perception this round. The budget across
    watched players plus the table must sum to 1.0; it is committed before
    communication happens."""

    watch_players: dict[str, float] = {}
    track_table: float = Field(1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _budget(self) -> "AttentionPlan":
        total = self.track_table + sum(self.watch_players.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"attention budget must sum to 1.0, got {total}")
        if any(v < 0 for v in self.watch_players.values()):
            raise ValueError("attention weights must be non-negative")
        return self
