from pydantic import BaseModel, ConfigDict, Field


class Observation(BaseModel):
    """One agent's subjective view of one event — the only way game
    information ever reaches an agent.

    In mode 0 observations are faithful (confidence 1.0). From mode 3 on,
    the perception resolver produces fragments, mishearings, and omissions,
    and `confidence`/`decoded_meaning` start doing real work.
    """

    model_config = ConfigDict(frozen=True)

    observer: str
    source_event_id: str
    hand_no: int
    # the source event's type ("action_taken", "hand_ended", ...) — lets
    # consumers window history without ever touching the event itself
    kind: str = ""
    perceived_text: str
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    decoded_meaning: str | None = None
