# M5.6 - Matched exploratory evaluation results

**Completed 2026-11-18 (America/Chicago).** All 288 human score rows were validated and sealed before guarded condition reveal. On the 16 fresh held-out questions, the primary Graph-versus-fact-ablation comparison is **0 wins / 16 ties / 0 losses**. All three Graph arms fall back on every held-out question. The study therefore establishes **no held-out benefit from selected graph-traversal evidence**. Reranked Hybrid, Hybrid + Facts and Graph tie for the highest observed mean correctness (0.8125); their matching quality must not be attributed to successful Graph expansion.

## Design, provenance and human scoring

The unchanged corpus has 20 papers, 1,427 indexed chunks and 51 source-bound human-approved claims. A0 is the original baseline/reference policy; A1 is retrieval-v2 with the reference selector; A2 is retrieval-v2 with the pinned shared cross-encoder. Each has Vector, Hybrid, Hybrid + Approved Facts and Graph conditions. The same local Qwen generator, MiniLM encoder, source/approval rules and six-unit/1,800-estimated-token evidence budget apply. Algorithms remain defined by [the specification](../project_spec.md), not redefined here.

All 12 conditions answered the same 24 questions: eight reused public development questions and 16 fresh held-out questions, with two/four per category respectively (direct, cross-paper, multi-hop, unanswerable). Development was used for design; report its results separately. This is a matched comparison within the fresh study, **not** a paired comparison of old and new held-out means. The completed baseline study and its [original final report](FINAL_EVALUATION_REPORT.md) remain unchanged.

Exact freeze SHA-256: `c64da42c62fe46bbd51220738a0016d00742bb1c606575cbb68c4db21374329c`. Actual receipt SHA-256: `6e4871c6b316005bf5ed9b34a043cae12e0f4459fdefa1531da927bf1e757897`. One authorized runner invocation completed **288 answer runs**, zero extra encoder reads and $0 paid. The retained read-only target stopped. No second execution, automatic retry, new extraction, model change or paid request occurred. The public slot count does not expose exact provider-response totals; a deterministic abstention can complete without a generation call, so 288 provider responses is not claimed.

The user submitted `scores-complited.csv`, SHA-256 `428effab5368c4f342c407ccffcc732c57b20b374dbbf307e57e9ed4ba3afb67`. It was preserved byte for byte in the exact evaluator execution before validation. All 288 opaque answer IDs appeared exactly once; column, rating, reviewer, timezone-aware timestamp and packet-commitment checks passed. The complete scores were sealed before the system revealed conditions. No scores were edited or supplied by an agent. Actual active scoring time is **60 minutes total**, supplied as "1 hours"; granular durations are unknown. This is separate from source review. Private rows, notes, questions, answers and reveal mappings remain external and were not returned to development.

## Held-out results (16 questions)

Correctness and citation support are mean human ratings on the predefined 0/0.5/1 rubric, **not accuracy percentages**. Evidence Recall@6 uses actual assembled source-span support and averages over the 12 answerable questions; the four scoped-unanswerable questions are N/A for recall. Correctness/citation means include all 16 questions, so they must not be described as answerable-only accuracy or abstention rates. Retrieval medians include source/review/index integrity checks and selector work; they exclude generation and are not cold-start search benchmarks.

| Arm / requested mode | Correctness | Citation support | Evidence Recall@6 | Median retrieval ms | Graph fallbacks |
|---|---:|---:|---:|---:|---:|
| A0 / Vector | 0.7188 | 0.5625 | 0.3889 | 68.8 | - |
| A0 / Hybrid | 0.7500 | 0.5312 | 0.4722 | 42.8 | - |
| A0 / Hybrid + Facts | 0.6875 | 0.5312 | 0.3889 | 113.0 | - |
| A0 / Graph | 0.6875 | 0.5312 | 0.3889 | 154.2 | 16/16 |
| A1 / Vector | 0.7188 | 0.5625 | 0.3889 | 69.1 | - |
| A1 / Hybrid | 0.7500 | 0.5312 | 0.4722 | 43.0 | - |
| A1 / Hybrid + Facts | 0.6875 | 0.5312 | 0.3889 | 115.9 | - |
| A1 / Graph | 0.6875 | 0.5312 | 0.3889 | 159.0 | 16/16 |
| A2 / Vector | 0.6562 | 0.5000 | 0.3611 | 343.3 | - |
| A2 / Hybrid | 0.8125 | 0.6250 | 0.4861 | 506.5 | - |
| A2 / Hybrid + Facts | 0.8125 | 0.6250 | 0.4861 | 921.8 | - |
| A2 / Graph | 0.8125 | 0.6250 | 0.4861 | 998.0 | 16/16 |

