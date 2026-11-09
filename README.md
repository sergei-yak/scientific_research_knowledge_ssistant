# Scientific Research Knowledge Assistant

Current implementation: **M0–M3.1**, including four controlled retrieval modes on the five-paper pilot.
The CLI indexes MiniLM vectors in Neo4j, answers with local Qwen, and exports source-linked review packets.
Human review, approved-fact indexing, hybrid search and bounded graph traversal are implemented.
The UI, full product/recovery acceptance and frozen benchmark remain later milestones. Current
retrieval results and limits are in `docs/M3_1_REPORT.md`; claim counts are in `docs/M2_2_REPORT.md`.
All eight M2.3 development annotations are human-validated and final readiness is true; see `docs/M2_3_REPORT.md`.
Read `project_spec.md` and `AGENTS.md` before making changes.

## M1 baseline

The selected paper is [arXiv:2501.00309v2](https://arxiv.org/abs/2501.00309v2), a GraphRAG survey.
`manifests/pilot-paper.json` declares source hash, rights and partial page coverage (1–52).
Page 53's remaining discussion and reference-list pages are outside this pilot. Tables, diagrams
and equations are not independently verified. Reported studies remain attributed to the survey,
not treated as original experiments conducted by its authors.

Ensure the pinned PDF exists at `data/raw/arxiv-2501.00309v2.pdf`. If absent, download the manifest's
versioned URL there; ingestion rejects a hash mismatch. Use the locked environment and running local
Neo4j/Ollama services from setup below. Encoder artifacts must have passed the M0 artifact check.

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
$ingestReport = "runs/m1/ingest-$tag.json"
uv run --locked --offline python -m research_assistant ingest --manifest manifests/pilot-paper.json --output $ingestReport
$corpus = (Get-Content -Raw -LiteralPath $ingestReport | ConvertFrom-Json).corpus_id
uv run --locked --offline python -m research_assistant ask --corpus $corpus --question 'Which five components make up the holistic GraphRAG framework described in this survey?' --context-tokens 4096 --max-output-tokens 512 --output "runs/m1/answer-$tag.json"
```

`--offline` disables package-index access, not the deliberately selected local Neo4j/Ollama calls.
Paper/model downloads happen separately. No paid provider is selected or contacted by M1.
Use fresh report names: ingestion is idempotent, but run reports are never overwritten.
The public manifest and scientific source data are distinct; raw text/vectors/runs stay ignored in Git.
Frozen source metadata changes require a new snapshot identity, not an in-place rewrite.

Answers resolve only citation IDs actually shown in the six-unit/1,800-estimated-token context.
An unsupported question can return `insufficient_evidence=true`. Valid citation IDs do not prove
semantic correctness: the first development run found a real counterexample. See
`docs/M1_REPORT.md` for the failure, generic chunking fix, native usage/resources and verification.
The fixed evidence estimate is distinct from Qwen's native tokenizer; M1 uses a conservative context
preflight and native usage checks. CPU embeddings avoid competing with Qwen for scarce VRAM.

## M2.1 five-paper pilot

`manifests/pilot-five-papers.json` pins the five PDFs, rights, hashes and partial coverage.
Download missing PDFs separately from their versioned URLs to their declared local paths; ingestion
checks hashes. Selection is documented in `manifests/PILOT_SELECTION.md`; PDF inspection and known
reading-order/section-label limits are in `docs/M2_PDF_INSPECTION.md`.

OpenAlex metadata uses at most two bounded GETs per paper and caches successes/unknown outcomes.
`OPENALEX_API_KEY` is optional for the small basic lookups; stay within free access, never buy credits
automatically. A new metadata cache is an explicit refresh and changes the combined snapshot identity.
Bibliographic CITES edges are work-level discovery data, not proof about the pinned PDF's citations.

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
$metadata = "runs/m2/metadata-$tag.json"
uv run --locked --offline python -m research_assistant pilot-metadata --manifest manifests/pilot-five-papers.json --cache-dir data/metadata/pilot-v1 --output $metadata
$ingestReport = "runs/m2/ingest-$tag.json"
uv run --locked --offline python -m research_assistant pilot-ingest --manifest manifests/pilot-five-papers.json --metadata $metadata --output $ingestReport
$corpus = (Get-Content -Raw -LiteralPath $ingestReport | ConvertFrom-Json).corpus_id
$packets = "runs/m2/review-$tag"
uv run --locked --offline python -u -m research_assistant extract --corpus $corpus --plan manifests/pilot-extraction.json --bundle-dir $packets --output "runs/m2/extraction-$tag.json"
uv run --locked --offline python -m research_assistant review-check --bundle-dir $packets --output "runs/m2/review-check-$tag.json"
```

Extraction uses **EXTRACTION_PROVIDER/MODEL**, independently of generation. Local M2 limits are
4,096 context/1,024 output tokens, two candidates/request, eight cumulative requests per paper,
at most eight distinct passages and 12 candidates. The current plan selects four passages/paper.
Prompt amendment D22 and all initial empty/interrupted calls remain counted. No automatic model
retry, repair call, provider change or approval occurs. A started call without a response reserves
its possible candidates and is never repeated automatically. Per-PDF journals under
`data/extraction/by-source/` survive export/configuration/corpus metadata changes. Preserve them.

`extract` can reuse saved responses for a **new export directory**, with zero new inference for
already attempted requests. Configuration changes need a recorded amendment and cannot reset
the cumulative caps. It refuses to overwrite packets or decisions. Open `START_HERE.md`, then each
`REVIEW.md` and its `decisions.csv`. Decision/reviewer/time fields start blank; only humans fill
them. Proposed mappings have revision hashes. M2.2 will validate/import decisions; no scientific
Evaluation/Finding/FactText nodes are created in M2.1. Human review time is zero until actually recorded.

`review-check` is entirely offline: it replays source/quote identities, mapping revisions, CSV
bindings and cumulative caps. Passing it establishes mechanical integrity, not semantic support.
Model prompts/responses, source text, review packets and journals stay ignored in Git.

## M2.2 human review and approved facts

Current status: `docs/M2_2_REPORT.md`. The user prefers small in-chat batches. M2.1 packets remain
historical; the current revision/decision history is in ignored `data/reviews/pilot/`. Preserve it.
Review batches and exact revision bindings are under `runs/m2/m2-2-session/`; use the current
milestone report for the next batch. Reviewing one batch never approves unseen claims.

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
uv run --locked --offline python -m research_assistant review-prepare --bundle-dir runs/m2/review-final --review-dir data/reviews/pilot --output "runs/m2/prepare-$tag.json"
uv run --locked --offline python -m research_assistant review-status --review-dir data/reviews/pilot --output "runs/m2/status-$tag.json"
# For human-edited CSV input, use the head-addressed template returned by review-prepare:
uv run --locked --offline python -m research_assistant review-import --review-dir data/reviews/pilot --decisions <human-decisions.csv> --output "runs/m2/import-$tag.json"
# Proposed corrections require a new ReviewRevision, predecessor hash and human re-review:
uv run --locked --offline python -m research_assistant review-revise --review-dir data/reviews/pilot --revision <proposed-revision.json> --output "runs/m2/revise-$tag.json"
uv run --locked --offline python -m research_assistant review-sync --review-dir data/reviews/pilot --output "runs/m2/sync-$tag.json"
```

Existing preparation replays idempotently and exports current revision bindings. Human CSV rows
need explicit decision/reviewer/timezone-aware timestamp/reason and source/entity/revision hashes.
For unmeasured per-claim time, leave seconds blank and state that in `review_time_note`. Blank
decisions stay pending. Preserve in-chat responses in local receipts and import only the exact
explicit decisions; record batch durations once, without inventing per-claim allocations.

An edit or changed source/support/alias definition invalidates the old approval. Synchronization
rebuilds eligible FactText using CPU MiniLM, creates corpus-scoped active-only vector/full-text
indexes, and preserves inactive history. It makes **no LLM calls**. `fact-text-v1` shows canonical
method/dataset mappings and unknown conditions in the common evidence bundle. All future fact
retrievers must require the current local review head through `ReviewRepository.active_facts`;
unsynchronized or rolled-back history fails closed. Never query stale approved rows as a fallback.
Overlong embedding input requires revision; it is never silently truncated.

Optional isolated review integration fixture (synthetic decisions, no production approvals):

```powershell
$env:RUN_REVIEW_SMOKE = '1'
uv run --locked --offline pytest -m integration tests/integration/test_review_repository.py
Remove-Item Env:RUN_REVIEW_SMOKE
```

The fixture removes only its UUID-owned synthetic nodes/indexes. It never resets application data
or volumes. M2.2 has 23 current human-approved facts across five papers; two GraphRAG drafts remain
pending at the initial review timebox. See `docs/M2_2_REPORT.md` and the local handoff index
`runs/m2/m2-2-session/FINAL_STATUS.md`. M3.1 retrieval is implemented; later checkpoints are below.

## M2.3 development gold validation

Eight human-validated development annotations and their exact source spans are local under
`data/evaluation/development/pilot-v1/`. `questions.jsonl` contains stripped requests;
`annotations.jsonl` contains reviewed reference answers and gold supports for evaluation only.
Never pass annotations or gold answers to retrieval/generation. Real artifacts and human receipts
remain outside Git. Held-out inputs stay in the evaluator-controlled external directory, untouched.

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
uv run --locked --offline python -m research_assistant dev-check --dataset-dir data/evaluation/development/pilot-v1 --output "runs/m2/dev-check-$tag.json"
```

The command checks immutable hashes, sources, category allocation, source-context feasibility and
recorded human validation. It makes no model/database calls. A successful mechanical check does
not mean the gold is human-validated; inspect `review.ready` and the per-question status.
Review packets are `review-batches/batch-01` through `batch-04` inside that dataset directory.
Use `docs/M2_3_REPORT.md` for current status. Changes require a new immutable dataset version and
fresh validation. Gold decisions do not approve graph claims or reopen extraction/review caps.
The creation manifest's draft label is historical; current readiness is determined by source/hash
checks and exact-bound receipt replay. `runs/m2/m2-3-session/acceptance.json` records development
acceptance, which is separate from M4's final-evaluation freeze. M3.1 is complete; expansion stays closed.

## M3.1 controlled retrieval

`vector`, `hybrid`, `hybrid_facts` and `graph` call the same evidence renderer/packer. Vector retains
the M1 threshold; the other semantic channels use fixed top-12 rankings and RRF. Graph starts with
the identical Hybrid + Facts pool and adds only current, source-backed approved targets. See the
spec and `docs/M3_1_REPORT.md` for selection rules and actual query-plan checks.

```powershell
$corpus = '74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329'
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
# Explicit setup adds missing indexes; it does not reset or reingest source/claim data.
uv run --locked --offline python -m research_assistant search-setup --corpus $corpus --output "runs/m3/setup-$tag.json"
# Retrieval only: no generator or paid calls.
uv run --locked --offline python -m research_assistant retrieve --corpus $corpus --mode graph --review-dir data/reviews/pilot --question 'Which methods were evaluated on MuSiQue?' --output "runs/m3/retrieve-$tag.json"
# Answer generation is a separate explicit command using configured local Qwen.
uv run --locked --offline python -m research_assistant ask --corpus $corpus --mode graph --review-dir data/reviews/pilot --question 'Which methods were evaluated on MuSiQue?' --output "runs/m3/answer-$tag.json"
```

`--mode` defaults to `vector`. Fact modes require the matching current review store; they hold its
lock and check graph/source/approval bindings. Stale or unavailable services/indexes fail explicitly.
Queries never prepare indexes or synchronize approvals automatically. Setup rejects frozen/unready
targets. `--minimum-similarity` applies to Vector only. `GRAPH_QUERY_TIMEOUT_SECONDS` defaults to 30;
0.001–30 seconds is allowed and applies to the whole retrieval read transaction. Timeout monitoring
is not a strict wall-clock SLA. Gold/reference answers must never be passed to retrieval/generation.

Outputs expose requested/effective mode and fallback reason. Graph returns the exact Hybrid + Facts
assembly if no new graph item survives selection/unit/token limits. All eight actual development
Graph reads did so; there is no observed added graph evidence in this pilot. A separate native
synthetic fixture proves new cross-paper traversal outside the fused baseline pool. Development
scores are exploratory; no generation/held-out superiority claim is made.

Optional isolated native fixtures (synthetic approvals only):

```powershell
$env:RUN_RETRIEVAL_SMOKE = '1'
$env:RUN_REVIEW_SMOKE = '1'
try {
    uv run --locked --offline pytest -m integration tests/integration/test_graph_retrieval_repository.py tests/integration/test_review_repository.py
} finally {
    Remove-Item Env:RUN_RETRIEVAL_SMOKE
    Remove-Item Env:RUN_REVIEW_SMOKE
}
```

An optional `M3_FIXTURE_REPORT` must name a fresh report path. Fixtures remove only their UUID-owned
nodes/indexes; existing corpora, review history, volumes and shared schema are preserved. The
deadline fixture uses a bounded three-second idle interval. Reports and real source/run data stay
ignored locally. M3.2 workflows/export are implemented below; next is M3.3 integrations and restore verification.

## Research workflows and evidence export (M3.2)

With Neo4j healthy and the pilot source/review caches present, launch from the project root:

```powershell
uv run --locked --offline streamlit run src/research_assistant/ui/app.py
```

Open `http://127.0.0.1:8501`. Discovery, comparison and limitations have editable starter questions;
Ask accepts a free-form question. Select any of the four retrieval modes. Synthesis is disabled by
default: enable it to use the configured local Qwen (context 4096, output 512, no automatic retry).
Submission runs the shared query service; changing controls or downloading never repeats inference.
The displayed result retains its actual submitted question/mode until another successful query.
Runs are saved under ignored `runs/ui/<run-id>/run.json`; generation failures preserve available raw
responses in `failed-run.json`. No application data is deleted or reset by the UI.

The page separates approved claims, raw excerpts, selected graph paths and LLM synthesis. Structured
rows use only selected approved claims matching explicitly mentioned reviewed method/dataset identities.
Conditions remain per claim/reporting paper; unknown fields do not become known from a different row.
Comparison notices qualify missing/differing conditions and prohibit unsupported numerical ranking.
PDF page links are primary; parsed sections and numerical tables remain unverified. Requested/effective
mode and graph fallback stay visible. Approval changes or unavailable current projection disable display
and export until a fresh query passes validation. Previously downloaded files remain historical snapshots.

Use the checked download buttons, or export a shared `RunArtifact` saved by `ask`, `retrieve` or the UI:

```powershell
uv run --locked --offline python -m research_assistant export-evidence --run <saved-run.json> --output <new-evidence.csv>
```

CSV has one row per actually shown excerpt: paper, source URL/PDF page, approved claim/revision (blank
for raw excerpts), JSON conditions, exact quotation, source hash/chunk/offsets, paths and run/mode/context
identity. UTF-8 CSV quoting preserves commas/newlines. Spreadsheet-sensitive cells receive a leading
apostrophe; `escaped_fields` names these fields so removing exactly one apostrophe recovers original text.
The run JSON always retains verbatim quotations. Export rechecks shared source/context/current-review
rules; it performs no retrieval, generation, approval or write to Neo4j. A failed export creates no CSV.
Earlier M3.1 diagnostic retrieval JSON remains historical; use a new `retrieve` run for this export schema.

Reproduce bounded product checks (fresh output directory required):

```powershell
uv run --locked --offline python scripts/accept_m3_2.py --output-dir runs/m3-2/<new-check>
# Optional: one local call per scenario, at most four, with no retries or paid calls:
uv run --locked --offline python scripts/accept_m3_2.py --output-dir runs/m3-2/<new-local-check> --generate
# Repeat only a changed scenario when needed: add --scenario abstention
```

See `docs/M3_2_REPORT.md` for actual checks, the corrected abstention behavior and remaining limits.
Product availability is not a semantic answer-quality score; M3.3 and the full expansion gate remain open.

## Source/evidence contracts

`contracts.py` defines immutable-source identities, exact excerpt spans, future human review records,
retrieval/answer/run artifacts and independent gold annotations. `evaluation/scoring.py` only scores
provided annotation/context objects; it never supplies gold answers to retrieval or generation.
Raw and approved-fact source spans receive identical credit. M1 tests use synthetic gold data;
M2.3 supplies eight human-validated real development annotations. Held-out execution remains M4 work.

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
