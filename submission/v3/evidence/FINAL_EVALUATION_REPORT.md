# Scientific Research Knowledge Assistant — Frozen Evaluation

**Completed 2026-11-14 (America/Chicago).** Hybrid had the highest mean human correctness on the 16 held-out questions. Graph fell back to Hybrid + Approved Facts on all 24 questions, so this study does **not** demonstrate a benefit from selected graph-traversal evidence. The successful synthetic traversal test establishes implementation capability separately; it is not an observed research advantage.

## Design and provenance

The frozen corpus contains 20 related papers, 1,427 unchanged indexed chunks and 51 active human-approved claims (23 pilot + 28 expansion). Claims preserve what a paper reports; approval does not independently prove its science. Paper selection was recorded before expansion, without selecting for graph gains. Coverage excludes some pages/appendices and unverified numerical tables; conclusions apply to the indexed versions and passages.

The 24 purposively authored, human-validated questions have six per primary category: direct, cross-paper, multi-hop and unanswerable. Eight development questions (two/category) were available during implementation; 16 held-out questions (four/category) remained external. Report the partitions separately. The same fixed local Qwen generator, MiniLM encoder, six-unit/1,800-estimated-token evidence budget and source contracts apply to four retrieval conditions. MiniLM versus MPNet is a separate vector-only experiment over identical chunks/questions; it generates no additional answers. No neural-network training/fine-tuning was performed. Exact algorithms and source-span recall rules remain in [the specification](../project_spec.md), not redefined here.

Freeze SHA-256: `62feb4b684efda52fa3b85e4e9b1283ead51aa944a31dae87f2b7ccc00770942`. The [authorized run plan](M4_2_RUN_PLAN.md) pins source/code/model/runtime/configuration bytes, graph/review/gold commitments and limits. The study ran once: **96 answer runs, 48 additional retrieval-only reads, zero failures/unknown attempts, zero retries and $0 paid API spend**. All 96 provider responses used the selected local generator. Ledger execution took about 56 minutes 36 seconds, excluding preflight/cleanup. Working data stayed unchanged; the isolated read-only target was stopped with volumes retained.

Sergei Iakovlev scored 96 randomized anonymous answers, with no condition reveal until the complete form was validated and sealed. The original download, blank form and packet remain preserved. The imported CSV has 96 unique bound IDs, valid seven-column structure/score fields and timezone-aware timestamps; no score was edited or inferred by an agent. Reported active scoring time: **60 minutes total**; per-answer/batch durations are unknown. Identity blinding cannot prevent a reviewer inferring a condition from wording/evidence. One person validated the annotations and scored answers; no inter-rater agreement was measured.

## Held-out results — 16 questions

Correctness/citation scores use the human rubric 0, 0.5, 1; means are **scores, not accuracy percentages**. Evidence recall uses actual rendered source spans, excludes four unanswerable questions, and averages over the 12 answerable questions. Citation means include zero-citation abstentions per the predefined rubric; abstention success is separate. Retrieval time includes integrity/index/source guards, not just native search.

| Requested condition | Mean correctness | Mean citation support | Evidence recall@6 | Median retrieval ms | Fallbacks |
|---|---:|---:|---:|---:|---:|
| Vector | 0.531 | 0.250 | 0.153 | 154.5 | 0/16 |
| Hybrid | **0.719** | **0.438** | **0.389** | **100.6** | 0/16 |
| Hybrid + Approved Facts | 0.563 | 0.250 | 0.194 | 243.3 | 0/16 |
| Graph | 0.563 | 0.250 | 0.194 | 351.0 | **16/16** |

Paired correctness counts compare answers to the **same** questions; a win means a higher human score.

| Held-out comparison | Wins | Ties | Losses |
|---|---:|---:|---:|
| Hybrid vs Vector | 6 | 9 | 1 |
| Hybrid + Approved Facts vs Vector | 3 | 11 | 2 |
| Graph vs Vector | 3 | 11 | 2 |
| Graph vs Hybrid + Approved Facts | 0 | 16 | 0 |
| Graph vs Hybrid | 0 | 12 | 4 |

