"""Checksummed logical snapshots and fail-closed restore to an isolated empty target."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from neo4j import Query, READ_ACCESS
from neo4j.exceptions import Neo4jError

from research_assistant.contracts import Chunk, fingerprint
from research_assistant.graph.repository import GraphRepository, PROJECT
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings

BASE_LABELS = {'Paper', 'Chunk', 'Corpus', 'ReviewedClaim', 'FactText', 'Method', 'Dataset', 'ReviewState'}
RELATIONSHIPS = {'HAS_PAPER', 'HAS_CHUNK', 'CITES', 'REPORTS_EVALUATION', 'REPORTS_FINDING',
                 'OF_METHOD', 'ON_DATASET', 'ABOUT_METHOD', 'ABOUT_DATASET', 'ABOUT_EVALUATION',
                 'MENTIONS', 'SUPPORTED_BY', 'REPRESENTS'}
PROPERTIES = {'id', 'text', 'search_text', 'canonical_name', 'aliases', 'embedding_384', 'embedding_768'}


def require_read_only(settings: Settings) -> dict:
    """Prove server write refusal in a transaction that is always rolled back, even on failure."""
    repo = GraphRepository(settings)
    refused = None
    try:
        with repo.driver.session(database=repo.database) as session:
            tx = session.begin_transaction()
            try:
                tx.run('CREATE (:RAWriteProbe {probe:$probe})', probe='rollback-only-readiness-probe').consume()
            except Neo4jError as exc:
                if exc.code not in {'Neo.ClientError.General.ForbiddenOnReadOnlyDatabase',
                                    'Neo.ClientError.General.WriteOnReadOnlyAccessDatabase'}:
                    raise
                refused = exc.code
            finally:
                tx.rollback()
        if refused is None:
            raise ValueError('Frozen evaluator database still allows writes')
        return {'write_refused': True, 'code': refused, 'probe_rolled_back': True}
    finally:
        repo.close()


def frozen_projection(graph: dict, corpus_id: str) -> dict:
    """Freeze only one exported Corpus flag, without mutating the working capture or facts."""
    matches = [node for node in graph['nodes'] if 'Corpus' in node['labels'] and node['properties']['id'] == corpus_id]
    if len(matches) != 1 or not matches[0]['properties'].get('ready'):
        raise ValueError('Only an existing ready corpus can be frozen in an export')
    return {**graph, 'nodes': [
        {**node, 'properties': {**node['properties'], 'frozen': True}} if node is matches[0] else node
        for node in graph['nodes']]}


def identifier(value: str) -> str:
    """Whitelist schema identifiers; artifact strings never become arbitrary Cypher."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('Unsafe schema identifier')
    return '`' + value + '`'


def labels_valid(labels: list[str]) -> None:
    """Allow only the application schema and content-addressed corpus/active-fact labels."""
    if not labels or len(BASE_LABELS.intersection(labels)) != 1 or any(
            label not in BASE_LABELS | {'Evaluation', 'Finding'} and
            not re.fullmatch(r'(RACorpus|RAApproved)_[0-9a-f]{16}', label) for label in labels):
        raise ValueError('Unsupported node labels')


def node_key(labels: list[str], identity: str) -> str:
    """IDs are unique within a base label, not necessarily across different entity types."""
    labels_valid(labels)
    if not isinstance(identity, str) or not identity:
        raise ValueError('Node lacks a stable string ID')
    return next(iter(BASE_LABELS.intersection(labels))) + ':' + identity


