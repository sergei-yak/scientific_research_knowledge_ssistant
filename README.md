# Scientific Research Knowledge Assistant

Current implementation: **M0 environment and smoke checks**. Product ingestion, retrieval,
review, evaluation and UI milestones are defined in `IMPLEMENTATION_PLAN.md` and are not implemented yet.
Read `project_spec.md` and `AGENTS.md` before making changes.

## Setup (PowerShell, project root)

1. Use Python 3.11 and `uv`. The locked Windows/Linux PyTorch source is the official CUDA 12.4 index for PyTorch 2.6. CUDA runtime libraries are supplied by the wheel; verify the NVIDIA driver with the probes below.
2. Run `uv sync --locked`. Initial dependency resolution is `uv lock`; routine checks must not regenerate the lockfile.
3. Copy `.env.example` to `.env` only if `.env` does not exist; choose a strong `NEO4J_PASSWORD`. The generated local `.env`, when present, is ignored by Git. Cache/model files, reports and data are also ignored.
4. Start Docker Desktop and Ollama. Run `docker compose config --quiet`, then `docker compose up -d neo4j`. This Compose project uses its own named data/log volumes and binds ports to localhost. If ports are occupied, choose unused ports in `.env` and update `NEO4J_URI`; preserve the other service.
5. Check `docker compose ps`. The image is pinned to `neo4j:5.26.32-community`; the readiness report records the pulled digest. Do not use `docker compose down -v` or reset existing volumes.

## M0 checks

The CLI defaults to imports/resources. Live operations and model downloads require explicit selection.
Each JSON report path must be new; an existing report is never overwritten.

```powershell
uv lock --check
uv run --locked python -m research_assistant --help
uv run --locked pytest -m "not integration"
uv run --locked python -m research_assistant smoke --checks imports resources openai --output runs/m0/environment.json
uv run --locked python -m research_assistant smoke --checks model-artifacts --allow-model-download --output runs/m0/model-artifacts.json
uv run --locked python -m research_assistant smoke --checks embeddings --output runs/m0/embeddings.json
uv run --locked python -m research_assistant smoke --checks neo4j --output runs/m0/neo4j.json
uv run --locked python -m research_assistant smoke --checks ollama --resident-encoder --output runs/m0/ollama.json
```

The artifact check downloads the two specified pretrained encoders and `o200k_base` estimator
only when allowed. Revision-addressed `.cache/models/` directories avoid Windows symlink privileges.
Later inference checks use those completed local artifacts without hub access. Encoder inference uses CPU for the
resource-sharing probe; a separate CUDA matrix check verifies the GPU-enabled PyTorch installation.
The Ollama probe uses the configured, already installed model with a small context/output limit,
temperature zero and thinking disabled; it does not pull models or substitute another provider.
`--resident-encoder` holds cached CPU MiniLM during local inference so Neo4j/encoder/Ollama
coexistence can be measured. Ollama may release the model after its two-minute keep-alive.
These small M0 probe limits are not the final answer-generation budget: M1 must account for
instructions, question, evidence and output together and recheck resources at that context size.

The Neo4j check writes one parameterized sentinel twice, creates UUID-scoped vector/full-text
indexes, awaits `ONLINE`, queries both and cleans up only that invocation's fixture resources.
It does not ingest papers or touch existing application data.

Optional pytest service checks are separately marked and disabled unless enabled:

```powershell
$env:RUN_NEO4J_SMOKE = '1'
uv run --locked pytest -m integration tests/integration/test_smoke_services.py
Remove-Item Env:RUN_NEO4J_SMOKE
```

Set `RUN_OLLAMA_SMOKE=1` only when intentionally repeating local inference. Offline tests do not
contact either service. Failed checks exit nonzero; **pending** checks are explicitly recorded and
do not mean the corresponding milestone gate passed.

## Provider readiness

The explicit M0 live choice is local Ollama (`qwen3.8:latest`); the actual digest is recorded.
OpenAI is configuration/import-only in M0. The `openai` probe makes **zero paid requests**;
credentials and a user-approved numerical budget remain prerequisites for budget-accounted
adapter probes in M1/M3. There is no automatic provider fallback. Do not add a key or raise
spend settings on the assumption that it authorizes paid execution.

Actual task outcomes, limitations and evidence paths are maintained in `IMPLEMENTATION_PLAN.md`.
Dependency, Docker and model downloads may need network access; service checks need local
Docker/Ollama access. A sandbox permission failure is not proof that a service itself is broken.

Technical sources: [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/),
[uv PyTorch integration](https://docs.astral.sh/uv/guides/integration/pytorch/),
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
