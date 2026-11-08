# M2.3 — Development evidence checkpoint

**Status: waiting for human gold validation; not complete.** Eight development questions and
source-span annotations are prepared and mechanically verified. **Two of eight annotations are
human-approved** (DEV-D1/DEV-D2); six remain pending. The cross-paper batch is now presented in chat. No held-out inputs were
listed, searched or read; no final benchmark or M3 retrieval comparison has run.

## Task outcome so far

| M2.3 requirement | Actual outcome |
|---|---|
| Eight stratified development questions | Two direct, two cross-paper, two multi-hop and two unanswerable drafts. All five pilot papers contribute answerable evidence. |
| Independent gold spans | New gold identifiers, exact PDF/chunk/offset/hash references and sufficient-fact sets. Gold data is stored outside graph/retrieval inputs. One direct source fact has no approved graph support counterpart. |
| Limitations and multi-passage support | Real-paper limitations, AND requirements across passages, cross-paper setups, connected reasoning chains and explicit unknown/incompatible conditions are included. |
| Human validation | **Approved: 2/8; pending: 6/8.** DEV-D1 and DEV-D2 explicitly approved as supported. Prior graph-claim approvals do not approve a question, reference answer or scoring annotation. |
| Five-paper acceptance gate | Remains open. M3 traversal, product workflows, integrations and recovery are still separate gates. Corpus expansion remains closed. |

Corpus: `74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329`.
Development version: ignored `data/evaluation/development/pilot-v1/`.
Dataset binding: `bf50cdc6e912926732220c2f4276d0e09a5ecf98c93d0f71c85380856db5a67c`.

## Design and limits

The questions test design, scalability caveats, differing evaluation corpora, linked discovery and
cost/fallback behavior. Each multi-hop draft includes a connected chain with at least two explicit
relations; that category takes precedence over cross-paper. The set is purposive development data
with overlapping sources, not an independent statistical sample or a performance-selected benchmark.
Its gold is agent-proposed and requires human validation; graph-independent identifiers alone do
not establish semantic validity or complete annotation coverage.

Reference answers preserve reporting-paper ownership and distinguish original HippoRAG from
HippoRAG 2. Shared MuSiQue identity does not imply matching releases, subsets or splits. Qualitative
overhead reports do not establish numerical cross-study superiority. Gold may exist without an
approved graph claim; it is never ingested into the graph to improve apparent coverage.

The unanswerable drafts concern an unavailable exact emissions measurement and an unreported gain
from a proposed fine-tuning intervention. Their absence audit scans the 571 indexed chunks, retaining
all four emissions/energy-term hits and 12 original-HippoRAG fine-tuning/NER/OpenIE hits, including
irrelevant and citation matches. The original paper's future-work/off-the-shelf discussion provides
useful context. Keyword triage is **not** proof of semantic absence. Human review must validate the
corpus scope and rationale; omitted pages, appendices, other versions and wider literature are not
certified absent. Unanswerable questions have no gold facts or sufficient sets; recall is `N/A`.

Source spans currently identify fixed quotation windows, sometimes including surrounding context.
Equivalent sufficient passages must be explicitly annotated and reviewed; matching a graph claim ID
or paraphrasing a reference answer cannot supply missing source evidence. Reviewers should flag
overbroad spans or missing alternatives. Revalidate development annotations if the corpus expands;
the pilot's unanswerability judgments do not automatically hold for the final corpus.

Gold-validation effort is recorded separately from M2.2's initial claim-review timeboxes. This work
does not approve new graph claims, reopen the two deferred GraphRAG drafts or reset extraction caps.
No claim journals or graph state were modified.

The first gold batch (DEV-D1/DEV-D2) was explicitly approved as supported, with **approximately ten
minutes / 600 seconds** reported for that batch. The reply `10` is interpreted in minutes because
the displayed question explicitly asked for minutes. Individual question times remain unknown.
The exact response, reviewer identity and displayed annotation bindings are in the ignored receipt
`data/evaluation/development/pilot-v1/human-inputs/batch-01-chat.json`. No unseen annotation was approved.

## Implementation

- `ingestion/sources.py` now owns the existing immutable corpus-cache loader, shared by review and
  evaluation. Source hashes remain checked; the review API delegates to it without changing its
  approval rules. No independent source-validation implementation is introduced per retrieval mode.
