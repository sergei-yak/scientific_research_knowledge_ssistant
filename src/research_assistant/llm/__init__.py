"""Explicit local-provider interface; no paid or alternate-provider fallback."""

from __future__ import annotations

import json
import time
from typing import Protocol, TypeVar

import ollama
from pydantic import BaseModel

from research_assistant.contracts import LLMResult
from research_assistant.retrieval.evidence import estimate_tokens
from research_assistant.settings import Settings

Schema = TypeVar("Schema", bound=BaseModel)


class LLMClient(Protocol):
    """Selected providers expose the same typed generation boundary."""

    def generate_text(self, messages: list[dict[str, str]]) -> LLMResult:
        """Generate bounded text with identity/usage metadata."""
        ...

    def generate_structured(self, schema: type[Schema], messages: list[dict[str, str]]) -> tuple[Schema, LLMResult]:
        """Validate the provider JSON against the supplied schema."""
        ...


class OllamaClient:
    """One explicitly selected model, bounded context, no retries or substitution."""

    def __init__(self, settings: Settings, context_tokens: int = 4096, output_tokens: int = 512) -> None:
        if settings.generation_provider != "ollama":
            raise ValueError("M1 implements local Ollama only; no provider fallback")
        if not 2048 <= context_tokens <= 8192 or not 64 <= output_tokens <= 1024:
            raise ValueError("M1 context/output limits are outside supported bounds")
        self.settings = settings
        self.context_tokens, self.output_tokens = context_tokens, output_tokens
        self.client = ollama.Client(host=settings.ollama_base_url, timeout=settings.request_timeout_seconds)
        self.model = settings.generation_model
        self.digest = self._digest()

    def _digest(self) -> str:
        models = self.client.list().models
        match = next((m for m in models if m.model == self.model), None)
        if match is None:
            raise ValueError("Configured local model is not installed; no automatic pull")
        return match.digest

    def _generate(self, messages: list[dict[str, str]], schema: dict | None) -> LLMResult:
        if self._digest() != self.digest:
            raise ValueError("Model digest changed during the run")
        estimate = estimate_tokens(json.dumps(messages, ensure_ascii=False))
        if schema:
            estimate += estimate_tokens(json.dumps(schema))
        # A conservative estimate, not a claim of native-token equivalence.
        if int(estimate * 1.25) + self.output_tokens + 256 > self.context_tokens:
            raise ValueError("Prompt/context safety margin exceeded; no implicit truncation")
        options = {"num_ctx": self.context_tokens, "num_predict": self.output_tokens,
                   "temperature": 0, "num_batch": 64}
        start = time.perf_counter()
        response = self.client.chat(model=self.model, messages=messages, format=schema,
                                    options=options, think=False, keep_alive="2m")
        if response.done_reason == "length":
            raise ValueError("Generator hit the output/context limit; answer not accepted")
        if response.prompt_eval_count is None:
            raise ValueError("Provider did not report native prompt usage")
        if response.prompt_eval_count + self.output_tokens > self.context_tokens:
            raise ValueError("Native context margin exceeded; answer not accepted")
        if self._digest() != self.digest:
            raise ValueError("Model digest changed during generation")
        return LLMResult(
            text=response.message.content, provider="ollama", model=self.model, digest=self.digest,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            usage={"prompt_tokens": response.prompt_eval_count, "output_tokens": response.eval_count},
            settings={**options, "thinking": False, "retries": 0, "concurrency": 1,
                      "prompt_estimate": estimate, "prompt_version": "grounded-vector-v1",
                      "loaded_models": [m.model_dump(mode="json") for m in self.client.ps().models]},
            messages=messages,
        )

    def generate_text(self, messages: list[dict[str, str]]) -> LLMResult:
        """Return bounded local text; never call another provider."""
        return self._generate(messages, None)

    def generate_structured(self, schema: type[Schema], messages: list[dict[str, str]]) -> tuple[Schema, LLMResult]:
        """Require fully schema-valid JSON; invalid/incomplete output fails visibly."""
        result = self._generate(messages, schema.model_json_schema())
        return schema.model_validate_json(result.text), result
