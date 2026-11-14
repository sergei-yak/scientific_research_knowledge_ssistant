"""Development-only 40-read encoder/mode check; no provider or held-out inputs."""

import json
from pathlib import Path

from research_assistant.contracts import QueryRequest, RetrievalResult, fingerprint
from research_assistant.embeddings import Encoder, MPNetEncoder
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.graph.recovery import capture
from research_assistant.pipeline import run_query, write_immutable
from research_assistant.retrieval.embedding_experiment import retrieve_embedding
from research_assistant.settings import Settings, configure_caches


def main() -> None:
    """Record actual rendered-context scores; never tune from them or treat witnesses as results."""
    configure_caches()
    output = Path('runs/m4-2/development-encoders')
    if output.exists():
        raise ValueError('Preserve the existing check; use a new versioned script/output for a changed experiment')
    directory = Path('data/evaluation/development/expansion-v1')
    manifest, entries, chunks = load_dataset(directory)
    if not review_status(directory)['ready']:
        raise ValueError('Development annotations need human validation')
    settings, mini, mpnet = Settings.from_env(), Encoder(), MPNetEncoder()
    results = []
    for entry in entries:
        for mode in ('vector', 'hybrid', 'hybrid_facts', 'graph'):
            run = run_query(QueryRequest(corpus_id=manifest['corpus_id'], question=entry.gold.question, mode=mode),
                settings, generate=False, review_directory=Path('data/reviews/expansion-v1'), encoder=mini)
            write_immutable(output / entry.gold.question_id / (mode + '.json'), run.model_dump_json(indent=2) + '\n')
            results.append({'question_id': entry.gold.question_id, 'encoder': 'minilm', 'mode': mode,
                'effective_mode': run.retrieval.effective_mode, 'context_sha256': run.retrieval.context_sha256,
                'retrieval_ms': run.retrieval.retrieval_ms, 'score': score_evidence(entry.gold, run.retrieval, chunks)})
        artifact = retrieve_embedding(manifest['corpus_id'], entry.gold.question, 'mpnet', settings, encoder=mpnet)
        retrieved = RetrievalResult.model_validate(artifact['retrieval'])
        write_immutable(output / entry.gold.question_id / 'mpnet.json', json.dumps(artifact, indent=2) + '\n')
        results.append({'question_id': entry.gold.question_id, 'encoder': 'mpnet', 'mode': 'vector',
            'effective_mode': retrieved.effective_mode, 'context_sha256': retrieved.context_sha256,
            'retrieval_ms': retrieved.retrieval_ms, 'score': score_evidence(entry.gold, retrieved, chunks)})
        print('Completed development questions:', len(results) // 5, flush=True)
    before = json.loads(Path('runs/m4-2/preservation-before.json').read_text(encoding='utf-8'))
    after = capture(settings)
    current = {node['key']: node for node in after['nodes']}
    for node in before['nodes']:
        actual = current[node['key']]
        if (not set(node['labels']) <= set(actual['labels'])
                or any(actual['properties'].get(key) != value for key, value in node['properties'].items())):
            raise ValueError('An existing source/vector/review property changed')
        allowed = {'embedding_768', 'mpnet_encoder_revision'} if 'Chunk' in node['labels'] else (
            {'mpnet_manifest_json'} if 'Corpus' in node['labels'] else set())
        if set(actual['properties']) - set(node['properties']) - allowed:
            raise ValueError('Unexpected additive property')
    if (before['relationships'] != after['relationships'] or before['constraints'] != after['constraints']
            or len(before['nodes']) != len(after['nodes']) or any(index not in after['indexes'] for index in before['indexes'])):
        raise ValueError('Existing graph/schema identity changed')
    report = {'task_id': 'M4.2.1', 'reads': len(results), 'results': results,
        'source_corpus_id': manifest['corpus_id'], 'model_revisions': {'minilm': mini.revision, 'mpnet': mpnet.revision},
        'provider_calls': 0, 'private_evaluation_inputs_read': 0,
        'preservation': 'All prior node properties, labels, relationships and schema preserved; only MPNet fields/index added.',
        'nodes': len(after['nodes']), 'relationships': len(after['relationships']),
        'graph_sha256': fingerprint(after), 'note': 'Development retrieval measurements only; no generated-answer or final evaluation scores.'}
    write_immutable(output / 'summary.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps({'reads': len(results), 'provider_calls': 0, 'preservation': 'passed'}))


if __name__ == '__main__':
    main()