The preregistered primary contrast is **A2-graph vs A2-hybrid_facts**. Both score 0.8125 correctness, 0.6250 citation support and 0.4861 evidence recall, with 16/16 Graph fallbacks. A1 Graph also ties its matching fact ablation on all 16 questions. A1's broader routes show no held-out correctness difference from A0's reference modes; the held-out reference Graph requests all fall back.

| Matched correctness comparison | Wins | Ties | Losses |
|---|---:|---:|---:|
| A2-graph vs A2-hybrid_facts | 0 | 16 | 0 |
| A1-graph vs A1-hybrid_facts | 0 | 16 | 0 |
| A2-vector vs A1-vector | 0 | 14 | 2 |
| A2-hybrid vs A1-hybrid | 3 | 12 | 1 |
| A2-hybrid_facts vs A1-hybrid_facts | 4 | 12 | 0 |
| A2-graph vs A1-graph | 4 | 12 | 0 |
| A1-vector vs A0-vector | 0 | 16 | 0 |
| A1-hybrid vs A0-hybrid | 0 | 16 | 0 |
| A1-hybrid_facts vs A0-hybrid_facts | 0 | 16 | 0 |
| A1-graph vs A0-graph | 0 | 16 | 0 |

The A2 policy improves mean correctness over A1 by **0.0625 for Hybrid** and **0.1250 for Hybrid + Facts/Graph** on this sample. Those are mean-rating differences, not percentage-point accuracy gains. Vector falls by 0.0625 (zero wins/two losses). The reranker is therefore not uniformly beneficial. These are end-to-end policy contrasts: reranking can change Graph anchors as well as final selection, so the experiment does not isolate a single causal mechanism.

The observed quality tie also has a latency trade-off: reranked Hybrid's held-out retrieval median is 506.5 ms, compared with 921.8 ms for reranked Hybrid + Facts and 998.0 ms for Graph. The graph stage added observed latency without a held-out quality or source-recall gain over its matching ablation. This is specific to the frozen corpus, questions, budgets and workstation; application defaults were not changed.

## Development results (8 previously available questions)

| Arm / requested mode | Correctness | Citation support | Evidence Recall@6 | Median retrieval ms | Graph fallbacks |
|---|---:|---:|---:|---:|---:|
| A0 / Vector | 0.6875 | 0.3750 | 0.2778 | 70.3 | - |
| A0 / Hybrid | 0.7500 | 0.5625 | 0.5556 | 43.0 | - |
| A0 / Hybrid + Facts | 0.8125 | 0.6250 | 0.7778 | 113.5 | - |
| A0 / Graph | 0.8125 | 0.6250 | 0.7778 | 157.9 | 8/8 |
| A1 / Vector | 0.6875 | 0.3750 | 0.2778 | 68.3 | - |
| A1 / Hybrid | 0.7500 | 0.5625 | 0.5556 | 43.6 | - |
| A1 / Hybrid + Facts | 0.8125 | 0.6250 | 0.7778 | 115.3 | - |
| A1 / Graph | 0.8750 | 0.6875 | 0.7778 | 169.9 | 7/8 |
| A2 / Vector | 0.6250 | 0.3750 | 0.3889 | 348.9 | - |
| A2 / Hybrid | 0.7500 | 0.3125 | 0.2778 | 510.9 | - |
| A2 / Hybrid + Facts | 0.8750 | 0.5000 | 0.6389 | 924.4 | - |
| A2 / Graph | 0.8750 | 0.5000 | 0.6389 | 1031.9 | 8/8 |

A1 Graph has one development correctness win/seven ties against its fact ablation (0.8750 vs 0.8125), with one nonfallback request, but both retain mean source recall 0.7778. This does not overturn the earlier retrieval-only no-go or establish a held-out benefit. A2 Graph again ties its fact ablation on all eight questions and falls back eight times. Reranking lowers development fact-mode recall from 0.7778 to 0.6389 even where human correctness rises; these metrics measure different properties.

