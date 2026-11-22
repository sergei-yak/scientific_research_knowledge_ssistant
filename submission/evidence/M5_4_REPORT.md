# M5.4 — Matched development retrieval ablations

**Status: complete. Decision: no-go for a larger fresh Graph answer study under the original-51-claim route/selector hypothesis.** Both new arms have zero mean final-recall advantage over their paired Hybrid + Facts ablation, and no selected novel graph item supplies missing registered gold support. This is a valid negative development result, not an implementation acceptance failure or a claim about Graph RAG generally. M5.5/M5.6 are not started under this hypothesis.

## Scope and preregistration

Implementation is in `C:/Users/serge/DBU-GraphRAG-Worktrees/retrieval-v2-m52-54d8b329`. Specification 6.3, R2.1–R2.8, D54–D55 and the unchanged M5.1 V2 comparison policy govern this step. D64 resolves diagnostic execution/scoring details before the first measured retrieval; D65 records the outcome. Requirements, models, dependency pins, corpus, annotations and approvals were not changed to obtain a gain.

Before execution, `runs/retrieval-v2/m5-4/comparison-v1/execution-manifest.json` bound code/tests/runner/scorer bytes, profile policies, model/features, question bytes, original 51 approvals, physical target, source and index identities. Exact file SHA-256: `d2fb2c3819f2e95b86e23b5059d12f2c8b5a6f02ffcb7d8598a51751ecff0610`.

One sequential matrix used all **eight unchanged public development questions × three arms × four modes = 96 retrieval requests**, with durable pre-request reservations, **zero failures/retries/generation/paid calls**. Question/arm/mode order follows the recorded policy. The matrix ran from 2026-11-15 23:14:04 to 23:15:54 UTC. Gold was loaded only by the separate offline scorer after saved retrieval completion. The old private set was not accessed and remains retired from untouched-test use.

| Arm | Routes | Selection |
|---|---|---|
| A0 | Legacy reference | Reference ordering |
| A1 | Broader Finding/Evaluation/direct-entity routes | Same reference ordering |
| A2 | Same route policy as A1 | Shared pinned MiniLM cross-encoder in all four modes |

All arms used the same isolated Neo4j copy/indexes, source chunks, MiniLM query encoder, review head, **six evidence units / 1,800 estimated tokens** and original **51** facts. No enrichment, fresh extraction or paper replacement occurred. A0 is a fresh matched reference on these indexes; historical pre-restore contexts are not the comparison control.

## Evidence recall

Candidate coverage is the exact source-interval AND/OR sufficient-fact coverage of the **eligible pre-packing excerpt union**, without a generator budget. Final Recall@6 is the existing shared scorer applied to the **actual rendered context**. Both reuse the same interval validation and coverage logic. Candidate coverage is not an oversized generator result, a relevance precision measure or answer quality. Means below use all **six answerable questions**; the two unanswerable questions are N/A throughout.

| Mode | Candidate recall A0 / A1 / A2 | Final recall A0 | Final recall A1 | Final recall A2 |
|---|---:|---:|---:|---:|
| Vector | .4444 / .4444 / .4444 | .2778 | .2778 | .3889 |
| Hybrid | .6111 / .6111 / .6111 | .5556 | .5556 | .2778 |
| Hybrid + Facts | .9167 / .9167 / .9167 | .7778 | .7778 | .6389 |
| Graph | .9167 / .9167 / .9167 | .7778 | .7778 | .6389 |

The broader routes did not increase registered candidate support. Reranking improved Vector mean recall but reduced Hybrid and fact-mode recall; it is not a measured across-mode improvement. Reference non-Graph contexts match A0/A1 for all eight questions, and their non-Graph candidate pools match A1/A2. All A1/A2 final context hashes differ, including the unanswerable questions; changing a context does not establish improvement.

