"""Provider adapter wiring — no network, just construction and config."""

import pytest

from bluffhouse.llm import LLMError, OpenAICompatClient


def test_openrouter_preset_resolves_base_url_and_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = OpenAICompatClient("meta-llama/llama-3.3-70b-instruct", preset="openrouter")
    assert str(client._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert client.model == "meta-llama/llama-3.3-70b-instruct"


def test_keyed_presets_fail_fast_without_key(monkeypatch):
    for preset, env in (("openai", "OPENAI_API_KEY"), ("xai", "XAI_API_KEY"), ("openrouter", "OPENROUTER_API_KEY")):
        monkeypatch.delenv(env, raising=False)
        with pytest.raises(LLMError, match=env):
            OpenAICompatClient("some-model", preset=preset)


def test_ollama_needs_no_key(monkeypatch):
    client = OpenAICompatClient("llama3.3", preset="ollama")
    assert str(client._client.base_url).startswith("http://localhost:11434/v1")


def test_unknown_preset_rejected():
    with pytest.raises(ValueError, match="unknown preset"):
        OpenAICompatClient("m", preset="nonsense")


def test_cli_seat_spec_keeps_slashes_in_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    from bluffhouse.agents import LLMAgent
    from bluffhouse.harness.cli import build_agent

    agent = build_agent("openrouter:qwen/qwen3-coder", "A", seed=1)
    assert isinstance(agent, LLMAgent)
    assert agent.client.model == "qwen/qwen3-coder"