Public development diagnostics and source-backed cases are retained in [M5.4](M5_4_REPORT.md). In that earlier fixed retrieval comparison, the novel NER/OpenIE finding did not supply registered novel gold support. This report does not infer which current scored answer caused a difference from the aggregate counts. Individual reviewed answer/source cases remain in the external anonymous packet; no held-out prompt or answer is reproduced here. Pooled 24-question means are retained in the public JSON for reconciliation, not used as held-out headlines.

## Cost, limitations and interpretation

- **Research limitation:** M5.4 found no measurable development Graph benefit. The user explicitly chose to proceed despite that negative gate. The fresh question author received prior outcome summaries through startup instructions, and the user accepted an explicitly exploratory disposition. Human source validation cannot remove possible outcome-informed question-selection bias. See the [study amendment](M5_5_STUDY_AMENDMENT.md).
- **Scope:** The sample is small, purposive and limited to indexed paper versions/pages. Excluded appendices, incomplete source/claim coverage and unverified numerical tables limit conclusions. Approval means a statement matches its source, not independent scientific verification. Findings do not establish population superiority or universal failure of Graph RAG.
- **Graph interpretation:** All held-out Graph requests fall back. This study cannot estimate an effect of selected traversal evidence where none enters generation. The implementation's positive synthetic traversal tests show capability separately; they are not research gains on this corpus.
- **Human measurement:** One human supplied the ratings; no independent second-rater reliability check was performed. Anonymous IDs and sealed-before-reveal scoring do not prevent guessing conditions from answer/evidence wording. Fine-grained review times are unknown. Preserve partial/negative scores and the sealed original; any later correction needs a disclosed amendment.
- **Operational cost:** This study used $0 paid API calls. Local hardware/electricity costs and energy/emissions were not measured. RAM/VRAM headroom was tight; this one completed matrix is not a general production-endurance claim. The published retrieval medians reflect the run's cache/service state and integrity overhead. No cold-cache, cache-hit-rate, per-condition generation-cost or energy comparison is available in the public aggregate, so none is inferred.
- **Preparation cost:** Answer scoring took 60 actual minutes. The complete fresh annotation-review time remains unknown; the historical 2.43-minute partial record is not a total. Earlier corpus claim/gold reviews and readiness probes retain their own reports; do not sum overlapping or unknown durations into a fabricated project total.
- **Unavailable detail:** Public output does not include answerable-only correctness, abstention-rate/category breakdowns, score distributions or generation-time medians. No substitute quantities were invented, and private rows were not opened in development to reconstruct them.

## Verification and disposition

**16 public aggregate-consistency groups pass** (partition sizes/weighted means/paired counts, exact receipt/CSV commitments and seal-before-reveal ordering). **16 fresh preservation groups pass**: 208 current frozen runtime assets and 118 original baseline assets unchanged; current source/review/catalog/development readiness and both working graph fingerprints preserved; both used evaluation targets stopped. These are reporting/integrity checks, not new model-quality tests. No application-code/interface/dependency changes occurred, so the prior 363 offline/two corrected native passes were retained rather than rerun. The two corrected public postexecution verification-harness mistakes remain recorded in the operational report; neither was a study retry. No new retrieval/generation, private development read, UI demo or paid check was performed during score finalization.

Public evidence under `runs/retrieval-v2/m5-5/m5-6/`: `human-score-intake-v1.json`, `human-score-sealing-outcome-v1.json`, `guarded-reveal-outcome-v1.json`, `aggregate-results-v1.json`, `aggregate-consistency-v1.json`, `postscoring-preservation-v1.json`, and additive final acceptance. The earlier human-scoring checkpoint remains historical. Source CSV, anonymous packet, immutable seal and revealed individual rows stay external; do not repeat seal/reveal exports or restart either used freeze.

**M5.6 is complete.** Report the observed reranker trade-offs and absence of held-out traversal benefit. No further study or retrospective tuning is authorized. **M6 product demonstration readiness is next and remains unstarted**; it will verify the working local UI separately while preserving these frozen research artifacts.
