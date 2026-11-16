# M5.5 — Fresh evaluation readiness proposal

**State: preparation in progress; this is not a freeze or execution authorization.** The user requested M5.5 after the M5.4 no-go was explained and reserved demonstration work for M6. Specification 6.4 permits readiness preparation only. The negative result and original stopping decision remain part of the record; any later study must explicitly disclose and authorize continuation despite that decision. No architecture, catalog, paper, model or evidence-budget change is proposed.

## Purpose and matched design

Proposed purpose: independently describe the frozen policies' answer/evidence behavior, including negative effects, on fresh questions. This is not a claim that the failed development gate passed. Do not tune after private authoring, pick favorable papers, promote the reranker or require a Graph win.

Retain all three development policies as matched references rather than select a favorable arm after inspecting results:

| Arm | Profile / selector | Four modes |
|---|---|---|
| A0 | baseline / reference | vector, hybrid, hybrid_facts, graph |
| A1 | retrieval-v2 / reference | vector, hybrid, hybrid_facts, graph |
| A2 | retrieval-v2 / cross_encoder | vector, hybrid, hybrid_facts, graph |

The main same-selector comparison is A2's four modes. Primary contrast: A2 Graph versus A2 Hybrid + Facts. A1's same-arm contrast, A2/A1 selector contrasts and A1/A0 route contrasts are separately labeled secondary/exploratory comparisons. Selector-dependent Graph anchors can change, so A2/A1 Graph is an end-to-end policy comparison, not a pure fixed-pool reranker effect. Existing pool/threshold and merged-order differences remain disclosed. Include all questions and all arms; no MPNet repeat.

This is a **12-condition proposal**, not the previous four-condition study. It requires **288 answer runs and 288 human scoring rows**, three times the previous 96-row form. The user may revise the proposal before new private authoring/freeze; a revision must be recorded before execution. No calls are authorized by these numbers.

## Proposed limits and controls

- **24 questions:** eight unchanged, currently human-validated public development questions plus sixteen fresh held-out questions (four each direct, cross-paper, multi-hop, unanswerable). Report the partitions separately; development is not an untouched test.
- **288 maximum logical retrieval requests / 288 local generation requests**, including failed or unknown attempts; zero additional encoder-comparison reads, zero automatic retries, concurrency one and **$0 paid spend**. A request with no evidence may abstain without a provider call; it still consumes its planned logical slot. Separate readiness probes need their own bounded plan; none are included or authorized here.
- Local Qwen at its verified installed digest; existing MiniLM query encoder and pinned cross-encoder, original 20 papers/1,427 chunks/51 approved facts. All modes share six units/1,800 estimated tokens, exact sources and approvals; generator context/output remain 4,096/512 tokens. No automatic provider substitution or model/index rebuild.
- Provisional ordering: seed **5551**, seeded question order with twelve conditions rotated by question position. Keep paired conditions on identical questions/target/sources/catalog; record actual order and cache state. This ordering needs a versioned runner; the legacy four-condition rotation is not compatible.
- One new isolated, physically read-only restored target. Pin source graph/review/index/container/volume/runtime/code/model/feature identities after compatibility and restore checks. Preserve the working scope, all previous snapshots and consumed targets.
- Keep durable once-only external execution reservations; retain failed/interrupted attempts. Keep stripped prompts separate from gold, load gold only after generation, and seal real anonymous human scores before any condition reveal. Use one scoring/budget/source contract, not arm-specific copies.

## Fresh authoring and review

Prepared public-only input bundle: `runs/retrieval-v2/m5-5/readiness-v1/evaluator-public-bundle/`. It contains verified normalized sources, current approved facts, source coverage and stripped development questions. It excludes development gold, retrieval runs/results and all private data.

Proposed fresh evaluator output root, **not inspected or created by development**: `C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1`.

A new isolated evaluator with **no development-chat history** must be explicitly authorized before private work. For non-paraphrase screening, the requested additional evaluator-only access is the retired **stripped questions file only**, `C:/Users/serge/DBU-GraphRAG-Evaluation/expansion-v1/questions.jsonl`. The evaluator must not list that directory or read its old gold, answers, scores, notes, executions or reveal maps. The developer receives only counts, hashes, readiness flags and a human-review location. This is procedural context separation on the same account, not OS isolation.

The evaluator follows `docs/M5_5_EVALUATOR_TASK.md`. Fresh annotations need independent exact source spans/AND-OR sets, source-scoped absence rationales and real human validation. Similar scientific topics do not justify reusing an old question's meaning/reference-fact combination. No retrieval probing or gain-based selection is permitted. If sixteen distinct feasible questions cannot be supported, report that limit instead of fabricating them or altering sources. Earlier 16-question approvals do not carry over. An authoring receipt grants no execution permission.

## Implementation gaps found during M5.5 preparation

1. The legacy `RunPlan` and final receipt are fixed to four conditions / 96 generations / 144 retrievals and repeat MPNet. Their reader/runner must remain valid for historical artifacts. New versioned contracts must represent arm/profile/selector/scope/condition IDs and the new limits without relabeling or weakening old receipts.
2. The legacy runner constructs default-baseline requests; it does not pass V2 profiles/selectors/scopes. Its aggregate/blinding labels must distinguish full conditions and keep the mapping external until real score sealing.
3. `run_query` intentionally rejects V2 synthesis. An evaluation-only execution boundary must require the new exact authorization and verified frozen scope before generation; do not enable it by removing that guard globally or by using the UI as a runner.
4. The live V2 scope validator requires its current unfrozen development target/container. A fresh read-only evaluation copy needs a distinct attested scope contract, not repointing or editing the working declaration. Recovery must not restore old endpoint metadata blindly.
5. The old public-file allowlist omits new M5/reranker locations. A versioned narrow allowlist must support the actual new assets while continuing to reject external/private/symlink/secret inputs. The old reader must not become a permissive bypass.
6. Local Qwen is installed and its service lists successfully; current combined generation/reranker capacity and fresh inference are **not tested** in this step. Readiness probes need separately recorded numerical limits before use.
7. No fresh held-out data, attestation, human review, recovery target, final freeze hash or final-run authorization exists yet. No placeholders or old attestations may be presented as readiness.

## Verifiable completion gates

**M5.5.1:** Public proposal/audit/bundle, exact source/review/model/baseline preservation, precise evaluator scope and M6 reservation. Preparation checks are separate from research authorization.

**M5.5.2:** Versioned profile-aware contracts/runner/read-only scope and blinding changes, with synthetic/offline tests for exact authorization, consumed receipts, all condition identities, private-path guards, budget/once-only accounting, source/approval checks, exact fallback and error containment. Preserve baseline behavior and frozen source checkout.

**M5.5.3:** Fresh isolated authoring authorization, sixteen independent draft annotations, novelty/feasibility/absence checks, real human decisions with exact bindings/time provenance, and public attestation without developer exposure. Only the evaluator accesses private content.

**M5.5.4:** Bounded local readiness probes and a new read-only restore proof; actual runtime/model/resource/index/source checks. Failures stay failures and only dependent gates pause.

**M5.5.5:** Finalize the exact matched design and bounds, freeze verified executable/model/data bytes, disclose continuation despite the negative development gate, then request one exact-freeze final-run authorization as the final checkpoint. M5.6 does not start automatically. M6 demonstration remains a separate unstarted milestone.
