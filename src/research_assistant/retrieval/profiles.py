"""Profile and physical scope guards shared by retrieval and saved-result validation."""
from pathlib import Path

from research_assistant.contracts import Chunk, ExperimentScope, QueryRequest, RetrievalProfile, fingerprint
from research_assistant.graph.recovery import attest_target
from research_assistant.ingestion.sources import source_identity
from research_assistant.retrieval.catalog import ReviewCatalog
from research_assistant.settings import Settings


def reference_profile(profile_id: str) -> RetrievalProfile:
    """Hash explicit policies; a reranker cannot be requested before its separate model gate."""
    if profile_id not in {'baseline', 'retrieval-v2'}:
        raise ValueError('Unknown retrieval profile')
    return RetrievalProfile(profile_id=profile_id, policy_sha256=fingerprint({
        'profile': profile_id, 'selector': 'reference', 'routes': 'broader-routes-v1' if profile_id=='retrieval-v2' else 'legacy-routes-v1',
        'features': 'canonical-evidence-v1', 'ranking': 'alias-cosine-path-baseline-id',
        'channel_limit':12, 'rrf_k':60, 'anchors':4, 'rows':80, 'graph_candidates':40,
        'units':6, 'tokens':1800}))


def retrieval_profile(profile_id: str,selector_id: str='reference') -> RetrievalProfile:
    """Keep reference identity stable; explicit reranking requires its verified model identity."""
    reference=reference_profile(profile_id)
    if selector_id=='reference':return reference
    if profile_id!='retrieval-v2' or selector_id!='cross_encoder':
        raise ValueError('Unsupported profile/selector combination')
    from research_assistant.retrieval.reranker import verified_manifest,model_identity
    identity=model_identity(verified_manifest())
    return RetrievalProfile(profile_id='retrieval-v2',selector_id='cross_encoder',model_identity=identity,
        policy_sha256=fingerprint({'reference_policy':reference.policy_sha256,'selector':'cross_encoder',
                                  'model':identity,'ties':'score-desc-baseline-rank-asc-id'}))


def load_scope(request: QueryRequest) -> ExperimentScope:
    """Reject external/private paths before reading a scope declaration."""
    if request.profile_id != 'retrieval-v2' or not request.scope_file:
        raise ValueError('retrieval-v2 requires an explicit local scope file')
    path=Path(request.scope_file).resolve()
    allowed=Path('data/scopes').resolve()
    if path==allowed or not path.is_relative_to(allowed):
        raise ValueError('Scope files must be inside this worktree data/scopes')
    scope=ExperimentScope.model_validate_json(path.read_bytes())
    if scope.corpus_id!=request.corpus_id or scope.profile_id!=request.profile_id:
        raise ValueError('Requested profile/corpus differs from experiment scope')
    return scope


def validate_scope(request: QueryRequest, settings: Settings, review_directory: Path,
                   chunks: dict[str,Chunk], catalog: ReviewCatalog, repo) -> ExperimentScope:
    """Fail closed on a copied scope used with a different checkout, endpoint or review store."""
    scope=load_scope(request)
    root=Path.cwd().resolve()
    if (root==Path(scope.baseline_root).resolve() or not (root/'.git').is_file()
            or settings.neo4j_uri!=scope.target_uri
            or Path(review_directory).resolve()!=Path(scope.review_directory).resolve()
            or not Path(review_directory).resolve().is_relative_to(root/'data/reviews')
            or catalog.head!=scope.review_head or source_identity(chunks)!=scope.source_chunks_sha256):
        raise ValueError('Experiment checkout/target/source/review scope mismatch')
    target=attest_target(settings, {'source_uri':'bolt://127.0.0.1:7687'},scope.target_id)
    if (target['container_id']!=scope.container_id or target['image_id']!=scope.image_id
            or target['volumes']!=sorted(scope.volumes)):
        raise ValueError('Experiment container/image/volume identity mismatch')
    with repo.reading(scope.corpus_id,catalog.head,settings.graph_query_timeout_seconds):
        row=repo.tx.run('MATCH (c:Corpus {id:$id,project:$project,ready:true}) '
            'RETURN c.experiment_scope_id AS scope,c.retrieval_profile_id AS profile,c.frozen AS frozen,c.experiment_scope_sha256 AS binding',
            id=scope.corpus_id,project=repo.project).single()
        if (row is None or row['scope']!=scope.scope_id or row['profile']!=scope.profile_id or row['frozen']
                or row['binding']!=fingerprint(scope.model_dump())):
            raise ValueError('Database scope is missing, frozen or mismatched')
    return scope
