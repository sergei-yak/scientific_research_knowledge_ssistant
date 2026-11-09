"""Offline tests for authorization, endpoint restrictions and secret handling."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from research_assistant.settings import Settings
from research_assistant.smoke import check_openai, run_check


@pytest.mark.parametrize("url", ["bolt://example.com:7687", "http://user:secret@localhost:11434", "file://localhost/data"])
def test_service_probe_cannot_target_remote_or_credential_url(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(neo4j_uri=url)


@pytest.mark.parametrize("field,url", [("neo4j_uri", "http://localhost:7687"), ("ollama_base_url", "bolt://localhost:11434")])
def test_local_services_require_the_correct_protocol(field: str, url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: url})


def test_process_environment_wins_without_mutation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GENERATION_MODEL=from-file\nNEO4J_PASSWORD=file-secret\n", encoding="utf-8")
    monkeypatch.setenv("GENERATION_MODEL", "from-process")
    settings = Settings.from_env(env_file)
    assert settings.generation_model == "from-process"
    assert "file-secret" not in repr(settings)


def test_paid_probes_need_approval_budget_and_request_ceiling() -> None:
    settings = Settings(openai_api_key="test-not-a-real-key")
    assert settings.paid_probe_blockers()
    assert Settings(openai_api_key="test-key", api_budget_approved=True, api_budget_usd=1, api_max_request_usd=2).paid_probe_blockers()
    assert not Settings(openai_api_key="test-key", api_budget_approved=True, api_budget_usd=1, api_max_request_usd=0.1, api_max_requests=2).paid_probe_blockers()


def test_openai_configuration_probe_never_constructs_api_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import openai

    def forbidden_client(*args: object, **kwargs: object) -> None:
        pytest.fail("A configuration probe attempted paid API access")

    monkeypatch.setattr(openai, "OpenAI", forbidden_client)
    result = check_openai(Settings())
    assert result["requests_made"] == 0 and result["pending"]


def test_failures_redact_secrets_and_pending_is_not_passed() -> None:
    settings = Settings(neo4j_password="private-password", openai_api_key="private-api-key")

    def failing_probe() -> dict:
        raise RuntimeError("private-password private-api-key")

    result = run_check("example", failing_probe, settings)
    assert result.status == "failed"
    assert "private" not in result.model_dump_json()
    assert run_check("missing", lambda: {"pending": "service unavailable"}, settings).status == "pending"


@pytest.mark.parametrize("field,value", [("api_budget_usd", -1), ("api_budget_usd", float("nan")), ("max_retries", 20), ("ollama_context_tokens", 1000000)])
def test_invalid_cost_and_resource_limits_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_local_model_revision_cannot_escape_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from research_assistant.smoke import encoder_artifact

    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".cache/models/all-MiniLM-L6-v2"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text('{"revision": "../../outside"}', encoding="utf-8")
    with pytest.raises(ValueError, match="revision"):
        encoder_artifact("all-MiniLM-L6-v2")


def test_cached_artifact_check_does_not_query_hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from huggingface_hub import HfApi
    from research_assistant.smoke import check_model_artifacts

    monkeypatch.chdir(tmp_path)

    def forbidden_metadata(*args: object, **kwargs: object) -> None:
        pytest.fail("Offline artifact check contacted the model hub")

    monkeypatch.setattr(HfApi, "model_info", forbidden_metadata)
    with pytest.raises(FileNotFoundError):
        check_model_artifacts(False)
