"""Claude adapter for the model-agnostic LLM surface."""

import time
from typing import Literal

import anthropic

from bluffhouse.llm.base import (
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    provider_concurrency,
)


class AnthropicClient(LLMClient):
    """Claude via the Anthropic SDK.

    Credentials resolve from the environment (ANTHROPIC_API_KEY, an
    `ant auth login` profile, ...). `thinking="adaptive"` is the default —
    it improves play quality; pass "off" for cheaper, faster games. On
    Claude Fable models thinking is always on and the parameter is omitted.
    """

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        thinking: Literal["adaptive", "off"] = "adaptive",
        max_retries: int = 3,
        api_key: str | None = None,
    ):
        self.model = model
        self._thinking = thinking
        self._client = anthropic.Anthropic(max_retries=max_retries, api_key=api_key)
        # Fail fast at the table, not mid-hand: mirror the SDK's own auth
        # check (api_key / auth_token / credentials, resolved from env or an
        # `ant auth login` profile).
        if not any(
            getattr(self._client, attr, None) is not None
            for attr in ("api_key", "auth_token", "credentials")
        ):
            raise LLMError(
                "no Anthropic credentials found — set ANTHROPIC_API_KEY "
                "or log in with `ant auth login`"
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict = {}
        # Fable models: thinking is always on; explicit config is rejected.
        if self._thinking == "adaptive" and not self.model.startswith("claude-fable"):
            kwargs["thinking"] = {"type": "adaptive"}

        start = time.monotonic()
        try:
            with provider_concurrency("anthropic"):
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=request.max_tokens,
                    system=request.system,
                    messages=request.messages,
                    **kwargs,
                )
        except (anthropic.APIError, TypeError) as exc:
            # TypeError is the SDK's unresolved-authentication failure mode
            raise LLMError(f"anthropic: {exc}") from exc
        latency = time.monotonic() - start

        if response.stop_reason == "refusal":
            # Never expected at a poker table, but don't crash the game.
            text = ""
        else:
            text = "".join(b.text for b in response.content if b.type == "text")

        usage = response.usage
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_s=latency,
        )
