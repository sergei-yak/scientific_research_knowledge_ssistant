"""Validated local settings; secrets are never included in smoke reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationInfo, field_validator


class Settings(BaseModel):
    """M0 configuration loaded explicitly from environment and a local dotenv file."""

    model_config = ConfigDict(extra="ignore")

    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    neo4j_database: str = "neo4j"
    extraction_provider: Literal["openai", "ollama"] = "ollama"
    extraction_model: str = "qwen3.8:latest"
    generation_provider: Literal["openai", "ollama"] = "ollama"
    generation_model: str = "qwen3.8:latest"
    ollama_base_url: str = "http://127.0.0.1:11434"
    openai_model: str = "gpt-6.1-terra"
    openai_api_key: SecretStr = SecretStr("")
    openalex_api_key: SecretStr = SecretStr("")
    api_budget_approved: bool = False
    api_budget_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    api_max_request_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    request_timeout_seconds: float = Field(default=180, gt=0, le=600)
    max_output_tokens: int = Field(default=128, gt=0, le=4096)
    max_concurrency: int = Field(default=1, ge=1, le=8)
    max_retries: int = Field(default=0, ge=0, le=3)
    ollama_context_tokens: int = Field(default=2048, ge=512, le=8192)

    @field_validator("neo4j_uri", "ollama_base_url")
    @classmethod
    def validate_local_endpoint(cls, value: str, info: ValidationInfo) -> str:
        """Restrict setup probes to local services and forbid embedded credentials."""
        parsed = urlsplit(value)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("M0 service endpoints must be local")
        if parsed.username or parsed.password:
            raise ValueError("Use separate credential settings")
        schemes = {"bolt", "neo4j"} if info.field_name == "neo4j_uri" else {"http", "https"}
        if parsed.scheme not in schemes:
            raise ValueError("Unsupported service scheme")
        return value

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> Settings:
        """Read settings without overriding process variables or printing secrets."""
        values = {**dotenv_values(env_file), **os.environ}
        return cls(**{key.lower(): value for key, value in values.items() if value is not None})

    def paid_probe_blockers(self) -> list[str]:
        """Return outstanding paid-operation prerequisites without making a request."""
        reasons = []
        if not self.openai_api_key.get_secret_value():
            reasons.append("OPENAI_API_KEY is not configured")
        if not self.api_budget_approved or self.api_budget_usd <= 0:
            reasons.append("No user-approved positive API budget")
        if not 0 < self.api_max_request_usd <= self.api_budget_usd:
            reasons.append("Per-request cost ceiling is missing or exceeds budget")
        return reasons

    def redact(self, message: str) -> str:
        """Remove configured secrets from diagnostic error messages."""
        for secret in (self.neo4j_password, self.openai_api_key, self.openalex_api_key):
            if value := secret.get_secret_value():
                message = message.replace(value, "[REDACTED]")
        return message


def configure_caches() -> None:
    """Keep model/token downloads in project-local ignored directories by default."""
    defaults = {
        "HF_HOME": ".cache/huggingface",
        "SENTENCE_TRANSFORMERS_HOME": ".cache/sentence-transformers",
        "TIKTOKEN_CACHE_DIR": ".cache/tiktoken",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
