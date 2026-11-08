# M2.3 — Development evidence and human gold validation

**Status: complete.** All eight development annotations have explicit human approval against their
exact displayed question, reference answer and source-span bindings. Final `dev-check` reports
`human_validated: 8` and `ready: true`. The M2 evidence gate is satisfied for the bounded pilot;
M3's end-to-end product/traversal/integration/recovery gate remains unfinished. Corpus expansion
remains closed. No held-out inputs were listed, searched or read.

## Task outcomes

| M2.3 requirement | Actual outcome |
|---|---|
| Eight stratified development questions | Two direct, two cross-paper, two multi-hop and two unanswerable annotations, all human-approved. All five pilot papers contribute answerable evidence. |
| Independent gold spans | Separate gold IDs and exact PDF/chunk/offset/hash references with sufficient-fact sets. One real source fact has no approved graph support counterpart. Gold stays outside graph/retrieval inputs. |
| Limitations and multi-passage evidence | Real-paper limitations, AND support across passages, reporting-paper attribution, incompatible/unknown conditions and connected multi-hop reasoning chains exercised. |
| Human checkpoint | Four two-question batches approved; exact responses and identity retained in ignored receipts. No approval or duration inferred for unseen items. |
| Final readiness | Source/annotation/audit hashes, all eight approval bindings, category allocation, source-only context feasibility and unanswerable scoring checks pass. |

Corpus: `74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329`.
Development version: ignored `data/evaluation/development/pilot-v1/`.
Dataset binding: `bf50cdc6e912926732220c2f4276d0e09a5ecf98c93d0f71c85380856db5a67c`.
Implementation checkpoint: `7469244`; subsequent closeout changes affect documentation and private
human records only. Source-tree and lockfile hashes are recorded in the acceptance artifact.

## Human validation and preparation time

| Batch | Category / IDs | Recorded decision | Approximate reported minutes |
|---|---|---|---:|
| 01 | Direct / DEV-D1, DEV-D2 | Approved — supported | 10 |
| 02 | Cross-paper / DEV-C1, DEV-C2 | Approved — supported | 15 |
| 03 | Multi-hop / DEV-M1, DEV-M2 | Approved — supported | 10 |
| 04 | Unanswerable / DEV-U1, DEV-U2 | Approved — scoped absence supported | 15 |
| **Total** | **8/8 approved; zero pending/rejected** | | **50** |

The total is approximately **3,000 seconds of user-reported batch review**, separate from M2.2's
claim-review effort. Numeric replies were to questions explicitly asking for minutes. Individual
question times remain unknown. Verbatim responses, timestamps and exact bindings are preserved in
`human-inputs/batch-01-chat.json` through `batch-04-chat.json` inside the dataset directory. Receipt
hashes are included in the final acceptance record. No private identity or raw response enters Git.

## Design, scope and limits

The questions cover design, scaling caveats, evaluation setups, linked discovery, cost/fallback
behavior and justified abstention. Multi-hop questions have connected chains with at least two
explicit relations and take category precedence over cross-paper. This is purposive development
data with overlapping sources, not an independent statistical sample or performance-selected test.
Gold is agent-proposed and human-validated; it does not certify scientific truth or exhaustive
coverage. Graph-independent IDs do not by themselves establish semantic validity.

Reference answers distinguish original HippoRAG from HippoRAG 2 and preserve reporting-paper
ownership. A shared MuSiQue name does not prove matching releases, subsets or splits. Qualitative
cost reports do not establish numerical cross-study superiority. Numerical performance comparison
remains limited by the pilot evidence; no values were fabricated or graph claims added to match gold.

The unanswerable judgments are human-validated for the **recorded indexed corpus only**. The audit
retains all four carbon/energy-term hits and 12 original-HippoRAG fine-tuning/NER/OpenIE hits, including
irrelevant/citation matches. Keyword triage alone is not proof of semantic absence. Omitted pages,
appendices, other versions and the wider literature remain outside the judgment. Both questions
have empty gold-fact/sufficient-set lists and evidence recall `N/A`; context-only quotations do not
become answers to the missing measurements. Revalidate these judgments if the corpus expands.

Fixed source windows sometimes include surrounding context. Equivalent sufficient passages require
explicit reviewed annotations. Missing/truncated support receives no credit; graph IDs and reference
answer text cannot substitute for source spans. Later changes require a new immutable dataset
version and fresh validation. The creation manifest's draft label is historical; current human
eligibility comes from exact-bound receipts and `dev-check`, not that creation-time text.

