"""Distinct physical read-only evaluation scope, never a repointed development declaration."""

from pathlib import Path
import json
import subprocess
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from research_assistant.contracts import Contract, fingerprint
from research_assistant.graph.recovery import attest_target, require_read_only
from research_assistant.ingestion.sources import source_identity
from research_assistant.settings import Settings

HEX = r'^[a-f0-9]{64}$'


class FrozenEvaluationScope(Contract):
    """New target authority plus explicit retained projection lineage from the source copy."""

    format: Literal['matched-read-only-scope-v1'] = 'matched-read-only-scope-v1'
    scope_id: str = Field(pattern=r'^m5eval-[a-f0-9]{12}$')
    corpus_id: str = Field(pattern=HEX)
    source_chunks_sha256: str = Field(pattern=HEX)
    review_head: str = Field(pattern=HEX)
    catalog_sha256: str = Field(pattern=HEX)
    baseline_root: str
    review_directory: Literal['data/reviews/expansion-v1'] = 'data/reviews/expansion-v1'
    source_uri: str
    target_uri: str
    target_project: str = Field(pattern=r'^dbu-m4-recovery-m5eval-[a-f0-9]{12}$')
    container_id: str = Field(pattern=HEX)
    image_id: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    volumes: list[str] = Field(min_length=2, max_length=2)
    graph_sha256: str = Field(pattern=HEX)
    snapshot_manifest_sha256: str = Field(pattern=HEX)
    projection_scope_id: str = Field(pattern=r'^m5dev-[a-f0-9]{12}$')
    projection_scope_sha256: str = Field(pattern=HEX)
    projection_profile_id: Literal['retrieval-v2'] = 'retrieval-v2'
    frozen: Literal[True] = True

    @model_validator(mode='after')
    def isolated_target(self):
        """Refuse development/consumed targets and default/source database endpoints."""
        Settings(neo4j_uri=self.source_uri)
        Settings(neo4j_uri=self.target_uri)
        from research_assistant.evaluation.readiness_v2 import private_path
        private_path(self.baseline_root)
        source, target = urlsplit(self.source_uri), urlsplit(self.target_uri)
        if (source.scheme != 'bolt' or target.scheme != 'bolt' or target.port in {None, 7687, 9765}
                or target.port == (source.port or 7687)
                or self.target_project != 'dbu-m4-recovery-' + self.scope_id
                or sorted(self.volumes) != [self.target_project+'_neo4j_data', self.target_project+'_neo4j_logs']):
            raise ValueError('Matched scope needs a distinct new read-only target and owned volumes')
        if any(value == '0'*64 for value in (self.graph_sha256, self.container_id, self.snapshot_manifest_sha256,
                                             self.projection_scope_sha256)):
            raise ValueError('Read-only scope requires actual target/recovery commitments')
        return self


def validate_frozen_scope(scope: FrozenEvaluationScope, request, settings, review_directory,
                          chunks, catalog, repo) -> FrozenEvaluationScope:
    """Check exact physical/source ownership and write refusal before and after each request."""
    scope = FrozenEvaluationScope.model_validate(scope.model_dump(mode='json'))
    if (request.corpus_id != scope.corpus_id or settings.neo4j_uri != scope.target_uri
            or Path(review_directory).resolve() != Path(scope.review_directory).resolve()
            or catalog.head != scope.review_head or fingerprint(catalog.facts) != scope.catalog_sha256
            or source_identity(chunks) != scope.source_chunks_sha256):
        raise ValueError('Frozen query source/review/endpoint mismatch')
    target = attest_target(settings, {'source_uri': scope.source_uri}, scope.target_project)
    if (target['container_id'] != scope.container_id or target['image_id'] != scope.image_id
            or target['volumes'] != sorted(scope.volumes)):
        raise ValueError('Frozen query physical target changed')
    require_read_only(settings)
    with repo.reading(scope.corpus_id, catalog.head, settings.graph_query_timeout_seconds):
        row = repo.tx.run('MATCH (c:Corpus {id:$id,project:$project,ready:true}) '
            'RETURN c.experiment_scope_id AS scope,c.retrieval_profile_id AS profile,'
            'c.frozen AS frozen,c.experiment_scope_sha256 AS binding', id=scope.corpus_id, project=repo.project).single()
        if (row is None or row['scope'] != scope.projection_scope_id or row['profile'] != scope.projection_profile_id
                or row['frozen'] is not True or row['binding'] != scope.projection_scope_sha256):
            raise ValueError('Frozen projection/lineage is missing or mismatched')
    return scope


