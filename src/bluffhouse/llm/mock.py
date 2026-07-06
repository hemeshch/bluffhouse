"""Deterministic in-memory client so the whole LLM path is testable without
a network or a token."""

from collections.abc import Callable

from bluffhouse.llm.base import LLMClient, LLMRequest, LLMResponse


class MockClient(LLMClient):
    """Replies from a fixed queue, then from `fallback` (a function of the
    request) once the queue runs dry. Records every request it sees."""

    def __init__(
        self,
        replies: list[str] | None = None,
        fallback: Callable[[LLMRequest], str] | None = None,
        model: str = "mock",
    ):
        self.model = model
        self.replies = list(replies or [])
        self.fallback = fallback
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.replies:
            text = self.replies.pop(0)
        elif self.fallback is not None:
            text = self.fallback(request)
        else:
            text = '{"action": "check"}'
        return LLMResponse(text=text, model=self.model, input_tokens=10, output_tokens=5)