Hybrid exceeds Vector's mean correctness by 0.1875 and Graph's by 0.15625 on this sample. Adding approved facts did not improve on Hybrid here. Graph's matching quality and higher observed retrieval time accompany fallback to the fact ablation in every request. Across all 24 questions, saved Graph and Hybrid + Facts context hashes match exactly, with 24 tied human correctness scores. Fallback reasons are 20 `graph_candidates_not_selected_within_budget` and four `no_new_eligible_graph_candidates`. This is a lack of demonstrated incremental traversal benefit under the frozen selection/budget/corpus, not evidence that graph retrieval universally fails or cannot produce new candidates. The experiment cannot estimate the effect of *selected* traversal evidence when none enters generation.

### Score distributions and abstention judgments

| Held-out condition | Correctness counts: 0 / 0.5 / 1 | Answerable-only mean (n=12) | Human correct-abstention=true, unanswerable (n=4) | Human abstention=false, answerable (n=12) |
|---|---:|---:|---:|---:|
| Vector | 5 / 5 / 6 | 0.375 | 4 | 7 |
| Hybrid | 2 / 5 / 9 | 0.625 | 4 | 4 |
| Hybrid + Approved Facts | 4 / 6 / 6 | 0.417 | 4 | 8 |
| Graph | 4 / 6 / 6 | 0.417 | 4 | 8 |

All four held-out unanswerable questions receive full correctness and a true abstention judgment in every condition, so they raise the all-question means. The answerable-only scores expose the remaining gap. The last column records the human rubric's negative abstention judgment; it is **not** a reconstructed raw model-abstention flag. Actual model-abstained flags are unavailable in the numeric reporting inputs and were not inferred. Remaining answerable judgments are N/A (Vector five, Hybrid eight, fact/graph four each).

### Generation and timing interpretation

| Held-out condition | Median generation seconds | Median recorded retrieval + generation seconds |
|---|---:|---:|
| Vector | 41.06 | 41.20 |
| Hybrid | 40.79 | 40.92 |
| Hybrid + Approved Facts | 35.71 | 36.05 |
| Graph | 14.53 | 16.32 |

These component sums are not a separately measured end-to-end wall clock. Graph's lower recorded generation time cannot be attributed to traversal: its selected contexts match the ablation's exactly. Repeated prompts, the frozen rotating condition order and runtime/cache effects can affect timing; no cache-hit counts are established here. Raw provider-native token/cache statistics were not aggregated from the permitted numeric summaries. Generation dominates the recorded local runtime (3,264.93 seconds summed over 96 calls); retrieval medians alone do not represent user waiting time.

## Development results — eight questions

Evidence recall averages over six answerable questions; the other two are unanswerable.

| Requested condition | Mean correctness | Mean citation support | Evidence recall@6 | Median retrieval ms | Fallbacks |
|---|---:|---:|---:|---:|---:|
| Vector | 0.750 | 0.375 | 0.278 | 142.6 | 0/8 |
| Hybrid | 0.688 | 0.563 | 0.556 | 59.6 | 0/8 |
| Hybrid + Approved Facts | 0.875 | 0.563 | 0.778 | 136.7 | 0/8 |
| Graph | 0.875 | 0.563 | 0.778 | 285.5 | **8/8** |

The better development scores for fact modes did not transfer to the held-out partition. These are different questions and small samples; do not use the eight known questions or a pooled 24-question average as a replacement for held-out performance. No parameters, gold facts or selected papers were changed to improve these results.

Development-only diagnostics illustrate scope without exposing held-out cases: DEV-D1 has higher annotated-support recall with Hybrid + Facts than Vector; DEV-D2 and DEV-M2 have equal recall between those conditions. In all three, Graph falls back with the same saved context hash as the fact ablation. These observations identify evidence-selection outcomes, not explanations of hidden answer wording or proof of a particular error cause. No post-reveal gold amendment or search for more favorable support was performed.

## Separate vector-only encoder experiment

Both encoders use the same pinned chunks, source-span annotations, ranking/packing contract and frozen similarity threshold. Latencies include shared guards and cache/order effects; they are observed workstation timings, not universal architectural speed claims.