def capture(settings: Settings) -> dict:
    """Capture project-owned graph and relevant schema in a single read transaction."""
    repo = GraphRepository(settings)
    try:
        with repo.driver.session(database=repo.database, default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=120) as tx:
                version = tx.run('CALL dbms.components() YIELD versions,edition RETURN versions,edition').single().data()
                nodes = tx.run('MATCH (n {project:$project}) RETURN labels(n) AS labels,properties(n) AS properties', project=PROJECT).data()
                relations = tx.run('MATCH (a {project:$project})-[r]->(b {project:$project}) '
                    'RETURN labels(a) AS a_labels,a.id AS a_id,labels(b) AS b_labels,b.id AS b_id,'
                    'type(r) AS type,properties(r) AS properties', project=PROJECT).data()
                constraints = tx.run('SHOW CONSTRAINTS YIELD name,type,entityType,labelsOrTypes,properties '
                    'WHERE name STARTS WITH "ra_" RETURN name,type,entityType,labelsOrTypes,properties').data()
                indexes = tx.run('SHOW INDEXES YIELD name,type,entityType,labelsOrTypes,properties,options,owningConstraint '
                    'WHERE name STARTS WITH "ra_" AND owningConstraint IS NULL '
                    'RETURN name,type,entityType,labelsOrTypes,properties,options').data()
        for node in nodes:
            node['labels'] = sorted(node['labels'])
            node['key'] = node_key(node['labels'], node['properties'].get('id'))
        edges = [{'start': node_key(r['a_labels'], r['a_id']), 'end': node_key(r['b_labels'], r['b_id']),
                  'type': r['type'], 'properties': r['properties']} for r in relations]
        graph = {'version': version, 'nodes': sorted(nodes, key=lambda n: n['key']),
                 'relationships': sorted(edges, key=lambda r: (r['start'], r['type'], r['end'], fingerprint(r['properties']))),
                 'constraints': sorted(constraints, key=lambda row: row['name']),
                 'indexes': sorted(indexes, key=lambda row: row['name'])}
        validate_graph(graph)
        return graph
    finally:
        repo.close()


def validate_graph(graph: dict) -> None:
    """Check semantic identities, source hashes, vectors and supported schema before any write."""
    if graph['version'] != {'versions': ['5.26.32'], 'edition': 'community'}:
        raise ValueError('Recovery requires the tested Neo4j 5.26.32 Community version')
    keys = set()
    for node in graph['nodes']:
        props = node['properties']
        if node_key(node['labels'], props.get('id')) != node['key'] or node['key'] in keys or props.get('project') != PROJECT:
            raise ValueError('Duplicate/invalid node identity or ownership')
        keys.add(node['key'])
        if 'Chunk' in node['labels']:
            chunk = Chunk.model_validate_json(props['source_json'])
            if chunk.chunk_id != props['id'] or chunk.text != props['text']:
                raise ValueError('Stored chunk/source identity mismatch')
        for name, dimension in [('embedding_384', 384), ('embedding_768', 768)]:
            if name in props:
                vector = np.asarray(props[name], dtype=float)
                if vector.shape != (dimension,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-5):
                    raise ValueError('Invalid snapshot vector')
    for row in graph['relationships']:
        if row['start'] not in keys or row['end'] not in keys or row['type'] not in RELATIONSHIPS:
            raise ValueError('Invalid relationship endpoint/type')
    schema_commands(graph)  # Validate schema separately from property data.