- `evaluation/development.py` defines development annotations, category/rationale checks, connected
  reasoning links, immutable dataset exports, exact-bound review packets and human receipts. It uses
  the existing `EvaluationQuestion`, `SourceSpanRef`, common evidence packer and source-span scorer.
- The workflow accepts only versioned directories inside `data/evaluation/development/`; external
  dataset paths and held-out rows are rejected. This is a development boundary, not the M4 private
  evaluation runner. It never discovers an evaluator-controlled directory.
- `annotations.jsonl` contains proposed answers/spans. `questions.jsonl` strips answers and supports;
  only stripped requests may later go to retrieval/generation. All real questions, gold, audit text
  and receipts remain ignored local artifacts. Tracked tests contain synthetic data only.
- Annotation/source/audit hashes detect edits. Changed annotations require a new version and fresh
  human validation. Receipts retain verbatim responses, exact displayed bindings, timezone-aware
  capture time and known/unknown batch duration. Per-question time is not invented. Old receipt
  replay cannot undo a later decision; altered receipt hashes fail. Human provenance remains a
  trusted input boundary, not cryptographic proof of identity.
- New CLI: `dev-check --dataset-dir <development-version> --output <new-report.json>` with the
  standard `uv run --locked --offline python -m research_assistant` prefix. This command checks
  annotation integrity/readiness without LLM or Neo4j calls. It does not mark drafts human-valid.

## Actual checks and omissions

| Check | Outcome |
|---|---|
| `uv run --locked --offline pytest -m "not integration"` | **75 passed**, three integration cases deselected; 78 collected. Five upstream PyMuPDF SWIG deprecation warnings. |
| Development corpus/source/category checks | Eight unique development-only questions, exactly two per category; all exact gold spans valid. Six answerable oracle contexts fit in **1–3 units / 257–739 estimated tokens**. |
| Real multi-passage scorer | Complete support recall 1; missing premise 0; one-character truncation 0. Raw and approved-fact support both receive recall 1 for the same independent gold fact. |
| Outside-graph source fact | Direct question DEV-D2 is supported by a chunk absent from every current approved-fact support bundle; a raw source witness receives recall 1. |
| Source/review preservation | Offline replay still has 571 source chunks, 23 eligible facts and unchanged M2.2 journal head. No graph writes, extraction or provider calls. |
| Dependency checks | `uv lock --check --offline` and `uv pip check` passed; no dependency or lockfile changes. |
| First human import/readback | Exact-bound DEV-D1/DEV-D2 decisions replay as approved; six others remain pending and dataset readiness stays false. Source/category/witness checks still pass; no code changes or test rerun were needed for this import. |

The first focused test run passed 22 cases and failed one because the synthetic receipt fixture
changed JSON formatting before replay. The fixture now preserves canonical formatting; the full
suite passed afterward. No production receipt was edited to repair this test.

Oracle contexts are deliberately assembled from annotated sources to check feasibility. Their recall
is **not measured retrieval performance**. No answer quality, mode comparison or traversal claim is
made. Service integration tests were not rerun for this offline change. Ollama inference was not
needed; OpenAI live readiness remains pending credentials/budget for M3.3. Zero LLM/paid calls and
zero held-out accesses occurred.

## Artifacts and remaining checkpoint

- Dataset: `data/evaluation/development/pilot-v1/{manifest.json,questions.jsonl,annotations.jsonl,absence-audit.json}`.
- Four two-question packets: `review-batches/batch-01` through `batch-04` in that directory.
- Current human request: batch-02, DEV-C1/DEV-C2. Batch-01 is approved with ten minutes reported;
  batch-02 decisions/time are pending. Reviewer identity persists from the prior session.
- Preparation/check reports: `runs/m2/m2-3-session/prepare-result.json`, `check-initial.json`.
- Real scorer fixture: `runs/m2/m2-3-session/source-scorer-check.json`.
- Latest human import/readback: `runs/m2/m2-3-session/gold-import-batch-01.json`.
- Source-curation and verifier scripts remain under the same ignored session directory.

Finish the remaining three small human-validation batches, record actual decisions/time, revise any rejected
or unclear annotations as a new version, and rerun the applicable checks. M2.3 remains unchecked
until all required gold annotations are validated. `project_spec.md` section 4 explicitly requires
"Human-validate statements/spans before freezing"; mechanical passes cannot substitute for that step.
