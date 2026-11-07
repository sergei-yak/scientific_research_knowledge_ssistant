"""Explicitly enabled service tests; offline test runs never contact services."""

import os

import pytest

from research_assistant.settings import Settings, configure_caches
from research_assistant.smoke import check_neo4j, check_ollama

pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("RUN_NEO4J_SMOKE") != "1", reason="Set RUN_NEO4J_SMOKE=1 to enable fixture writes")
def test_neo4j_parameterized_writes_and_indexes() -> None:
    result = check_neo4j(Settings.from_env())
    assert "pending" not in result and result["vector_and_fulltext"]


@pytest.mark.skipif(os.getenv("RUN_OLLAMA_SMOKE") != "1", reason="Set RUN_OLLAMA_SMOKE=1 to enable local inference")
def test_ollama_text_and_schema() -> None:
    configure_caches()
    result = check_ollama(Settings.from_env())
    assert "pending" not in result and len(result["probes"]) == 2