This is **development acceptance, not the M4 final-evaluation freeze**. Human gold validation grants
no graph-claim approval, does not reopen the two timeboxed GraphRAG drafts, and does not reset
extraction limits. All existing source/claim histories remain preserved.

## Implementation and checks

`evaluation/development.py` provides development-only contracts, immutable exports, category and
connected-chain checks, complete review packets, exact-bound human receipts and readiness replay.
`ingestion/sources.py` supplies the shared hash-verified corpus loader; review delegates to the same
loader. The workflow reuses the existing `EvaluationQuestion`, common evidence packer and scorer.
It rejects external dataset directories and held-out rows; it is not the private evaluation runner.

`questions.jsonl` contains stripped requests. `annotations.jsonl` contains reviewed reference
answers and gold spans for evaluation only. Never give gold to retrieval/generation. All real
questions, answers, source/audit text and receipts stay ignored locally; tracked fixtures are
synthetic. Human provenance is a trusted input boundary, not cryptographic proof of identity.

| Check actually performed | Outcome |
|---|---|
| Offline implementation suite | **75 passed**, three integration cases deselected; 78 collected. Five upstream PyMuPDF SWIG deprecation warnings. No application changes since this run; data-only human imports did not trigger redundant unit-test reruns. |
| Locked dependencies | `uv lock --check --offline` and `uv pip check` passed during implementation; no dependency/lockfile changes. |
| Final CLI readiness | `uv run --locked --offline python -m research_assistant dev-check --dataset-dir data/evaluation/development/pilot-v1 --output runs/m2/m2-3-session/final-readiness.json` passed: eight approved, readiness true, exact source and artifact hashes valid. |
| Source-only feasibility | All six answerable oracle contexts fit in **1–3 units / 257–739 estimated tokens** and cover their required gold spans. This is annotation feasibility, not measured retrieval recall. |
| Real multi-passage scorer | Full support recall 1; missing premise 0; one-character truncation 0. Raw and approved-fact evidence both receive recall 1 for the same independent gold fact. |
| Outside-graph gold | DEV-D2 is supported by a source chunk absent from every current approved-fact support bundle; its raw witness receives recall 1. |
| Final acceptance verifier | Eight stripped requests match annotations; all four receipts pass binding/hash replay; both unanswerable recalls are null (`N/A`); review time sums to 3,000 seconds. |
| Preservation | Offline source/journal replay still has 571 chunks, 23 eligible facts and two deferred claims at the unchanged M2.2 head. No graph writes or provider calls. |

The first focused implementation test run passed 22 and failed one because a synthetic receipt
fixture changed JSON formatting before replay. The fixture was corrected to preserve canonical
formatting; the full suite passed afterward. No production receipt was edited to fix that test.

Service integration tests were not rerun for this offline milestone. Ollama inference was not
needed; OpenAI live readiness remains pending credentials and an approved budget for M3.3. No
retrieval-mode comparison, answer-quality evaluation, graph traversal or recovery test is claimed.
There were **zero LLM/paid calls and zero held-out accesses** in M2.3.

## Artifacts, deviations and next step

- Dataset: `data/evaluation/development/pilot-v1/`; complete source/audit/annotation files and all
  four original review packets remain unchanged. Only derived receipts/acceptance notes were added.
- Final import: `runs/m2/m2-3-session/gold-import-batch-04.json`.
- Final CLI checks: `runs/m2/m2-3-session/final-readiness.json`.
- Immutable development acceptance: `runs/m2/m2-3-session/acceptance.json`, including dataset/source/
  annotation/receipt/code/lockfile hashes and current readiness. It is a historical acceptance record;
  future edits or revocations require a fresh readiness check.
- Earlier preparation, scorer checks and intermediate imports remain preserved under the same
  ignored session directory. Current handoff: `runs/m2/m2-3-session/START_HERE.md`.

No requirement or dependency deviations were introduced. There is no remaining M2.3 human
checkpoint or blocker. Next is **M3.1**: implement Hybrid, Hybrid + Approved Facts and Graph retrieval
with the established shared evidence contracts, bounded templates, fallback and query-plan checks.
M3.2 product workflows and M3.3 provider/recovery checks still precede expansion. Held-out inputs
remain evaluator-controlled and untouched; final-run authorization belongs to M4.
