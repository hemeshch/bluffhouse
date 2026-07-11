from pydantic import BaseModel, Field, model_validator


class TableConfig(BaseModel):
    """Configuration for one game: a sequence of hands at a single table.

    `agent_ids` is the physical seating ring; the harness rotates the button
    around it. The seed drives every deck shuffle and every scripted-bot RNG,
    so a config replays byte-identically.
    """

    seed: int
    num_hands: int = Field(20, ge=1)
    small_blind: int = Field(5, ge=1)
    big_blind: int = Field(10, ge=1)
    starting_stack: int = Field(1000, ge=1)
    agent_ids: list[str] = Field(min_length=2, max_length=10)
    mode: int = Field(0, ge=0, le=6)
    # per-street private belief reports (mode 2+); one extra LLM call per
    # agent per street, so cost-sensitive runs can switch it off
    collect_beliefs: bool = True

    @model_validator(mode="after")
    def _check(self) -> "TableConfig":
        if len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("agent_ids must be unique")
        if self.big_blind < self.small_blind:
            raise ValueError("big_blind must be >= small_blind")
        return self