| Partition | Encoder | Queries / answerable | Evidence recall@6 | Median retrieval ms |
|---|---|---:|---:|---:|
| Held-out | MiniLM, 384-D | 16 / 12 | 0.153 | 151.0 |
| Held-out | MPNet, 768-D | 16 / 12 | 0.208 | 385.6 |
| Development | MiniLM, 384-D | 8 / 6 | 0.278 | 143.4 |
| Development | MPNet, 768-D | 8 / 6 | 0.167 | 370.7 |
| Pooled, descriptive only | MiniLM | 24 / 18 | 0.194 | 148.2 |
| Pooled, descriptive only | MPNet | 24 / 18 | 0.194 | 380.9 |

MPNet's held-out recall is higher by about 0.0556, with higher observed median retrieval latency. Development recall moves in the opposite direction and pooled recall ties. These results do not support an unconditional encoder upgrade. The shared 0.30 threshold is frozen; cosine-score calibration can differ between encoders. No held-out threshold tuning or extra generation was performed.

Held-out median encoding/fetch components are 35.4/109.5 ms for MiniLM and 101.6/263.8 ms for MPNet. Component medians need not sum to the total median; source/index guards are also included. Encoder order alternates within this separate experiment, with no additional model answers.

## Preparation cost and practical limits

| Documented human effort | Approximate minutes | Basis |
|---|---:|---|
| Pilot + expansion graph-claim review | 85 + 133 = **218** | M2.2/M4.1 batch reports; 51 active claims, two deferred pilot drafts |
| Pilot development, expanded development, private gold review | 50 + 65 + 30 = **145** | Separately recorded annotation-validation totals |
| Blind answer scoring | **60** | User's explicit “1 hour” report; exact score values come from the CSV |
| Total recorded review/scoring | **423 (7 h 3 min)** | Includes pilot reuse/revalidation; excludes coding, authoring, PDF inspection and unmeasured work |

The 218-minute graph review is a distinct preparation burden; gold validation and answer scoring support all conditions. Expansion extraction used 30 local Qwen requests (874.210 seconds recorded inference). This is not a complete end-to-end cost model: initial extraction, indexing/embedding time, authoring, electricity and hardware cost are not fully aggregated here. $0 refers to paid API use in the final study, not free local computation or the historical paid readiness probes. Human durations are approximate self-reported totals, with unknown per-item times.

The main limits are sparse reviewed graph coverage, the absence of selected graph additions, a small purposive question set, reused development topics, AI-assisted gold authorship, one human scorer/validator, strict registered-source-span coverage, omitted source sections/tables, hardware/cache/order effects and no training/generalization study. Equivalent but unregistered supporting passages may receive no evidence-recall credit. Recovery reproduced saved-context scores exactly but rebuilt indexes changed five fresh contexts and two recalls; saved frozen artifacts are authoritative. Corrected annotations or later retrieval improvements require a disclosed versioned amendment, not a relabeled untouched held-out rerun.

## Reproducible artifacts

- Research aggregates: `runs/m4-3/aggregate-results-20261115T035119990546Z.json`; includes both partitions, paired counts and the separate encoder comparison.
- Exact human CSV import/provenance: `human-score-import-validation-20261115T035119990546Z.json`, `scoring-submission-chat.json`; CSV SHA-256 `bd8398a217a4ba894fa06e850a36de3bed190e050ad2370a3e75c2e86425fde4`.
- Seal proof: `human-score-seal-20261115T035119990546Z.json`; original private packet/gold/scores/reveal mappings remain external and out of Git/chat.
- Supplemental post-seal numeric report: `post-seal-descriptive-results-20261115T035119990546Z.json`; six condition pairs, score distributions, denominated judgments, timings, context-hash equality and development-only diagnostics. This is descriptive reporting over saved numeric outputs, with input hashes preserved; no frozen algorithm/gold/score amendment or new experiment.
- Execution, preservation, verification and milestone checks: [M4.3 report](M4_3_REPORT.md), [M4.2 report](M4_2_REPORT.md). No extra inference/retrieval was used to seal or reveal scores.
