"""The provider-agnostic LLM client surface.

bluffhouse never talks to a vendor SDK directly — agents see only LLMClient.
Provider quirks (parameter names, auth, thinking modes) live inside each
adapter, so putting a new model at the table means one new adapter class and
nothing else changes.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
import os
import re
import threading

from pydantic import BaseModel


class LLMError(Exception):
    """A provider call failed after the SDK's own retries. Agents catch this
    and fall back to a safe action instead of crashing the game."""


class LLMRequest(BaseModel):
    system: str
    # [{"role": "user"|"assistant", "content": str}, ...] — first must be user
    messages: list[dict[str, str]]
    max_tokens: int = 8000


class LLMResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0


class LLMCall(BaseModel):
    """One transcript line: everything about a single provider call, so any
    decision in a benchmark run can be audited after the fact. Token counts
    are the ground truth; dollar cost is a downstream concern (tokens ×
    whatever prices are true on the day of analysis)."""

    agent_id: str
    hand_no: int
    # increments once per decision (act() call); attempts within a decision
    # share it, which is what lets a replay match reasoning to actions
    decision_id: int
    phase: str = "action"  # "action" | "comm"
    attempt: int
    messages: list[dict[str, str]]
    response_text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    parse_error: str | None = None
    action: str | None = None


class LLMClient(ABC):
    model: str

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one completion. Raises LLMError on unrecoverable provider
        failure (after the SDK's own retry policy)."""


_semaphores: dict[str, threading.Semaphore] = {}
_semaphores_lock = threading.Lock()


def _provider_env_name(provider: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "_", provider.upper()).strip("_")
    return f"BLUFFHOUSE_{key}_CONCURRENCY"


def _provider_limit(provider: str) -> int:
    raw = os.environ.get(
        _provider_env_name(provider),
        os.environ.get("BLUFFHOUSE_LLM_CONCURRENCY", "1"),
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


@contextmanager
def provider_concurrency(provider: str) -> Iterator[None]:
    """Limit concurrent live calls per provider across parallel rotations."""
    limit = _provider_limit(provider)
    key = f"{provider}:{limit}"
    with _semaphores_lock:
        semaphore = _semaphores.setdefault(key, threading.Semaphore(limit))
    with semaphore:
        yield
