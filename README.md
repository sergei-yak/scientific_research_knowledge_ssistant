# Scientific Research Knowledge Assistant

Current implementation: **M0–M4.3 complete; frozen evaluation scored and reported**.

**Current iteration:** Specification 6.5 governs `retrieval-v2`; M5.0–M5.4 are complete.
[M5.4](docs/M5_4_REPORT.md) records the matched 96-request development comparison and a **no-go**
for a larger fresh Graph answer study under the tested original-51/catalog route+selector hypothesis.
Development checkout: `C:/Users/serge/DBU-GraphRAG-Worktrees/retrieval-v2-m52-54d8b329`;
the original OneDrive checkout preserves baseline code/data. Use the development checkout for V2.
The user subsequently requested **M5.5 readiness preparation**; specification **6.5** retains a
preparation-only exception while preserving that negative gate. The [proposal](docs/M5_5_STUDY_PROPOSAL.md)
and [status](docs/M5_5_REPORT.md) disclose pending fresh evaluator, implementation, restore and authorization
gates. The 12-condition/288-request matrix is proposed only; no fresh final run is authorized.
The user accepted the new drafts with an explicit exploratory author-context limitation; read the
[mandatory study amendment](docs/M5_5_STUDY_AMENDMENT.md). Human source approval and final execution remain pending.
**M6** is reserved for product demonstration readiness and has not started.
The development UI is on port 8502.
The [archived 6.1 specification](docs/baselines/project_spec_v6_1.md) governs the completed baseline;
existing `freeze-v2.json` is consumed and unrelated to the new profile name. No new generation/final
study is authorized. Existing defaults retain baseline/reference behavior.

From the development checkout, retrieve V2 evidence with a fresh output path:

```powershell
Set-Location 'C:/Users/serge/DBU-GraphRAG-Worktrees/retrieval-v2-m52-54d8b329'
uv sync --locked --offline
docker compose -p dbu-m4-recovery-m5dev-2d43d2b9a2fa up -d --pull never neo4j
uv run --locked --offline python -m research_assistant retrieve --profile retrieval-v2 --scope-file data/scopes/retrieval-v2.json --corpus 298e3cafbda1ffdf95c8ee66fa2b9ba3a81dc8d5e26bfb94816655ca41de3fbf --review-dir data/reviews/expansion-v1 --mode graph --question 'Which methods were evaluated on MuSiQue?' --output runs/my-new-v2-query.json
```

The scope file, data and credentials are local ignored assets. V2 rejects a different endpoint/head;
UI corpus/profile selection is explicit, with the pilot default retained. V2 synthesis stays disabled
until its later gates. The native fixture uses `RUN_V2_SMOKE=1` and cleans only UUID-owned test data.

For the common reranker, add `--selector cross_encoder` to the V2 retrieve command in any of the
four modes, or select **Shared reranker** under **Evidence ordering** in the UI. The local pinned
model manifest records seven assets (~87.6 MiB), native 512-token pairs and CPU/runtime policy.
Oversized inputs or missing/changed assets fail explicitly; queries never download or substitute a
model. `reference` remains available independently. Reranking preserves the same evidence budgets,
source/approval guards and exact same-selector Graph fallback. The completed development comparison
finds no incremental registered Graph support; the reranker lowers mean fact-mode evidence recall
on the six answerable questions. Keep reference defaults; no answer-quality improvement is established.

Completed M5.4 artifacts are under `runs/retrieval-v2/m5-4/`: 96 saved runs and once-only receipts,
offline candidate/final source-span scores, 24 separate plan probes, tests, UI and acceptance/handoff.
Do not rerun `scripts/run_m5_comparison.py` on the completed `comparison-v1` matrix or overwrite scores.
Candidate recall measures an unbounded excerpt union; final Recall@6 measures actual shown evidence.

