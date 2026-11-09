"""Carry unchanged review history into a superset corpus without granting new approval."""

import hashlib
import json
import shutil
from pathlib import Path

from research_assistant.contracts import fingerprint
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.review.facts import projection
from research_assistant.review.store import load_chunks, review_lock, state


def extend_scope(source: Path, target: Path, corpus_id: str) -> dict:
    """Require byte-equivalent source chunks, preserve receipts/events and create a new scope."""
    if target.exists():
        raise ValueError("Scope target must be a new directory")
    chunks = load_corpus_chunks(corpus_id)
    with review_lock(source):
        original_chunks = load_chunks(source)
        if any(chunks.get(key) != value for key, value in original_chunks.items()):
            raise ValueError("Expansion must preserve every original normalized source chunk")
        original = projection(source, original_chunks)
        config = json.loads((source / "config.json").read_text(encoding="utf-8"))
        files = [p for p in sorted(source.rglob('*')) if p.is_file() and p.name not in {'.review.lock', 'config.json'}]
        provenance = {'source_corpus_id': config['corpus_id'], 'source_review_head': state(source)['head'],
                      'target_corpus_id': corpus_id, 'new_human_decisions': 0,
                      'copied_files_sha256': fingerprint({p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})}
        target.mkdir(parents=True, exist_ok=False)
        for path in files:
            relative = path.relative_to(source)
            # Derived fact IDs bind corpus_id; retain old projections as history, never as target caches.
            destination = (target / 'inherited' / config['corpus_id'] / relative
                           if relative.parts[0] == 'projections' or relative.name == 'scope-extension.json'
                           else target / relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        write_immutable(target / 'config.json', json.dumps({**config, 'corpus_id': corpus_id}, indent=2) + '\n')
        write_immutable(target / 'scope-extension.json', json.dumps(provenance, indent=2) + '\n')
        carried = projection(target, chunks)
        if (carried['review_head'] != original['review_head']
                or len(carried['facts']) != len(original['facts'])):
            raise ValueError('Unchanged history failed eligibility replay in expanded scope')
    return {**provenance, 'eligible_carried_claims': len(carried['facts']), 'review_directory': str(target)}
