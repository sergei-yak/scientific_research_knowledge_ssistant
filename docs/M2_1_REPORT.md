# M2.1 bounded five-paper evidence pilot

**Outcome:** Five pinned papers are ingested and complete, unapproved review packets are prepared
using local Qwen. **M2.1 is complete; the full M2 acceptance gate is not passed.** Human decisions,
repairs/revisions, approval import and development gold annotations remain M2.2/M2.3.

## Sources and snapshot

Selection preceded extraction; see `manifests/PILOT_SELECTION.md`. The user-selected survey is
joined by original GraphRAG, HippoRAG, LightRAG and HippoRAG 2 papers. The four additions use their
first arXiv versions for a consistent historical selection, not the latest published versions.

| Paper | Pinned version | Retrieval pages | Chunks |
|---|---|---|---:|
| GraphRAG survey | 2501.00309v2 | 1–52 of 88 | 325 |
| From Local to Global (GraphRAG) | 2404.16130v1 | 1–11 of 15 | 62 |
| HippoRAG | 2405.14831v1 | 1–10 of 28 | 59 |
| LightRAG | 2410.05779v1 | 1–10 of 16 | 66 |
| From RAG to Memory (HippoRAG 2) | 2502.14802v1 | 1–8 of 18 | 59 |
| **Total** | **Five papers** | **91 selected pages** | **571** |

PDF hashes/rights/coverage: `manifests/pilot-five-papers.json`. Sources remain local and ignored;
the licenses are recorded without treating arXiv distribution permission as unrestricted reuse.
Title/method/setup/limitations pages were visually inspected; details and omissions are in
`docs/M2_PDF_INSPECTION.md`. All selected pages yielded text and zero replacement characters.
Neither tables, diagrams nor equations are certified for numerical extraction. Line-wrap artifacts
remain. HippoRAG 2's section heuristic incorrectly retains “Front matter”; packets disclose this and
use exact page locations. Its final conclusion tail is omitted with the mixed bibliography page.

Combined corpus: `74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329`.
Index: `ra_mini_74260b76836e2974`. Both it and the original 325-chunk M1 index are `ONLINE`.
The combined identity includes the full source manifest, frozen bibliographic metadata and member
snapshots. M1's corpus/chunks and the earlier failed M1 development snapshot remain preserved.

