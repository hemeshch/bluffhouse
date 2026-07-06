"""OpenAI-compatible adapter: one class covers OpenAI, Grok (xAI), and
open-source models served by Ollama, vLLM, or any other OpenAI-compatible
endpoint — they all speak the same chat-completions dialect."""

import os
import time

import openai

from bluffhouse.llm.base import LLMClient, LLMError, LLMRequest, LLMResponse

# preset -> (base_url, api_key_env). base_url None = the SDK's default (OpenAI).
PRESETS: dict[str, tuple[str | None, str | None]] = {
    "openai": (None, "OPENAI_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
}


class OpenAICompatClient(LLMClient):
    def __init__(
        self,
        model: str,
        preset: str = "openai",
        base_url: str | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
    ):
        if preset not in PRESETS:
            raise ValueError(f"unknown preset '{preset}' (choose from {', '.join(PRESETS)})")
        preset_url, key_env = PRESETS[preset]
        self.model = model
        resolved_key = api_key or (os.environ.get(key_env) if key_env else None)
        if key_env is not None and resolved_key is None:
            raise LLMError(f"no API key for '{preset}' — set {key_env}")
        self._client = openai.OpenAI(
            base_url=base_url or preset_url,
            api_key=resolved_key or "unused",  # key-less local servers (ollama, vllm)
            max_retries=max_retries,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        messages = [{"role": "system", "content": request.system}, *request.messages]
        start = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=request.max_tokens,
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"openai-compat ({self.model}): {exc}") from exc
        latency = time.monotonic() - start

        text = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_s=latency,
        )
