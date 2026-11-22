"""Small append-only local registry; no second application database or automatic approvals."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Iterator
from uuid import uuid4

from research_assistant.collections.contracts import (
    CorpusBinding, DocumentVersion, ImportJob, InputReference, JOB_TRANSITIONS, LIMITS, TERMINAL_STATES, UserCollection,
)
from research_assistant.collections.scope import load_user_scope


class CollectionRegistry:
    """Persist only inside one explicit scope; metadata never asserts live index/review readiness."""

    def __init__(self, workspace: Path | None = None):
        """Validate paths and fixed ownership before creating any registry directories."""
        self.workspace = (workspace or Path.cwd()).resolve()
        self.scope = load_user_scope(self.workspace)
        self.root = Path(self.scope.storage_root)

    def _path(self, *parts: str) -> Path:
        """Reject traversal and redirected files/directories, including within another collection."""
        path = self.root.joinpath(*parts)
        if path.resolve() != path or not path.is_relative_to(self.root):
            raise ValueError('Registry path escaped or was redirected')
        return path

    def _check_owner(self) -> None:
        """Do not allow a new declaration to silently take over an existing storage root."""
        path = self._path('owner.json')
        if not path.exists() or json.loads(path.read_bytes()) != {'scope_sha256': self.scope.sha256}:
            raise ValueError('Registry owner does not match the current scope')

    def initialize(self) -> None:
        """Create metadata only once; refuse nonempty unowned roots and never repair stale locks."""
        self._path()
        if self.root.exists():
            self._check_owner()
            return
        self.root.mkdir(parents=True, exist_ok=False)
        self._write(self._path('owner.json'), {'scope_sha256': self.scope.sha256})

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize writers/import reservations; stale locks remain explicit failures."""
        self._check_owner()
        path = self._path('.registry.lock')
        token = uuid4().hex
        with path.open('x', encoding='utf-8') as handle:
            handle.write(token)
        try:
            yield
        finally:
            if path.read_text(encoding='utf-8') != token:
                raise ValueError('Registry lock ownership changed; preserve it for investigation')
            path.unlink()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        """Use create-only records; failed/interrupted writes are never overwritten automatically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(value, sort_keys=True, indent=2) + '\n')

    def _history(self, kind: str, ident: str, model: type) -> list:
        """Replay exact contiguous events and predecessor hashes, rejecting changed ownership."""
        self._check_owner()
        pattern = r'uc-[a-f0-9]{32}' if kind == 'collections' else r'import-[a-f0-9]{32}'
        if not re.fullmatch(pattern, ident):
            raise ValueError('Invalid collection/job identity')
        directory = self._path(kind, ident, 'history')
        rows, previous = [], '0' * 64
        for number, path in enumerate(sorted(directory.glob('*.json')), 1):
            if path.name != f'{number:06d}.json':
                raise ValueError('Registry history is missing or reordered')
            self._path(kind, ident, 'history', path.name)
            envelope = json.loads(path.read_bytes())
            row = model.model_validate(envelope['record'])
            sequence = row.revision if kind == 'collections' else row.sequence
            identity = row.collection_id if kind == 'collections' else row.job_id
            if (sequence != number or identity != ident or row.previous_sha256 != previous
                    or row.scope_sha256 != self.scope.sha256 or envelope['sha256'] != row.sha256):
                raise ValueError('Registry record hash, chain or ownership mismatch')
            if kind == 'jobs' and rows:
                fixed = ('job_id', 'collection_id', 'collection_sha256', 'scope_sha256', 'created_at', 'inputs')
                if (any(getattr(row, key) != getattr(rows[-1], key) for key in fixed)
                        or row.state not in JOB_TRANSITIONS[rows[-1].state]):
                    raise ValueError('Import history changed identity or has an invalid state transition')
            rows.append(row)
            previous = row.sha256
        return rows

    def _append(self, kind: str, ident: str, row: UserCollection | ImportJob) -> None:
        """Persist an exact complete revision while the workspace lock is held."""
        sequence = row.revision if isinstance(row, UserCollection) else row.sequence
        self._write(self._path(kind, ident, 'history', f'{sequence:06d}.json'),
            {'record': row.model_dump(mode='json'), 'sha256': row.sha256})

    def list(self) -> list[UserCollection]:
        """Read only this registry's collection IDs, never discover source or evaluator files."""
        self._check_owner()
        return [self.get(path.name) for path in sorted(self._path('collections').glob('*'))]

    def get(self, collection_id: str) -> UserCollection:
        """Return the latest verified revision; unknown or damaged collections fail explicitly."""
        history = self._history('collections', collection_id, UserCollection)
        if not history:
            raise ValueError('Collection does not exist')
        return history[-1]

    def jobs(self) -> list[ImportJob]:
        """Replay status histories; an interrupted/unknown active job is never retried implicitly."""
        self._check_owner()
        result = []
        for path in sorted(self._path('jobs').glob('*')):
            history = self._history('jobs', path.name, ImportJob)
            if not history:
                raise ValueError('Import job history is missing')
            job = history[-1]
            history_collection = self._history('collections', job.collection_id, UserCollection)
            if job.collection_sha256 not in {row.sha256 for row in history_collection}:
                raise ValueError('Import job belongs to an unknown collection revision')
            result.append(job)
        return result

    def create(self, name: str) -> UserCollection:
        """Create an empty collection without downloading, indexing, inference or approval."""
        with self._locked():
            if len(self.list()) >= LIMITS.max_collections:
                raise ValueError('Collection limit reached')
            row = UserCollection(collection_id='uc-' + uuid4().hex, scope_sha256=self.scope.sha256,
                revision=1, previous_sha256='0' * 64, name=name, created_at=datetime.now(timezone.utc))
            self._append('collections', row.collection_id, row)
            return row

    def revise(self, collection_id: str, expected_sha256: str, *, name: str,
               documents: tuple[DocumentVersion, ...] | None = None, binding: CorpusBinding | None = None) -> UserCollection:
        """Publish a new revision; readiness/approvals do not carry to a changed binding."""
        with self._locked():
            current = self.get(collection_id)
            if self._path('.query.lock').exists():
                raise ValueError('A question is running; wait before changing collection revisions')
            if current.sha256 != expected_sha256:
                raise ValueError('Collection changed; reload before publishing')
            if any(j.collection_id == collection_id and j.state not in TERMINAL_STATES for j in self.jobs()):
                raise ValueError('Collection has an active import; resolve it before revising')
            row = UserCollection(collection_id=collection_id, scope_sha256=self.scope.sha256,
                revision=current.revision + 1, previous_sha256=current.sha256, name=name,
                created_at=datetime.now(timezone.utc),
                documents=current.documents if documents is None else documents, binding=binding)
            self._append('collections', collection_id, row)
            return row

    def queue(self, collection_id: str, expected_sha256: str, inputs: tuple[InputReference, ...]) -> ImportJob:
        """Reserve the sole foreground import slot; M8.1 does not execute the queued work."""
        with self._locked():
            if self._path('.query.lock').exists():
                raise ValueError('A question is running; wait before starting an import')
            current = self.get(collection_id)
            if current.sha256 != expected_sha256:
                raise ValueError('Collection changed; reload before queueing')
            if any(job.state not in TERMINAL_STATES for job in self.jobs()):
                raise ValueError('Another import is active; no automatic takeover/retry')
            if current.binding:
                self.committed_import(current)
            job = ImportJob(job_id='import-' + uuid4().hex, collection_id=collection_id,
                collection_sha256=current.sha256, scope_sha256=self.scope.sha256, sequence=1,
                previous_sha256='0' * 64, created_at=datetime.now(timezone.utc), inputs=inputs)
            self._append('jobs', job.job_id, job)
            return job

    def interrupt(self, job_id: str, expected_sha256: str, reason: str) -> ImportJob:
        """Explicitly close an unexecuted/stopped import without erasing its reservation/history."""
        with self._locked():
            if self._path('.worker.lock').exists():
                raise ValueError('An import worker is active; stop it before explicitly interrupting')
            history = self._history('jobs', job_id, ImportJob)
            if not history:
                raise ValueError('Import job does not exist')
            current = history[-1]
            if current.sha256 != expected_sha256 or current.state in TERMINAL_STATES:
                raise ValueError('Job changed or is already terminal')
            job = ImportJob.model_validate({**current.model_dump(), 'sequence': current.sequence + 1,
                'previous_sha256': current.sha256, 'state': 'interrupted', 'reason': reason})
            self._append('jobs', job_id, job)
            return job

    @contextmanager
    def worker(self, job_id: str) -> Iterator[str]:
        """Run one foreground worker; abrupt crashes leave an explicit lock/reservation."""
        self.get_job(job_id)
        path = self._path('.worker.lock')
        token = job_id + ':' + uuid4().hex
        with self._locked():
            if self._path('.query.lock').exists():
                raise ValueError('A question is running; import worker cannot start')
            with path.open('x', encoding='utf-8') as handle:
                handle.write(token)
        try:
            yield token
        finally:
            if path.read_text(encoding='utf-8') != token:
                raise ValueError('Import worker lock changed; preserve it for investigation')
            path.unlink()

    @contextmanager
    def query_lock(self) -> Iterator[None]:
        """Serialize local queries with imports across sessions; never reclaim a stale lock."""
        path = self._path('.query.lock')
        token = uuid4().hex
        with self._locked():
            if self._path('.worker.lock').exists() or any(j.state not in TERMINAL_STATES for j in self.jobs()):
                raise ValueError('An import is active or reserved; finish it before asking a question')
            with path.open('x', encoding='utf-8') as handle:
                handle.write(token)
        try:
            yield
        finally:
            if path.read_text(encoding='utf-8') != token:
                raise ValueError('Question lock ownership changed; preserve it for investigation')
            path.unlink()

    def get_job(self, job_id: str) -> ImportJob:
        """Read one exact job, validating its collection revision and the entire status chain."""
        history = self._history('jobs', job_id, ImportJob)
        if not history:
            raise ValueError('Import job does not exist')
        job = history[-1]
        if job.collection_sha256 not in {
                c.sha256 for c in self._history('collections', job.collection_id, UserCollection)}:
            raise ValueError('Import job references an unknown collection revision')
        return job

    def _advance(self, job: ImportJob, state: str, reason: str | None = None,
                 output_corpus_id: str | None = None) -> ImportJob:
        """Append a checked status event under both caller-held locks."""
        if state not in JOB_TRANSITIONS[job.state]:
            raise ValueError('Invalid import state transition')
        updated = ImportJob.model_validate({**job.model_dump(), 'sequence': job.sequence + 1,
            'previous_sha256': job.sha256, 'state': state, 'reason': reason,
            'output_corpus_id': output_corpus_id})
        self._append('jobs', job.job_id, updated)
        return updated

    def _check_worker(self, job_id: str, token: str) -> None:
        """A live worker cannot be replaced by another process or an unrelated job."""
        if not token.startswith(job_id + ':') or self._path('.worker.lock').read_text(encoding='utf-8') != token:
            raise ValueError('Import worker ownership mismatch')

    def advance(self, job_id: str, expected_sha256: str, token: str,
                state: str, reason: str | None = None) -> ImportJob:
        """Record progress/failure; ready requires a separate source-binding commit."""
        with self._locked():
            self._check_worker(job_id, token)
            job = self.get_job(job_id)
            if job.sha256 != expected_sha256 or state == 'ready':
                raise ValueError('Import head changed or ready requires a committed collection')
            return self._advance(job, state, reason)

    def publish_import(self, job_id: str, expected_sha256: str, token: str,
                       collection: UserCollection) -> ImportJob:
        """Commit a fully indexed new revision; partial multi-file writes never gain a commit receipt."""
        with self._locked():
            self._check_worker(job_id, token)
            job = self.get_job(job_id)
            current = self.get(job.collection_id)
            if (job.sha256 != expected_sha256 or job.state != 'indexing'
                    or current.sha256 != job.collection_sha256
                    or collection.collection_id != current.collection_id
                    or collection.scope_sha256 != self.scope.sha256
                    or collection.previous_sha256 != current.sha256
                    or collection.revision != current.revision + 1 or collection.binding is None
                    or collection.documents[:len(current.documents)] != current.documents):
                raise ValueError('Indexed collection does not match its reserved source revision')
            self._append('collections', collection.collection_id, collection)
            ready = self._advance(job, 'ready', output_corpus_id=collection.corpus_id)
            self._write(self._path('jobs', job_id, 'commit.json'), {
                'collection_sha256': collection.sha256, 'job_sha256': ready.sha256,
                'corpus_id': collection.corpus_id, 'scope_sha256': self.scope.sha256})
            return ready

    def committed_import(self, collection: UserCollection) -> ImportJob:
        """Incomplete publication is an error, never an inferred success or automatic resume."""
        if collection.scope_sha256 != self.scope.sha256 or collection.binding is None:
            raise ValueError('Collection has no committed index binding')
        for job in self.jobs():
            if job.collection_id != collection.collection_id or job.output_corpus_id != collection.corpus_id:
                continue
            expected = {'collection_sha256': collection.sha256, 'job_sha256': job.sha256,
                        'corpus_id': collection.corpus_id, 'scope_sha256': self.scope.sha256}
            path = self._path('jobs', job.job_id, 'commit.json')
            if job.state == 'ready' and path.exists() and json.loads(path.read_bytes()) == expected:
                return job
        raise ValueError('Collection publication is incomplete; explicit investigation required')

    def review_directory(self, collection: UserCollection) -> Path:
        """Derive the only valid review root for this exact scope, collection and revision."""
        if collection.scope_sha256 != self.scope.sha256 or self.get(collection.collection_id) != collection:
            raise ValueError('Collection scope/revision is stale or foreign')
        return self._path('collections', collection.collection_id, 'revisions', f'{collection.revision:06d}', 'reviews')

    def describe(self, collection: UserCollection) -> dict:
        """Describe metadata only; workspace QA separately verifies actual live readiness."""
        return {**collection.model_dump(mode='json'), 'sha256': collection.sha256,
            'review_directory': str(self.review_directory(collection)),
            'readiness': 'empty' if not collection.documents else 'not_verified', 'available_modes': []}