| Question | A1 Hybrid | A1 Facts / Graph | A2 Hybrid | A2 Facts / Graph |
|---|---:|---:|---:|---:|
| DEV-D1 | 1 | 1 / 1 | 0 | 1 / 1 |
| DEV-D2 | 1 | 1 / 1 | 1 | 1 / 1 |
| DEV-C1 | 0 | .5 / .5 | 0 | .5 / .5 |
| DEV-C2 | 0 | .5 / .5 | 0 | 0 / 0 |
| DEV-M1 | .3333 | 1 / 1 | .3333 | 1 / 1 |
| DEV-M2 | 1 | .6667 / .6667 | .3333 | .3333 / .3333 |

DEV-C1 has complete support in the fact-ablation candidate pool but only half in either final context. In A1, Graph exchanges the survey caveat for the HippoRAG caveat, while selecting one novel **NER/OpenIE fine-tuning** claim via a direct HippoRAG method anchor. That novel claim's excerpts do not supply the registered scalability fact. The newly covered caveat comes from already-available baseline evidence; removing the novel item retains it. Thus this is a fact swap, not incremental novel graph support. DEV-C2 has only .5 candidate coverage; A2 also loses that available half during final selection. Neither observation proves absent support across the full corpus or motivates changing gold.

## Graph reach, omissions and source contributions

Novel means outside the **entire same-arm fact-ablation candidate pool**, not merely outside its selected six. Incremental-support witnesses require a final fact absent from paired ablation, lost after removing all selected novel items, and exact novel-excerpt overlap with registered source spans. Joint/redundant support is allowed; the witness is not a claim of individual item necessity.

| Diagnostic, all eight questions | A0 | A1 | A2 |
|---|---:|---:|---:|
| Graph route calls / returned rows | 128 / 344 | 104 / 346 | 104 / 321 |
| Retained novel candidate occurrences / distinct IDs | 28 / 16 | 24 / 13 | 21 / 12 |
| Novel candidate final-order rank range | 13–47 | 5–45 | 23–45 |
| Novel occurrences omitted for `unit_limit` | 28 | 23 | 21 |
| Selected novel items | 0 | 1 | 0 |
| Graph fallbacks | 8/8 | 7/8 | 8/8 |
| Incremental registered novel-support questions | 0 | 0 | 0 |
| Mean final paper diversity | 2.625 | 2.500 | 2.125 |

All **23 actual fallbacks** exactly match paired evidence/context/aliases/tokens/candidates. Actual pre-fallback contexts, full candidate excerpts, per-candidate decisions, paths and row duplicate/baseline membership remain saved for every arm. Reference pre-fallback mean recall is .3056 in both A0/A1; fallback protects against that pool-wide graph ordering. A2 pre-fallback mean is .6389. All final contexts have six units; maximum observed size is **1,668 estimated tokens**. No graph slots or budget changes were introduced.

Graph versus same-arm fact ablation retains the same raw evidence in 23 fallbacks. A1 DEV-C1 displaces one raw chunk and adds the novel reviewed claim described above. Separately, A2 versus A1 displaces/adds **21/21 Vector**, **27/27 Hybrid**, **10/31 Facts** and **9/31 Graph** raw-chunk occurrences across eight questions; these are occurrence counts, not distinct corpus chunks. Exact retained/displaced/added IDs are in `descriptive-analysis.json`. A2 often selects more raw units, but increased raw presence does not establish complete gold coverage.

Selector changes alter Graph anchors for **8/8** questions and retained graph pools for **2/8**. The Graph A2/A1 contrast includes that anchor interaction; it is not a pure fixed-pool reranker effect. Legacy Graph's merged-pool ordering also differs from its fact ablation, as preregistered.

## Query work, timing and resources

After the measured matrix, **24 separate read-only EXPLAIN/PROFILE executions** inspected one saved representative call per arm/family. All twelve PROFILE calls reproduced the saved rows, returned at most five, used indexed plans and avoided AllNodesScan. Actual maximum operator rows reached **2,904**, with the largest representative workload **13,284 database hits** in A1 finding linkage. Returned-row LIMIT 5 is not a bound on internal operator work. These are representative plan measurements, not totals for every matrix query. Positive native fixtures additionally verify indexed Finding/entity starts, ownership, roles, revocation and non-authoritative MENTIONS behavior.

