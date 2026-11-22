"""Versioned, immutable boundaries for the first user-collection release."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit
import ipaddress
import re

from pydantic import ConfigDict, Field, field_validator, model_validator

from research_assistant.contracts import Contract, fingerprint

Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
CollectionId = Annotated[str, Field(pattern=r'^uc-[a-f0-9]{32}$')]
JobId = Annotated[str, Field(pattern=r'^import-[a-f0-9]{32}$')]
TERMINAL_STATES = frozenset({'ready', 'duplicate', 'failed', 'interrupted'})
JOB_TRANSITIONS = {
    'queued': {'resolving', 'failed', 'interrupted'},
    'resolving': {'parsing', 'duplicate', 'failed', 'interrupted'},
    'parsing': {'indexing', 'duplicate', 'failed', 'interrupted'},
    'indexing': {'ready', 'failed', 'interrupted'},
    **{state: set() for state in TERMINAL_STATES},
}


class ImmutableContract(Contract):
    """Persisted records are replaced by new revisions, never edited in place."""

    model_config = ConfigDict(extra='forbid', frozen=True)


class CollectionLimits(ImmutableContract):
    """Fixed v1 resource policy; raising a limit requires a recorded policy revision."""

    version: Literal[1] = 1
    max_collections: Literal[20] = 20
    max_revisions: Literal[100] = 100
    max_documents: Literal[10] = 10
    max_pdf_bytes: Literal[26214400] = 25 * 1024 * 1024
    max_collection_bytes: Literal[104857600] = 100 * 1024 * 1024
    max_pdf_pages: Literal[100] = 100
    max_collection_pages: Literal[300] = 300
    max_chunks: Literal[3000] = 3000
    max_url_length: Literal[2048] = 2048
    max_redirects: Literal[3] = 3
    request_timeout_seconds: Literal[30] = 30
    concurrent_imports: Literal[1] = 1
    automatic_retries: Literal[0] = 0


LIMITS = CollectionLimits()


def supported_url(value: str) -> str:
    """Validate syntax only; the M8.2 downloader must also check DNS and every redirect."""
    if len(value) > LIMITS.max_url_length or re.search(r'[\x00-\x20\x7f]', value):
        raise ValueError('URL is too long or contains whitespace/control characters')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or parsed.fragment):
        raise ValueError('Use a public HTTPS URL without credentials, fragments or a custom port')
    host = parsed.hostname.encode('idna').decode('ascii').lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP-literal URLs are unsupported')
    if (len(host) > 253 or '.' not in host or host.endswith(('.local', '.internal', '.localhost', '.test'))
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
            or all(part.isdecimal() for part in host.split('.'))
            or any(not part or len(part) > 63 or part.startswith('-') or part.endswith('-')
                   for part in host.split('.'))):
        raise ValueError('URL must name a public domain')
    path = parsed.path
    if host in {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'}:
        match = re.fullmatch(r'/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v[1-9]\d*)?)(?:\.pdf)?', path)
        if not match or parsed.query:
            raise ValueError('Use a modern arXiv abstract or PDF URL')
        return 'https://arxiv.org/pdf/' + match.group(1)
    if not path.lower().endswith('.pdf'):
        raise ValueError('Only arXiv pages and direct public PDF links are supported')
    return urlunsplit(('https', host, path, parsed.query, ''))


class InputReference(ImmutableContract):
    """Untrusted source identity, with no file/network access during construction."""

    kind: Literal['upload', 'url']
    value: str = Field(min_length=1)

    @model_validator(mode='after')
    def valid_input(self) -> InputReference:
        """Keep display filenames separate from server paths and bound URL syntax."""
        if self.kind == 'url':
            supported_url(self.value)
        elif (len(self.value) > 180 or self.value != self.value.strip()
              or not self.value.lower().endswith('.pdf') or self.value in {'.pdf', '..pdf'}
              or re.search(r'[\\/:\x00-\x1f\x7f]', self.value)):
            raise ValueError('Upload name must be a PDF basename, never a server path')
        return self


class DocumentVersion(ImmutableContract):
    """Actual PDF bytes, declared indexed coverage and immutable content identity."""

    paper_id: str = Field(min_length=1)
    source_sha256: Digest
    source: InputReference
    byte_count: int = Field(gt=0, le=LIMITS.max_pdf_bytes)
    pdf_pages: int = Field(gt=0, le=LIMITS.max_pdf_pages)
    indexed_pages: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def valid_coverage(self) -> DocumentVersion:
        """Reject duplicate, reordered and out-of-document coverage."""
        if self.paper_id != 'pdf-' + self.source_sha256:
            raise ValueError('User paper identity must bind the exact PDF content hash')
        if self.indexed_pages != tuple(sorted(set(self.indexed_pages))) or any(
                page < 1 or page > self.pdf_pages for page in self.indexed_pages):
            raise ValueError('Indexed pages must be unique, ordered and within the PDF')
        return self


class CorpusBinding(ImmutableContract):
    """Index snapshot identity; its presence alone never establishes runtime readiness."""

    corpus_id: Digest
    snapshot_sha256: Digest
    chunks_sha256: Digest
    chunk_count: int = Field(gt=0, le=LIMITS.max_chunks)
    encoder_revision: str = Field(min_length=1)


class UserCollection(ImmutableContract):
    """One immutable revision, distinct from the preserved pilot/expanded presets."""

    format: Literal['user-collection-v1'] = 'user-collection-v1'
    collection_id: CollectionId
    scope_sha256: Digest
    revision: int = Field(ge=1, le=LIMITS.max_revisions)
    previous_sha256: Digest
    name: str = Field(min_length=1, max_length=80)
    created_at: datetime
    documents: tuple[DocumentVersion, ...] = Field(default=(), max_length=LIMITS.max_documents)
    binding: CorpusBinding | None = None

    @field_validator('created_at')
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        """Audit timestamps always include an explicit timezone."""
        if value.tzinfo is None:
            raise ValueError('Timestamp requires a timezone')
        return value

    @field_validator('name')
    @classmethod
    def clean_name(cls, value: str) -> str:
        """Reject blank/control-only labels without silently changing saved names."""
        if value != value.strip() or not value.strip() or re.search(r'[\x00-\x1f\x7f]', value):
            raise ValueError('Collection name must be trimmed printable text')
        return value

    @model_validator(mode='after')
    def bounded_membership(self) -> UserCollection:
        """Duplicate content, excess coverage and foreign corpus identities fail closed."""
        if (len({d.source_sha256 for d in self.documents}) != len(self.documents)
                or len({d.paper_id for d in self.documents}) != len(self.documents)):
            raise ValueError('Duplicate document content or paper identity')
        if (sum(d.byte_count for d in self.documents) > LIMITS.max_collection_bytes
                or sum(d.pdf_pages for d in self.documents) > LIMITS.max_collection_pages):
            raise ValueError('Collection byte/page limit exceeded')
        if self.binding and (not self.documents or self.binding.corpus_id != self.corpus_id):
            raise ValueError('Index binding belongs to another collection/revision')
        if self.revision == 1 and self.previous_sha256 != '0' * 64:
            raise ValueError('Initial revision cannot inherit another collection head')
        return self

    @property
    def corpus_id(self) -> str:
        """Namespace content snapshots by collection, revision and exact source membership."""
        return fingerprint({'format': 'user-collection-corpus-v1', 'scope': self.scope_sha256,
            'collection_id': self.collection_id, 'revision': self.revision,
            'documents': [d.model_dump(mode='json') for d in self.documents]})

    @property
    def sha256(self) -> str:
        """Bind the complete revision, including its predecessor and index snapshot."""
        return fingerprint(self.model_dump(mode='json'))


class ImportJob(ImmutableContract):
    """Append-only import status. A recorded result never grants scientific approval."""

    format: Literal['user-import-job-v1'] = 'user-import-job-v1'
    job_id: JobId
    collection_id: CollectionId
    collection_sha256: Digest
    scope_sha256: Digest
    sequence: int = Field(ge=1)
    previous_sha256: Digest
    created_at: datetime
    inputs: tuple[InputReference, ...] = Field(min_length=1, max_length=LIMITS.max_documents)
    state: Literal['queued', 'resolving', 'parsing', 'indexing', 'ready', 'duplicate', 'failed', 'interrupted'] = 'queued'
    reason: str | None = None
    output_corpus_id: Digest | None = None

    @model_validator(mode='after')
    def consistent_status(self) -> ImportJob:
        """Keep failures/duplicates explicit; successful indexing needs an output identity."""
        if self.created_at.tzinfo is None:
            raise ValueError('Timestamp requires a timezone')
        if self.state in {'failed', 'interrupted', 'duplicate'} and not (self.reason and self.reason.strip()):
            raise ValueError('Terminal failure/duplicate state requires a reason')
        if (self.state == 'ready') != (self.output_corpus_id is not None):
            raise ValueError('Only a completed indexing job has an output corpus')
        if self.sequence == 1 and (self.state != 'queued' or self.previous_sha256 != '0' * 64):
            raise ValueError('An import must begin with a new queued event')
        return self

    @property
    def sha256(self) -> str:
        """Bind one exact status event for history replay and optimistic updates."""
        return fingerprint(self.model_dump(mode='json'))