def schema_commands(graph: dict) -> list[tuple[str, dict]]:
    """Construct schema operations from bounded metadata, never execute exported statements."""
    commands = []
    for row in graph['constraints']:
        if (not row['name'].startswith('ra_') or row['type'] != 'UNIQUENESS' or row['entityType'] != 'NODE'
                or len(row['labelsOrTypes']) != 1 or row['labelsOrTypes'][0] not in BASE_LABELS or row['properties'] != ['id']):
            raise ValueError('Unsupported recovery constraint')
        commands.append((f'CREATE CONSTRAINT {identifier(row["name"])} FOR (n:{identifier(row["labelsOrTypes"][0])}) REQUIRE n.id IS UNIQUE', {}))
    for row in graph['indexes']:
        if (not row['name'].startswith('ra_') or row['entityType'] != 'NODE' or row['type'] not in {'VECTOR', 'FULLTEXT'}
                or not row['properties'] or not set(row['properties']) <= PROPERTIES):
            raise ValueError('Unsupported recovery index')
        for label in row['labelsOrTypes']:
            if label not in {'Method', 'Dataset'} and not re.fullmatch(r'(RACorpus|RAApproved)_[a-f0-9]{16}', label):
                raise ValueError('Unsupported recovery index label')
        label = '|'.join(identifier(value) for value in row['labelsOrTypes'])
        fields = ','.join('n.' + identifier(value) for value in row['properties'])
        if row['type'] == 'VECTOR':
            if len(row['labelsOrTypes']) != 1 or len(row['properties']) != 1:
                raise ValueError('Invalid vector index shape')
            statement = f'CREATE VECTOR INDEX {identifier(row["name"])} FOR (n:{label}) ON ({fields}) OPTIONS $options'
        else:
            statement = f'CREATE FULLTEXT INDEX {identifier(row["name"])} FOR (n:{label}) ON EACH [{fields}] OPTIONS $options'
        commands.append((statement, {'options': row['options']}))
    return commands


def safe_asset(root: Path, relative: str) -> Path:
    """Keep copied/restored assets inside declared roots; reject traversal and symlinks."""
    relative_path = Path(relative)
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise ValueError('Snapshot asset path escapes its root')
    path = root / relative_path
    if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Snapshot asset path escapes its root or uses a symlink')
    return path