| Mean `run_query` wall time, ms, all eight | A0 | A1 | A2 |
|---|---:|---:|---:|
| Vector | 312 | 457 | 932 |
| Hybrid | 278 | 429 | 1,049 |
| Hybrid + Facts | 413 | 488 | 1,425 |
| Graph | 962 | 1,492 | 1,501 |

The runner starts one resident query encoder before the matrix, with no inference warmup. First A2 loads the reranker; its first readiness measurement was ~85 ms asset verification/~118 ms load. Later requests reuse weights, recheck all seven assets and start an empty request-wide feature cache. A2 inferred **921 pairs total**, at most **45 per request** against the 88 bound; **339 distinct question/feature keys** have exact overlapping scores across modes. Cache hits/stage timings/native lengths are retained. CPU float32, batch one, 12/12 torch threads and concurrency one remain pinned.

Wall time includes the complete `run_query` call and resource probes; it excludes resident encoder construction, artifact serialization and separate display/export validation. V2 `request_elapsed_ms` separately includes scope/model readiness; `retrieval_ms` retains the inner-service boundary. A0 has no scope-inclusive timer. OS/Neo4j caches were uncontrolled and likely warm; fixed order and first-query planning outliers make this a diagnostic pass, not a stable speed comparison. RAM/GPU observations are saved per request; no Qwen generation or simultaneous-generation capacity was tested.

## Verification, preservation and decision

**239 offline tests passed**, seven integration cases deselected; **five configured integration cases passed**. New tests cover unbounded candidate unions with eight-premise AND support, overlap credit, unanswerable N/A, forged/incomplete sources, current approvals, and novel-versus-already-available support. **2,014 offline consistency checks** verify saved hashes, source tree/snapshots, packing and pre-fallback replay, shared logits, parity, pool matching and exact fallback. The scoped Streamlit server was restarted and one additional explicit V2/cross-encoder Graph query succeeded on port **8502**, with synthesis disabled and a saved current-code artifact. This UI query is outside the 96-request matrix.

One test-development pass failed because a new test block included another fixture's variables; it was corrected before execution, and both failed/passing XML receipts remain. A post-run descriptive helper first omitted explicit UTF-8 on Windows and stopped before its descriptive output; the corrected helper read the unchanged saved runs. No matrix request was repeated, no scores/gold were edited, and no unresolved application failure remains.

Current source/review/model/target bindings are preserved: 20 papers/1,427 chunks/51 approvals, review head `03724d5d24329b73ff53ca69bebc2df4b7e3707576ea15c8b7ccd12687019c64`, graph fingerprint `58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe`. Final acceptance rechecks the original **118 frozen files**, original source graph/report, stopped consumed evaluation target, pinned model assets and unchanged dependency files. The original checkout receives documentation/navigation updates only.

**D55 continuation gate fails in both A1 and A2:** mean Graph minus same-arm Facts recall is **0**, with **zero novel-source support witnesses**. Stop the larger fresh Graph answer trial under this hypothesis. Keep these limited/negative findings for reporting; do not change papers, force graph slots or start M5.5/M5.6 to seek a favorable result. A genuinely different objective, enrichment factor, reranker-only study or architecture requires a recorded scope/comparison amendment before new work. None is authorized or implemented here. No default/profile promotion is warranted.

Artifacts: `runs/retrieval-v2/m5-4/` contains test/native receipts, UI provenance, descriptive analysis, final acceptance and Git handoff. Its `comparison-v1/` contains the exact manifest, 96 reservations/outcomes/runs, completion receipt, offline results and plan probes. `scripts/run_m5_comparison.py` refuses restart/resume of a started matrix; the offline scorer refuses to overwrite results. Do not repeat this completed matrix.

**Skipped by scope:** answer synthesis/abstention-quality scoring, paid probes, combined Qwen resource testing, new claim review, private authoring/fresh final evaluation. **Blockers: none for M5.4.** Generation/extraction/paid calls, private access, downloads and dependency changes: **zero**. The unchanged public set is small and development-used; no general answer-quality improvement or superiority claim follows.
