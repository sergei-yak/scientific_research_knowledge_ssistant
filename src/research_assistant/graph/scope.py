"""Physical write isolation for a checkout carrying an M5 development declaration."""
from pathlib import Path

from research_assistant.contracts import ExperimentScope
from research_assistant.settings import Settings


def guard_development_write(settings: Settings) -> None:
    """Existing baseline checkout has no marker; scoped worktrees cannot write another target."""
    path=Path('data/scopes/retrieval-v2.json')
    if not path.exists():
        if Path('.git').is_file():
            raise ValueError('Development worktree writes require an explicit scope declaration')
        return
    scope=ExperimentScope.model_validate_json(path.read_bytes())
    if Path.cwd().resolve()==Path(scope.baseline_root).resolve() or settings.neo4j_uri!=scope.target_uri:
        raise ValueError('Refusing graph write outside the isolated development target')
    from research_assistant.graph.recovery import attest_target
    target=attest_target(settings,{'source_uri':'bolt://127.0.0.1:7687'},scope.target_id)
    if (target['container_id']!=scope.container_id or target['image_id']!=scope.image_id
            or target['volumes']!=sorted(scope.volumes)):
        raise ValueError('Development write target identity changed')