Five bounded anonymous OpenAlex singleton requests matched five works and supplied **six positive
work-level CITES edges**. Public provenance is in `manifests/pilot-bibliography.json`; full cached
responses are ignored in `data/metadata/pilot-v1/`. Conference DOIs/years can differ from pinned
arXiv versions. Missing edges remain unknown, including possible duplicate-work mismatches; these
edges neither prove a PDF-version citation nor approve scientific claims. Current access reference:
[OpenAlex authentication](https://help.openalex.org/api/authentication/).

## Bounded local extraction: actual outcomes

The frozen selection has **four paragraph/section-aware passages per paper**, at most 600 common
estimated tokens each. Passages are separate from the frozen 200-token retrieval chunks; short
prose paragraphs stay short to avoid adding adjacent tables or interleaved columns. Other sections
and intervals are uncovered, including other text on selected pages; every packet lists coverage.
The observed missing mappings below show a limitation of this narrow-context first pass.

All calls used the configured extraction provider/model: Ollama `qwen3.8:latest`, unchanged digest
`22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`, temperature zero,
thinking disabled, 4,096 context/1,024 output tokens, concurrency one and zero automatic retries.
Independent generation settings were not substituted. Full prompts, raw responses, native usage,
timestamps, code/source fingerprints and caps are retained in the request journals.

| Paper | Requests reserved | Known candidates | Mechanically validated | Need correction | Human approved / rejected | Pending known |
|---|---:|---:|---:|---:|---|---:|
| Survey | 8 | 3 | 3 | 0 | 0 / 0 | 3 |
| GraphRAG | 7 | 8 | 3 | 5 | 0 / 0 | 8 |
| HippoRAG | 4 | 5 | 3 | 2 | 0 / 0 | 5 |
| LightRAG | 4 | 5 | 4 | 1 | 0 / 0 | 5 |
| HippoRAG 2 | 4 | 4 | 2 | 2 | 0 / 0 | 4 |
| **Total** | **27** | **25** | **15** | **10** | **0 / 0** | **25** |

“Validated” means exact quotation/source and minimum structural fields, **not semantic support or
human approval**. Nine evaluation drafts lack an explicit proposed method/dataset mapping; one
HippoRAG 2 finding contains a nonexact quote. Their original outputs/errors remain visible, with
no silent repair or promotion. Review must resolve/qualify these in new revisions or reject them.
All 25 known candidates are unique in the final packets. Initial human review time is **zero**;
allow up to 20 minutes per paper initially, recording actual decisions/time. Time never approves.

One additional GraphRAG call was interrupted during development and has **unknown outcome**.
It is counted among the 27 reservations and reserves up to **two additional possible candidates**;
they are not invented as known drafts or counted as a successful zero. No automatic retry occurred.
There are 26 saved completed responses. Every paper remains within eight cumulative requests,
eight distinct passages and 12 candidates including conservative unknown reservations.

### Recorded development amendment

The initial prompt produced five empty batches; the next dataset passage produced two candidates.
The run was stopped, preserving all attempts and the interrupted reservation. Decision **D22**
records a versioned clarification that method descriptions, survey challenges and limitations are
valid findings even without experimental numbers. The initial four-request limit became eight
cumulative requests per paper; passage/candidate limits remained unchanged. The second pass used
the same selected passages. This was an explicit development change, not an automatic repair loop
or an accuracy benchmark. D23 binds budgets to the PDF, preserving the original corpus journals as
byte-identical copies so metadata changes or new packet folders cannot reset allowance.

## Verification and cost

- **52 offline tests passed; two optional M0 integration cases deselected.** Tests cover source/hash
  integrity, quote gaps/overlap, wrong-paper/survey evaluation ownership, proposed aliases remaining
  unapproved, exact decision bindings, request reuse, unknown reservations, metadata-revision budget
  preservation, invalid corpus/citation membership before database access and packet-tampering
  rejection. Upstream PyMuPDF SWIG warnings remain.
- `review-check` passed for all five final packets, including all 25 draft identities, quoted spans,
  mapping revisions, CSV bindings and caps against the persistent request journals/raw drafts.
  Invalid candidates remain invalid; the audit verifies
  their recorded errors, rather than declaring their scientific content valid.
- Database read-back passed: five selected papers, 571 combined chunks, six metadata edges, original
  M1 still 325 chunks, both indexes `ONLINE`, **zero project Evaluation/Finding/FactText nodes**.
  The first absence check produced Neo4j unknown-label warnings because those labels do not yet exist.
- Repeat ingestion passed in **37.214 seconds** with byte-equivalent parsed report content and the
  same corpus/chunk counts; `runs/m2/ingest-repeat-check.json` records the measured cached rerun.
- A real combined-index vector query passed with six units/1,418 estimated tokens and **no generator
  call** (`runs/m2/vector-retrieval-check.json`). Original/source-scoped request journals match
  byte-for-byte: final export added **zero inference requests** (`runs/m2/resume-proof.json`).
- `uv lock --check --offline` and `uv pip check` passed; 95 resolved/79 installed packages remain
  compatible. No dependencies or locked package versions changed.
- Known saved generation totals: **748.058 seconds**, **17,744 native input / 5,350 output tokens**.
  This excludes the interrupted call's unknown usage/time and is not total project preparation time
  or a benchmark average. Final packet export reuses saved responses; its subsecond per-paper time
  is not inference latency. Initial ingestion wall time was not captured separately.
- A resource sample during extraction reported about **3.58 GB available RAM** and **11,685 MiB
  total GPU use**. It is one sample, not a peak. Qwen was unloaded after extraction before the
  CPU-encoder repeat check to avoid unnecessary memory competition; the server remains available.
- **Zero paid requests/spend.** OpenAlex used anonymous basic access; OpenAI was not called. Local
  electricity/hardware cost was not measured and is explicitly unknown, not asserted to be zero.

## Artifacts and human handoff

Canonical review entry point: **`runs/m2/review-final/START_HERE.md`**. Each paper has `REVIEW.md`,
canonical `bundle.json` and `decisions.csv`, with claim/source/entity revision hashes prefilled and
reviewer/decision/time/reason fields blank. Earlier development packet folders are preserved;
review the **final** packet identities. No human decisions have been entered or imported.

Key evidence: `runs/m2/ingest-five.json`, `ingest-repeat.json`, `database-integrity.json`,
`extraction-final.json`, `review-check-verified.json`, `resources-during-extraction.json`;
source-scoped journals under `data/extraction/by-source/`; old corpus-scoped journals retained.
All source text, PDFs, caches, journals and review artifacts stay out of Git.

M2.1 has no remaining implementation blocker. **M2.2 requires human decisions and correction of
the flagged proposals before approved-claim work.** M2.3 gold annotations have not begun. OpenAI
live checks remain pending credentials/approved numerical budget for M3.3. No held-out inputs were
created, searched or read; no graph retrievers, final evaluation or claim approval was performed.
