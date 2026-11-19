"""Explicit product corpus bindings; retrieval and approval rules stay in shared services."""

from dataclasses import dataclass
from pathlib import Path

from research_assistant.contracts import QueryRequest
from research_assistant.product import PILOT_CORPUS
from research_assistant.retrieval.profiles import load_scope
from research_assistant.settings import Settings


@dataclass(frozen=True)
class ProductCorpus:
    """One named indexed corpus and its matching current human review store."""

    label: str
    corpus_id: str
    review_directory: Path
    papers: int


CORPORA = {
    'pilot': ProductCorpus('Five-paper pilot', PILOT_CORPUS, Path('data/reviews/pilot'), 5),
    'expanded': ProductCorpus('Twenty-paper research corpus',
        '298e3cafbda1ffdf95c8ee66fa2b9ba3a81dc8d5e26bfb94816655ca41de3fbf',
        Path('data/reviews/expansion-v1'), 20),
}
MODE_LABELS = {'vector': 'Vector', 'hybrid': 'Hybrid',
               'hybrid_facts': 'Hybrid + Approved Facts', 'graph': 'Graph RAG'}
WORKFLOW_HELP = {
    'discovery': 'Find methods and the papers that evaluated them. Missing rows do not prove a method is absent.',
    'comparison': 'Compare paper-reported evaluation conditions. Unknown versions, splits or metrics prevent a controlled score ranking.',
    'limitations': 'Inspect paper-reported limitations with supporting quotations. Approval checks the source, not scientific truth.',
    'ask': 'Ask a free-form question about the selected papers. Enable an answer or inspect evidence only.',
}
FALLBACK_HELP = {
    'no_new_eligible_graph_candidates': 'Graph search found no additional eligible evidence. This result uses Hybrid + Approved Facts.',
    'graph_candidates_not_selected_within_budget': 'Additional graph evidence did not survive selection and the evidence budget. This result uses Hybrid + Approved Facts.',
}


def configured_profiles(corpus_key: str) -> list[str]:
    """Do not offer an experimental scope owned by a different retained checkout."""
    if corpus_key != 'expanded':
        return ['baseline']
    try:
        corpus = CORPORA[corpus_key]
        scope = load_scope(QueryRequest(question='Product scope selection', corpus_id=corpus.corpus_id,
            profile_id='retrieval-v2', scope_file='data/scopes/retrieval-v2.json'))
        if Path(scope.review_directory).resolve() == corpus.review_directory.resolve():
            return ['baseline', 'retrieval-v2']
    except (OSError, ValueError):
        pass
    return ['baseline']


def product_target(corpus_key: str, profile: str, settings: Settings) -> tuple[ProductCorpus, Settings, str | None]:
    """Choose the declared target without rewriting scopes, projections or provider configuration."""
    corpus = CORPORA[corpus_key]
    if profile == 'baseline':
        return corpus, settings, None
    if profile != 'retrieval-v2' or corpus_key != 'expanded':
        raise ValueError('Experimental V2 requires the twenty-paper corpus')
    scope_file = 'data/scopes/retrieval-v2.json'
    scope = load_scope(QueryRequest(question='Product scope selection', corpus_id=corpus.corpus_id,
        profile_id=profile, scope_file=scope_file))
    if Path(scope.review_directory).resolve() != corpus.review_directory.resolve():
        raise ValueError('Experimental scope belongs to another checkout; use its retained evidence explorer')
    # Retrieval and saved-output services still validate physical ownership, current
    # approvals and the nonfrozen projection on every request/display.
    return corpus, settings.model_copy(update={'neo4j_uri': scope.target_uri}), scope_file
