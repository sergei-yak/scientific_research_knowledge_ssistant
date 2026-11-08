# M1 one-paper vector baseline

**Outcome:** The selected paper runs through local PDF parsing, dual-tokenizer-safe chunking,
MiniLM embeddings, Neo4j vector retrieval and cited local-Qwen answers. M1.1/M1.2 are complete;
M2 review, other retrievers and the final benchmark have not started.

## Paper and scope

The user suggested [Retrieval-Augmented Generation with Graphs (GraphRAG)](https://arxiv.org/abs/2501.00309),
by Haoyu Han and colleagues. The downloaded source is pinned to **2501.00309v2**:

- PDF SHA-256: `737b0b8fe0aa8459429b5906d66d0bfcb5246c488add534d3ce23f58a0f7b7fc`.
- 88 pages total; this pilot indexes **pages 1–52 only**. Page 53 contains final discussion and the
  beginning of references; that page and the rest of the bibliography are omitted. This is partial
  coverage, not a claim that the entire main body was indexed.
- Source/version/license/selection details: `manifests/pilot-paper.json`. The PDF is local and ignored
  by Git; the arXiv distribution license is recorded, not interpreted as an unrestricted reuse license.
- Visually inspected the framework page and checked extracted text/normalization. All selected pages
  produced text; no Unicode replacement characters were found after extraction. This does not certify
  formulas, diagrams, table reading order or numerical results. Line-wrap hyphen artifacts can remain.
- It is a **survey**. Descriptions of other studies must not become experiments owned by this paper.
  No claims have been human-approved or inserted as scientific facts.

## What was implemented

- Strict source/claim/review/evidence/request/result/run contracts and a separate human-score shape.
- Graph-independent gold annotation/scoring with source hashes and exact normalized offsets,
  alternative sufficient fact sets, OR passage alternatives and AND multi-passage support. Identical
  page spans can be credited across overlapping chunk windows; graph claim IDs never grant credit.
- Soft section-aware, page-local windows: at most 200 MiniLM tokens, within MPNet's input limit,
  approximately 40 MiniLM-token overlap, fixed source hashes/offsets and deterministic IDs.
- Corpus-scoped vector indexes, immutable-source ownership guards, parameterized writes and
  idempotent ingestion. Existing snapshots are retained; no database/data reset was performed.
- A shared six-unit/1,800-estimated-token assembler and renderer, overlap removal, source references,
  citation-ID resolution and explicit abstention. All shown metadata/paths are counted.
- An `LLMClient` protocol and selected Ollama adapter with validated structured JSON, pinned runtime
  identity, zero retries/provider switching, context/output preflight and native usage records.
- CLI `ingest`/`ask` and immutable success/failure artifacts. Full prompts, shown context, candidate
  ranks, citations, source-tree fingerprint, model identity/settings, resources and timings are saved.

The M1 design bindings for future RRF, FactText embedding text, graph templates and candidate
selection live in `IMPLEMENTATION_PLAN.md`. Only vector search runs in the application at this stage.

## Real development checks

Final corpus: `23fb546e11aeb14b2737c238ddea9d23f5f86aeb5f4f4dea5dab84a55501f146`.
Final index: `ra_mini_23fb546e11aeb14b`; **325 chunks**, maximum observed MiniLM/MPNet lengths 200/200.

| Check | Observed outcome / ignored local evidence |
|---|---|
| Initial ingestion and rerun | First chunker: 352 chunks; same ID/count on rerun. `runs/m1/ingest-first.json`, `ingest-repeat.json`. |
| Revised ingestion and rerun | 325 chunks; identical final corpus ID/count. `ingest-soft-sections.json`, `ingest-soft-repeat.json`. |
| Framework question | Correct five-component answer; source passages on pages 1, 3 and 5. Six units, 1,107 estimated evidence tokens; native input/output 1,328/74. `framework-answer-v2.json`. |
| Unsupported training GPU-hours | Qwen explicitly abstained with no supporting citations, despite six retrieved units. 1,392 estimated evidence tokens; native input/output 1,766/47. `insufficient-evidence.json`. |
| New adapter text method | Returned `READY`; native input/output 19/2. `adapter-text.json`. Structured method exercised by both QA runs. |
| Context/source integrity | Reconstructed the actual contexts, revalidated run models, checked candidate membership and all excerpt offsets against cached chunks. Both final QA artifacts passed. |
| Offline tests | **41 passed, two integration cases deselected** via `uv run --locked --offline pytest -m "not integration"`. PyMuPDF emitted upstream SWIG deprecation warnings. |
| Environment consistency | `uv lock --check --offline` passed (95 resolved packages); `uv pip check` passed (79 installed packages). No locked package versions changed. |

These are development smoke checks, not the frozen 24-question evaluation or human-approved gold
annotations. No held-out inputs were created/read. No paid requests or OpenAI provider calls occurred.

The final saved-run replay also passed against the current contracts. Direct Python utilities must
call `settings.configure_caches()` before counting tokens: an initial ad-hoc replay omitted this,
attempted the default tokenizer download and failed DNS; the corrected replay used the existing
project cache successfully. The CLI configures that cache; offline unit fixtures inject
deterministic counters instead of downloading tokenizer artifacts.

### A real failure retained

The first framework query produced an incorrect component list even though its citation IDs were
valid (`framework-answer.json`). Its six slots over-selected short captions/headings and omitted the
explicit list at rank eight. Thus citation existence alone demonstrably does **not** ensure semantic support.

The generic fix was soft section boundaries: short adjacent captions/headings share useful context,
while respecting page/source/token limits. The chunker version and corpus identity changed; the
original 352-chunk snapshot (`fc41008b57b270d491669d0fffa5de082ee6b653dac5c64b8be45ede1fec0640`)
and failed answer were preserved. No paper-specific ranking weight or hidden source passage was added.
The same question then retrieved the explicit definition. This development change is not an unbiased
performance comparison; full comparative evaluation remains M4.

## Resources and limitations

Both QA runs used CPU MiniLM plus local Qwen 27.3B Q4_K_M, temperature zero, thinking disabled,
**4,096 context tokens / 512 maximum output tokens**. The model digest remained
`22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643` and the server reported a
4,096-token loaded context. M0's smaller probe settings are separate from these explicit CLI defaults.

The supported/abstaining runs took about 36.8/20.3 seconds for generation and 245/238 ms for retrieval
after encoder initialization. Available RAM after generation was about 5.05/4.62 GB; total GPU use
11,707/11,754 MiB. These individual measurements include cache/load effects and are not benchmark averages.
Native input plus reserved output remained well below context capacity. The shared estimator is still
an estimate, not proof of native-token equivalence for arbitrary languages or longer inputs.

Remaining: human claim review and real gold annotation, five-paper coverage, hybrid/graph retrievers,
OpenAlex metadata enrichment, UI and frozen evaluation. M2 must version the manifest/snapshot identity
when extending immutable metadata rather than overwrite an existing snapshot. OpenAI live integration
is still pending its credentials/budget. Code revision
and dirty-tree/source fingerprints are included in the development artifacts; the local M1 checkpoint
records the final implementation. NumPy was declared directly without changing locked package versions.

## Pending checks and blockers

- **No M1 blocker remains.** Existing PDFs, corpus snapshots, failed runs and database volumes were preserved.
- OpenAI live text/structured checks remain **pending**, with no credentials/approved numerical budget;
  they are required by M3.3 and do not block the selected local baseline.
- The two optional M0 pytest integration cases were deselected in the offline suite; the M1 ingestion,
  retrieval and local-Qwen commands exercised those services directly. This is not a claim that every
  integration test was rerun.
- Human claim approval, real gold annotations, the remaining four pilot papers, graph/query-plan checks,
  recovery testing and frozen evaluation have not run; they belong to M2–M4.