Four retrieval conditions, Streamlit workflows and checked evidence export operate on the five-paper
pilot. Both provider adapters and budget controls are implemented; local probes and an isolated logical
restore passed. Both OpenAI live probes passed after the user replaced an expired key. The configured
generator remains local Qwen. See `docs/M3_2_REPORT.md` and `docs/M3_3_REPORT.md` for actual outcomes;
M4.1 selection, 20-paper ingestion, expansion-claim review and all eight expanded development-gold
validations are complete; all 16 private annotations have human approval and public 24-question readiness is attested. M4.2 is complete, including exact-V2 human authorization. M4.3 execution passed: 96 answer runs / 48 encoder reads / zero failures / $0 paid. All 96 human scores validated/sealed before aggregate reveal. See [final research results](docs/FINAL_EVALUATION_REPORT.md) and `docs/M4_3_REPORT.md`.
All eight M2.3 pilot development annotations also remain human-validated; see `docs/M2_3_REPORT.md`.
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

After changing shared package interfaces, stop Streamlit with `Ctrl+C` in its terminal and repeat the
launch command. A browser refresh or Streamlit rerun can retain previously imported Python modules.
If a newly added symbol imports in a fresh Python process but fails in the running app, restart the
app server, then verify an actual page/query; the HTTP health endpoint alone does not execute the app.

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
Product availability is not a semantic answer-quality score. M3.3 subsequently passed the five-paper gate; see `docs/M3_3_REPORT.md`.

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
The M0 `smoke --checks openai` probe remains configuration-only and makes **zero paid requests**.
M3.3 adds explicit live adapter probes through `provider-check`; no provider is substituted on failure.
An API key alone does not authorize spending. Source/package changes require a Streamlit restart
before handoff, as described above.

```powershell
uv run --locked --offline python -m research_assistant provider-check --providers ollama openai --output <new-report.json>
```

Each requested provider receives at most two inference operations: plain text and validated JSON.
CPU MiniLM remains resident, performs inference between calls, and Neo4j is checked with real vector
retrieval. Unavailable authorization/credentials are recorded as pending; failed probes preserve available
raw replies and errors. The report records usage, model identity, settings and resource observations.
Cloud identity is the provider-reported model identifier, not a weights checksum.

Paid calls require `API_BUDGET_APPROVED`, `API_BUDGET_USD`, `API_MAX_REQUEST_USD`,
`API_MAX_REQUESTS`, `API_BUDGET_SCOPE`, `MAX_OUTPUT_TOKENS`, `MAX_CONCURRENCY=1` and
`MAX_RETRIES=0`, all within the user's actual authorization. A recorded M3.3 approval can instead
be supplied with `provider-check --approval <local-approval.json>`; it applies only to readiness
probes, without changing `.env` or permitting paid application generation/extraction.

The fixed project ledger `data/accounting/openai.jsonl` uses an exclusive cross-process lock and
hash-chained durable reservations before each call. All attempts count; failed/unknown outcomes retain
the whole reservation. Reservations are conservative upper bounds, not invoices. Changing a receipt,
client or working directory never clears consumption. Do not remove the journal or a stale lock to
regain budget. Readiness probes send fixed dummy prompts, not research/evaluation answers.

