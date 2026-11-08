"""Offline provider-boundary tests; no real requests or downloaded models."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from research_assistant.contracts import DraftAnswer
from research_assistant import llm
from research_assistant.settings import Settings
from research_assistant.retrieval.ranking import reciprocal_rank_fusion


class FakeSDK:
    calls = 0
    reason = "stop"
    content = '{"answer":"Missing evidence","citations":[],"insufficient_evidence":true}'

    def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model="qwen3.8:latest", digest="fixed")])

    def chat(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(message=SimpleNamespace(content=self.content), done_reason=self.reason,
                               prompt_eval_count=100, eval_count=20)

    def ps(self):
        return SimpleNamespace(models=[])


def client(monkeypatch):
    sdk = FakeSDK()
    monkeypatch.setattr(llm.ollama, "Client", lambda **kwargs: sdk)
    monkeypatch.setattr(llm, "estimate_tokens", lambda text: len(text) // 4)
    return llm.OllamaClient(Settings()), sdk


def test_prompt_overflow_is_rejected_before_inference(monkeypatch):
    model, sdk = client(monkeypatch)
    with pytest.raises(ValueError, match="safety margin"):
        model.generate_text([{"role": "user", "content": "x" * 20000}])
    assert sdk.calls == 0


def test_invalid_json_and_length_stop_are_never_accepted(monkeypatch):
    model, sdk = client(monkeypatch)
    sdk.content = "not JSON"
    with pytest.raises(ValidationError):
        model.generate_structured(DraftAnswer, [{"role": "user", "content": "question"}])
    assert sdk.calls == 1
    sdk.reason = "length"
    with pytest.raises(ValueError, match="limit"):
        model.generate_text([{"role": "user", "content": "question"}])
    assert sdk.calls == 2


def test_model_identity_change_and_provider_switch_fail_before_calls(monkeypatch):
    model, sdk = client(monkeypatch)
    sdk.list = lambda: SimpleNamespace(models=[SimpleNamespace(model="qwen3.8:latest", digest="changed")])
    with pytest.raises(ValueError, match="digest changed"):
        model.generate_text([{"role": "user", "content": "question"}])
    assert sdk.calls == 0
    with pytest.raises(ValueError, match="no provider fallback"):
        llm.OllamaClient(Settings(generation_provider="openai"))


def test_rrf_uses_ranks_not_raw_scores_and_deduplicates_each_list():
    result = reciprocal_rank_fusion([["a", "a", "b"], ["b", "a"]])
    assert [identity for identity, _ in result] == ["a", "b"]
    assert result[0][1] == result[1][1]
    assert result[0][1] == pytest.approx(1 / 61 + 1 / 62)