def export_snapshot(settings: Settings, output: Path, review_directory: Path, *, freeze_corpus: bool = False) -> dict:
    """Export graph twice around allowlisted asset copying; reject intervening writes/inconsistency."""
    if output.exists():
        raise ValueError('Snapshot directory already exists; never overwrite a backup')
    root = Path.cwd().resolve()
    with review_lock(review_directory):
        from research_assistant.graph.search import SearchRepository
        from research_assistant.ingestion.sources import load_corpus_chunks
        from research_assistant.retrieval.catalog import load_catalog
        config = json.loads((review_directory / 'config.json').read_text(encoding='utf-8'))
        chunks = load_corpus_chunks(config['corpus_id'])
        catalog = load_catalog(review_directory, config['corpus_id'], chunks)
        repo = SearchRepository(settings)
        try:
            source = repo.snapshot(config['corpus_id'])
            with repo.reading(config['corpus_id'], catalog.head, settings.graph_query_timeout_seconds):
                repo.fact_vectors(catalog, chunks, source['encoder_revision'])
        finally:
            repo.close()
        graph = capture(settings)
        relative_files = set()
        corpora = [node['properties']['id'] for node in graph['nodes'] if 'Corpus' in node['labels']]
        for corpus in corpora:
            if not re.fullmatch('[a-f0-9]{64}', corpus):
                raise ValueError('Invalid corpus identity in snapshot')
            directory = Path('data/processed') / corpus
            if not directory.is_dir():
                raise ValueError('Snapshot references a missing source cache')
            relative_files.update(str(path.relative_to(root)) for path in (root / directory).rglob('*') if path.is_file())
        for directory in (review_directory, Path('data/reviews/pilot'), Path('manifests'), Path('src/research_assistant'), Path('scripts'), Path('tests'),
                          Path('data/evaluation/development/pilot-v1'), Path('data/metadata/pilot-v1'),
                          Path('data/evaluation/development/expansion-v1'), Path('data/metadata/expansion-v1'),
                          Path('data/embeddings'), Path('runs/m4-2/development-encoders'),
                          Path('data/extraction'), Path('data/accounting'), Path('runs/m3/pilot-verified'),
                          Path('runs/m3-2/local-product-v2'), Path('runs/m3-2/abstention-final')):
            relative_files.update(str(path.relative_to(root)) for path in (root / directory).rglob('*')
                                  if path.is_file() and '__pycache__' not in path.parts and path.name not in {'.review.lock', '.openai.lock'})
        for path in Path('manifests').glob('*.json'):
            value = json.loads(path.read_text(encoding='utf-8'))
            papers = value.get('papers', [value])
            for paper in papers:
                if 'local_path' in paper:
                    source = safe_asset(root / 'data/raw', str(Path(paper['local_path']).relative_to('data/raw')))
                    relative_files.add(str(source.relative_to(root)))
        relative_files.update(['pyproject.toml', 'uv.lock', 'compose.yaml', '.env.example',
                               '.streamlit/config.toml', 'README.md', 'project_spec.md',
                               'project_spec_submission.md', 'IMPLEMENTATION_PLAN.md', 'AGENTS.md'])
        output.mkdir(parents=True)
        assets = {}
        for relative in sorted(relative_files):
            source, target = safe_asset(root, relative), safe_asset(output / 'files', relative)
            if source.name == '.env' or source.name.startswith('.env.') and source.name != '.env.example':
                raise ValueError('Credentials must not enter snapshots')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            assets[Path(relative).as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
        if capture(settings) != graph:
            raise ValueError('Graph changed during export; incomplete snapshot is not restorable')
        # Verify copied bytes still match the quiesced sources.
        if any(hashlib.sha256(safe_asset(root, name).read_bytes()).hexdigest() != digest for name, digest in assets.items()):
            raise ValueError('Source/review assets changed during export')
        source_graph_sha256 = fingerprint(graph)
        if freeze_corpus:
            # Freeze only the exported target's readiness flag; working data stays writable/unchanged.
            graph = frozen_projection(graph, catalog.corpus_id)
        write_immutable(output / 'graph.json', json.dumps(graph, ensure_ascii=False, sort_keys=True) + '\n')
        manifest = {'format': 'logical-recovery-v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                    **code_identity(), 'project': PROJECT, 'source_uri': settings.neo4j_uri,
                    'source_database': settings.neo4j_database, 'graph_sha256': fingerprint(graph),
                    'review_head': catalog.head, 'review_corpus_id': catalog.corpus_id,
                    'source_graph_sha256': source_graph_sha256,
                    'freeze_projection': {'corpus_id': catalog.corpus_id, 'field': 'frozen', 'value': True} if freeze_corpus else None,
                    'graph_file_sha256': hashlib.sha256((output / 'graph.json').read_bytes()).hexdigest(),
                    'assets': assets, 'nodes': len(graph['nodes']), 'relationships': len(graph['relationships']),
                    'configuration': settings.model_dump(mode='json', exclude={'neo4j_password', 'openai_api_key', 'openalex_api_key'}),
                    'external_dependencies': 'Locked Python environment and separately cached pinned encoder weights; not copied.'}
        write_immutable(output / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return {'snapshot': str(output), 'graph_sha256': manifest['graph_sha256'],
            'manifest_sha256': hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest(),
            'nodes': manifest['nodes'], 'relationships': manifest['relationships'], 'asset_files': len(assets)}


def verify_snapshot(directory: Path) -> tuple[dict, dict]:
    """Require complete manifest and all byte/semantic hashes before constructing writes."""
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['format'] != 'logical-recovery-v1' or manifest['project'] != PROJECT:
        raise ValueError('Unsupported snapshot format/owner')
    raw = (directory / 'graph.json').read_bytes()
    graph = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != manifest['graph_file_sha256'] or fingerprint(graph) != manifest['graph_sha256']:
        raise ValueError('Snapshot graph checksum mismatch')
    for relative, digest in manifest['assets'].items():
        if hashlib.sha256(safe_asset(directory / 'files', relative).read_bytes()).hexdigest() != digest:
            raise ValueError('Snapshot asset checksum mismatch')
    validate_graph(graph)
    return manifest, graph


def attest_target(settings: Settings, manifest: dict, target_project: str) -> dict:
    """Bind the local endpoint to a separately named disposable Compose container and volumes."""
    if not re.fullmatch(r'dbu-m[34]-recovery-[a-z0-9-]+', target_project):
        raise ValueError('Restore requires an explicitly named disposable recovery project')
    target_port = urlsplit(settings.neo4j_uri).port or 7687
    if target_port == (urlsplit(manifest['source_uri']).port or 7687):
        raise ValueError('Refusing to restore to the source database endpoint')
    raw = subprocess.run(['docker', 'inspect', target_project + '-neo4j-1'],
                         capture_output=True, text=True, timeout=20, check=True)
    container = json.loads(raw.stdout)[0]
    volumes = {mount.get('Name') for mount in container['Mounts'] if mount['Destination'] in {'/data', '/logs'}}
    bindings = container['NetworkSettings']['Ports'].get('7687/tcp') or []
    if (container['Config']['Labels'].get('com.docker.compose.project') != target_project
            or volumes != {target_project + '_neo4j_data', target_project + '_neo4j_logs'}
            or not bindings or any(binding['HostIp'] != '127.0.0.1' or int(binding['HostPort']) != target_port for binding in bindings)
            or not container['State']['Running']):
        raise ValueError('Recovery endpoint/container/volume identity mismatch')
    return {'container_id': container['Id'], 'project': target_project, 'volumes': sorted(volumes),
            'image_id': container['Image'], 'target_uri': settings.neo4j_uri}


def restore_snapshot(directory: Path, settings: Settings, target_project: str) -> dict:
    """Restore once into an attested empty database; never reset, delete or overwrite nodes."""
    manifest, graph = verify_snapshot(directory)
    target = attest_target(settings, manifest, target_project)
    repo = GraphRepository(settings)
    try:
        with repo.driver.session(database=repo.database) as session:
            if session.run('MATCH (n) RETURN count(n) AS n').single()['n'] or session.run('SHOW CONSTRAINTS').data():
                raise ValueError('Recovery target must be empty with no existing constraints')
            if any(row['type'] != 'LOOKUP' for row in session.run('SHOW INDEXES').data()):
                raise ValueError('Recovery target has existing application indexes')
            version = session.run('CALL dbms.components() YIELD versions,edition RETURN versions,edition').single().data()
            if version != graph['version']:
                raise ValueError('Target Neo4j version differs from snapshot')
            groups = defaultdict(list)
            for node in graph['nodes']:
                groups[tuple(node['labels'])].append(node['properties'])
            # One data transaction; failed restores leave no partial node/edge data.
            with session.begin_transaction(timeout=120) as tx:
                for labels, rows in groups.items():
                    pattern = ':'.join(identifier(label) for label in labels)
                    tx.run(f'UNWIND $rows AS props CREATE (n:{pattern}) SET n=props', rows=rows).consume()
                relgroups = defaultdict(list)
                for row in graph['relationships']:
                    a_kind, a_id = row['start'].split(':', 1)
                    b_kind, b_id = row['end'].split(':', 1)
                    relgroups[(a_kind, row['type'], b_kind)].append({'start': a_id, 'end': b_id, 'props': row['properties']})
                for (a, kind, b), rows in relgroups.items():
                    tx.run(f'UNWIND $rows AS row MATCH (a:{identifier(a)} {{id:row.start}}),(b:{identifier(b)} {{id:row.end}}) '
                           f'CREATE (a)-[r:{identifier(kind)}]->(b) SET r=row.props', rows=rows).consume()
            for statement, params in schema_commands(graph):
                session.run(Query(statement, timeout=60), **params).consume()
            session.run('CALL db.awaitIndexes(180)').consume()
        restored = capture(settings)
        if restored != graph:
            raise ValueError('Restored semantic graph/schema differs from snapshot; preserve target for investigation')
        return {**target, 'graph_sha256': fingerprint(restored), 'nodes': len(restored['nodes']),
                'relationships': len(restored['relationships']), 'semantic_graph_schema_equal': True}
    finally:
        repo.close()