def inspect_container(scope: FrozenEvaluationScope, *, running: bool) -> dict:
    """Inspect the exact already-created container before lifecycle actions; never create or pull."""
    scope = FrozenEvaluationScope.model_validate(scope.model_dump(mode='json'))
    raw = subprocess.run(['docker', 'inspect', scope.container_id], capture_output=True, text=True,
                         timeout=20, check=True)
    row = json.loads(raw.stdout)[0]
    mounts = {m.get('Name') for m in row['Mounts'] if m['Destination'] in {'/data','/logs'}}
    bindings = row['HostConfig']['PortBindings'].get('7687/tcp') or []
    environment = dict(pair.split('=',1) for pair in row['Config']['Env'] if '=' in pair)
    if (row['Id'] != scope.container_id or row['Image'] != scope.image_id
            or row['Name'] != '/'+scope.target_project+'-neo4j-1'
            or row['Config']['Labels'].get('com.docker.compose.project') != scope.target_project
            or mounts != set(scope.volumes) or row['State']['Running'] is not running
            or not bindings or any(b['HostIp']!='127.0.0.1' or int(b['HostPort'])!=urlsplit(scope.target_uri).port for b in bindings)
            or environment.get('NEO4J_server_databases_default__to__read__only') != 'true'):
        raise ValueError('Matched lifecycle target is not the exact retained read-only container')
    return row


def prepare_scope(snapshot_directory: Path, recovery_report: Path, settings: Settings, output: Path) -> dict:
    """Attest a real new recovered target; no working projection/old declaration is rewritten."""
    from research_assistant.evaluation.matched_assets import public_asset
    from research_assistant.evaluation.freeze import file_sha
    from research_assistant.graph.recovery import verify_snapshot, capture
    from research_assistant.pipeline import write_immutable
    manifest, graph = verify_snapshot(public_asset(snapshot_directory))
    proof = json.loads(public_asset(recovery_report).read_text(encoding='utf-8'))
    if (not proof.get('complete') or not proof.get('target_read_only_proved')
            or proof.get('snapshot_manifest_sha256') != file_sha(public_asset(snapshot_directory)/'manifest.json')
            or proof.get('graph_sha256') != manifest['graph_sha256']):
        raise ValueError('Actual matched recovery/read-only proof is required')
    project = proof['project']
    target = settings.model_copy(update={'neo4j_uri':proof['target_uri']})
    physical = attest_target(target, manifest, project)
    require_read_only(target)
    if fingerprint(capture(target)) != manifest['graph_sha256']:
        raise ValueError('Recovered graph changed before scope attestation')
    corpora = [n['properties'] for n in graph['nodes'] if 'Corpus' in n['labels'] and n['properties']['id']==manifest['review_corpus_id']]
    if len(corpora)!=1 or corpora[0].get('frozen') is not True:
        raise ValueError('Snapshot lacks the exact frozen Corpus projection')
    projection = corpora[0]
    from research_assistant.contracts import ExperimentScope
    original_scope = ExperimentScope.model_validate_json(Path('data/scopes/retrieval-v2.json').read_bytes())
    if (projection.get('experiment_scope_id') != original_scope.scope_id
            or projection.get('experiment_scope_sha256') != fingerprint(original_scope.model_dump())):
        raise ValueError('Retained projection lineage differs from the verified source scope')
    from research_assistant.ingestion.sources import load_corpus_chunks
    from research_assistant.retrieval.catalog import load_catalog
    from research_assistant.review.store import review_lock
    chunks = load_corpus_chunks(manifest['review_corpus_id'])
    with review_lock(Path('data/reviews/expansion-v1')):
        catalog = load_catalog(Path('data/reviews/expansion-v1'),manifest['review_corpus_id'],chunks)
        scope = FrozenEvaluationScope(scope_id=project.removeprefix('dbu-m4-recovery-'),
            corpus_id=catalog.corpus_id, source_chunks_sha256=source_identity(chunks), review_head=catalog.head,
            catalog_sha256=fingerprint(catalog.facts), baseline_root=original_scope.baseline_root,
            source_uri=manifest['source_uri'], target_uri=target.neo4j_uri,
            target_project=project, container_id=physical['container_id'], image_id=physical['image_id'],
            volumes=physical['volumes'], graph_sha256=manifest['graph_sha256'],
            snapshot_manifest_sha256=file_sha(public_asset(snapshot_directory)/'manifest.json'),
            projection_scope_id=projection['experiment_scope_id'],
            projection_scope_sha256=projection['experiment_scope_sha256'])
    inspect_container(scope,running=True)
    write_immutable(public_asset(output),scope.model_dump_json(indent=2)+'\n')
    return {'status':'matched_read_only_scope_attested','scope_path':str(output),
            'scope_sha256':file_sha(public_asset(output)),'execution_authorized':False}