The current adapter supports the explicitly configured `gpt-6.1-terra` through the Responses API,
with no hosted tools, storage, automatic truncation or SDK retries. Fixed-field schemas use strict
structured output; free-form mapping schemas use explicitly logged JSON mode and full Pydantic
validation. Invalid/incomplete/refusal responses fail and preserve their reservation/raw result.
Rates were checked on 2026-11-08; the conservative bound uses $5/million for both input and output
tokens, with extra protocol allowance and a 64 KiB input ceiling. Paid execution requires price review
again after 14 days. See the official [model/rates](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
and [structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Logical snapshot and isolated recovery (M3.3)

Quiesce ingestion/review/paid writers and finish fact-mode queries before export. The shared review
lock briefly blocks fact-mode queries while the snapshot is copied. Export into a fresh directory;
the service verifies current approvals, checks the graph before/after copying and rejects changing assets.

```powershell
uv run --locked --offline python -m research_assistant snapshot-export --snapshot-dir <new-snapshot-directory> --output <new-export-report.json>
uv run --locked --offline python scripts/recover_pilot.py --snapshot-dir <snapshot-directory> --output-dir <new-recovery-report-directory>
```

The snapshot includes all project-owned current/historical nodes, relationships and embeddings;
schema/index metadata; pinned source PDFs/manifests/caches; review/extraction/accounting journals;
development annotations/receipts; saved development contexts; application/configuration/test code and
the lockfile. File hashes, semantic graph hash and manifest hash are recorded. API/database secrets,
held-out files and model caches are excluded. Recovery requires the locked Python environment and
separately cached pinned encoder weights. Copied development gold is used only by scoring.

The runner creates a unique `dbu-m3-recovery-*` Compose project with **new** data/log volumes,
using the pinned Neo4j image and loopback ports 8765/8475 (override with `--bolt-port`/`--http-port`).
Restore verifies container/endpoint/volume identity and refuses the source endpoint, nonempty
targets or existing application schema. It never deletes/resets working data. It reconstructs only
allowlisted labels/types/schema with parameterized property data, then awaits ONLINE indexes.

The runner checks exact semantic graph/schema equality, uses the copied source/review assets for
32 fresh development retrievals, reproduces all 32 saved-context scores, runs discovery/comparison/
limitations/export and executes the two UUID-owned native guards against the restored database.
Rebuilt approximate indexes may return different contexts; saved contexts/scores remain authoritative.
The target is stopped afterward and its volumes/reports retained. `target.json`/`report.json` record
commands, ports, container/image/volume identities and outcomes. No working-database downtime is needed.

For an already-created **fresh, empty, attested** target, the lower-level operation is:

```powershell
uv run --locked --offline python -m research_assistant snapshot-restore --snapshot-dir <snapshot-directory> --target-uri bolt://127.0.0.1:8765 --target-project <dbu-m3-recovery-unique-name> --output <new-restore-report.json>
```

Restoring never re-enables paid access. Reconcile any newer live budget reservations before authorizing
paid operations from recovered files. Native offline dump/load is optional and was not exercised here;
it requires a separate downtime plan and fresh target. M4 still owns final corpus selection/freeze/evaluation.

## M4.1 expansion and evaluation readiness

See [M4.1 outcomes](docs/M4_1_REPORT.md), [pre-recorded selection](manifests/CORPUS_SELECTION.md)
and [evaluator handoff](docs/EVALUATOR_HANDOFF.md). The 20-paper corpus has 1,427 chunks;
all 28 expansion claims are human-approved (51 active claims including the pilot). All eight expanded
development annotations and all 16 isolated AI-authored private annotations are human-validated.
The evaluator imported an explicit exact-bound statement by Sergei Iakovlev and recorded approximately
30 minutes total private review; blank forms/pending reports remain historical. Public bindings/schema
checks pass; `runs/m4-1/evaluation-readiness-manifest.json` commits 24 questions, six per category.
See the evaluator handoff and `runs/m4-1/final-acceptance.json` for checks and limits. Private inputs stay external.
Only the exact-V2 local final study is authorized; no further paid calls. The UI keeps the five-paper pilot default.

Use an explicit scope for expanded retrieval; synthesis is not requested by this command:

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
uv run --locked --offline python -m research_assistant retrieve --corpus 298e3cafbda1ffdf95c8ee66fa2b9ba3a81dc8d5e26bfb94816655ca41de3fbf --review-dir data/reviews/expansion-v1 --mode hybrid_facts --question "How do the reviewed methods retrieve evidence?" --output "runs/m4-1/retrieve-$tag.json"
uv run --locked --offline python -m research_assistant dev-check --dataset-dir data/evaluation/development/expansion-v1 --output "runs/m4-1/dev-check-$tag.json"
```

Reconstruction entry points (cached PDFs and their declared source hashes are prerequisites):

```powershell
uv run --locked --offline python -m research_assistant corpus-metadata --manifest manifests/expanded-twenty-papers.json --cache-dir data/metadata/expansion-v1/openalex --output <new-metadata.json>
uv run --locked --offline python -m research_assistant corpus-ingest --manifest manifests/expanded-twenty-papers.json --metadata <metadata.json> --output <new-ingestion-report.json>
uv run --locked --offline python -m research_assistant review-extend --source-dir data/reviews/pilot --review-dir <new-review-store> --corpus <expanded-id> --output <new-scope-report.json>
```

Metadata commands make bounded live lookups only for missing cache entries; uv's `--offline`
controls package resolution, not service networking. Existing snapshots, volumes and review stores
are preserved. Corpus ingestion checks the recorded selection protocol hash. The extraction run
is already saved under `runs/m4-1/claim-packets/`; do not rerun merely to review it.
If an explicitly amended extraction is needed, `extract --selected-papers` accepts the plan's
nonempty subset without resetting the global per-PDF ledger.

`review-check` audits packets; `review-prepare` registers candidates into the matching review
scope; neither grants approval. Use the existing review-import/chat-receipt workflow for actual
human decisions, then `review-sync --review-dir data/reviews/expansion-v1 --output <new-report.json>`.
The original review queue is `runs/m4-1/review-batches/queue.json`; `mapping-proposals.json` records packet replacements; hash-bound `packet-amendments/` records supersede them when a pending claim is narrowed again. `scripts/update_m4_review_progress.py` derives a head-addressed checkpoint under `runs/m4-1/review-progress/`; immutable packets and prior checkpoints remain historical.
Current eligibility comes from journal replay, not an old queue label or packet.
The current human-validated development annotations are in `data/evaluation/development/expansion-v1/`.
The earlier `expansion-v1-draft` and `pilot-v1` directories remain preserved; their decisions do not
grant validation to the new dataset. Four fresh review batches total approximately 65 minutes of
gold review, separate from approximately 133 minutes of expansion claim review. Current source/receipt
replay reports 8/8 validated and ready; see `runs/m4-1/development-gold-acceptance.json`.
The additional private review total is approximately 30 minutes, with per-question/per-batch time unknown.
The progress helper validates the named public attestation's hash/current bindings and reports M4.1 done;
it never reads private evaluation inputs.
Repeat engineering verification with `uv run --locked --offline python scripts/check_expansion.py
--output-dir <new-report-directory>`; it preserves prior reports and makes no generation calls.

The development-only scoring API is `evaluation.blinding`: `build_development_bundle`,
`seal_development_scores`, then `reveal_development_scores`. It refuses private/external paths,
incomplete matrices, missing generation responses and inconsistent comparison settings. Only
humans fill real scoring forms. `pytest tests/test_m4_readiness.py` exercises synthetic fixtures;
those fixture scores do not enter project results. The dedicated frozen runner below is implemented;
one exact-V2 local execution completed; do not restart the used freeze.

## M4.2 separate encoder and frozen evaluator

Current verified proposal: [run plan](docs/M4_2_RUN_PLAN.md), [actual checks/limits](docs/M4_2_REPORT.md),
`runs/m4-2/freeze-v2.json` (SHA-256 `62feb4b684efda52fa3b85e4e9b1283ead51aa944a31dae87f2b7ccc00770942`).
V1 is historical/superseded before execution. The restored V2 target retains its read-only configuration and volumes; only the authorized runner starts/stops it.
The authorized study completed (`runs/m4-3/execution-outcome-v2.json`); target stopped and working graph unchanged. Do not launch an additional execution.

The working application keeps its existing MiniLM modes. MPNet is a separate retrieval-only experiment:

```powershell
uv run --locked --offline python -m research_assistant embedding-setup --corpus <corpus-id> --output <new-report.json>
uv run --locked --offline python -m research_assistant retrieve-embedding --corpus <corpus-id> --encoder mpnet --question <question> --output <new-report.json>
```

`embedding-setup` never deletes/replaces baseline vectors or source chunks. It refuses frozen or conflicting
targets. The cached 768-D vectors bind the same normalized source snapshot and pinned encoder revision.
MiniLM and MPNet use the same vector ranking, threshold, source validation and packing functions.

Logical frozen export/recovery (fresh report directories and cached source/model prerequisites):

```powershell
uv run --locked --offline python -m research_assistant snapshot-export --review-dir data/reviews/expansion-v1 --freeze-corpus --snapshot-dir <new-snapshot-dir> --output <new-report.json>
uv run --locked --offline python scripts/recover_corpus.py --snapshot-dir <snapshot-dir> --output-dir <new-recovery-dir>
uv run --locked --offline python -m research_assistant freeze-prepare --snapshot-dir <snapshot-dir> --recovery-report <recovery-report.json> --private-root <external-evaluator-root> --freeze-output <new-freeze.json> --output <new-report.json>
uv run --locked --offline python -m research_assistant freeze-verify --freeze <freeze.json> --output <new-report.json>
```

These preparation commands never read held-out content. The export changes only the target copy's
`Corpus.frozen` flag; recovery uses UUID-owned volumes on ports 9765/9475, tests both encoders and copied
development scores, enables server-enforced read-only access, then stops/retains that target. It never
resets working data or existing volumes. `NEO4J_READ_ONLY` defaults false for the working service.

The evaluator-only runner is `uv run --locked --offline python -m research_assistant.evaluation.runner --help`.
Its `run`, `seal` and `reveal` operations require the exact public freeze and a real numerical human
authorization receipt. It refuses private-path access before authorization; new output directories or
receipts do not reset a started freeze's durable execution ledger. One exact-V2 local study is now authorized
and completed; no retry or additional started execution is authorized.
All runs, failure diagnostics, scoring packets (including their `public/` subdirectory), gold and reveal
maps stay in the external evaluator root. Only aggregate status/hashes return to development.
Complete human scores must be sealed before revealing any condition results. An interrupted/failed
started study is preserved and requires a disclosed amendment; there is no automatic retry/resume.

Frozen executable/model bytes and runtime versions govern code identity. A later documentation-only Git
commit is allowed when all frozen executable/model/configuration hashes still match; both frozen and
actual execution revisions are recorded. Current checks: 190 offline passes; three separately enabled
native cases; 40 exact saved-score replays and 40 fresh restored-target reads. Five fresh contexts/two
recalls differ after index rebuild. Two local development-generation smoke checks and a restarted UI
query pass. Those are preparation checks; the separately authorized final study and human scoring are now complete.

M4.3's authorized execution has now completed: 96 answer runs, 48 separate vector-only reads,
zero failed/unknown attempts, $0 paid; working graph unchanged and evaluation target stopped.
All 96 actual human judgments have now validated and been sealed before guarded reveal. See
[final research results](docs/FINAL_EVALUATION_REPORT.md) and [M4.3 audit](docs/M4_3_REPORT.md).
Hybrid has the highest mean human correctness on this small held-out set; Graph falls back24/24,
with identical fact-ablation contexts, so no selected-traversal benefit is demonstrated. The original
[scoring guide](docs/M4_3_SCORING_GUIDE.md) remains procedural documentation. The blank handoff is
historical; current receipt/results are `runs/m4-3/scoring-finalization-outcome-20261115T035119990546Z.json`
and `aggregate-results-20261115T035119990546Z.json`. Do not repeat immutable exports or the consumed study.

Actual task outcomes, limitations and evidence paths are maintained in `IMPLEMENTATION_PLAN.md`.
Dependency, Docker and model downloads may need network access; service checks need local
Docker/Ollama access. A sandbox permission failure is not proof that a service itself is broken.

Technical sources: [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/),
[uv PyTorch integration](https://docs.astral.sh/uv/guides/integration/pytorch/),
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
