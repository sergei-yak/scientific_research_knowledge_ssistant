# Implementation plan

**Status:** Planning only. No application code, dependency installation, service checks, or tests have been completed by this documentation task.

**Requirements:** `project_spec.md` is authoritative. This document supplies implementation boundaries, sequencing, and verification; it does not replace the spec's retrieval or evaluation rules. All milestones below are **not started**.

## Decision log

These decisions are incorporated into the authoritative spec; implementation verification is pending. Append changes with reason, affected requirements/task IDs and verification evidence rather than silently replacing decisions.

| ID | Decision and reason | Verify in |
|---|---|---|
| D1 | Corrected three-versus-four template inconsistency to **four**. | M3.1 |
| D2 | Graph fallback is explicit and preserves baseline evidence; providers never switch automatically. | M1.1, M3.1 |
| D3 | Added claim/condition fields and source offsets/hashes to the evidence contract. | M1.1 |
| D4 | Five ordered rows per seed/template; up to 80 intermediates, 40 unique graph candidates. Indexes, timeouts and plan inspection also bound work. | M3.1 |
| D5 | Retain Python 3.11; record exact tested dependency/image/model identities, rather than treating aliases as snapshots. | M0.1–M0.3 |
| D6 | One live provider enables early development; both adapters remain required by M3. Offline work can proceed while live checks are unresolved. | M0.3, M3.3 |
| D7 | Independent gold source-span annotations credit raw chunks and structured evidence equally, including AND/OR support. | M1.1, M4.2 |
| D8 | Targeted extraction/review caps and human approval checkpoint bound semester workload. | M2.1–M2.2 |
| D9 | A synthetic fixture proves traversal; real-paper acceptance requires correct behavior, not an observed graph advantage. Record corpus selection before expansion. | M3.1–M4.1 |
| D10 | Autonomous routine work, budgeted paid operations, human review and one authorized frozen final evaluation have distinct boundaries. | M0.3, M2.2, M4.2 |
| D11 | Test logical snapshot reconstruction before freezing; native offline dump is optional and never overwrites the working volume. | M3.3 |

**M1 design checkpoint, before M2:** Specify candidate pooling and RRF ties, deterministic embedding text for chunks/facts, interval-aware deduplication and evidence assembly. Graph reuses the exact Hybrid + Facts builder. Question overlap counts question aliases only; seed aliases can seed traversal. Define per-template start keys, directed relationship patterns, ordering and timeout configuration. Validate these contracts on synthetic/development cases before real claim review; changes require a logged development decision, never gold-driven tuning.

## Module boundaries

Planned package: `src/research_assistant/`; service integration tests live separately from offline tests.

| Module | Owns |
|---|---|
| `contracts.py`, `settings.py` | Shared Pydantic models, configuration validation, run identities; no network/database access. |
| `ingestion/` | Corpus manifest, OpenAlex cache, PDF parsing, source locations, extraction passages, fixed retrieval chunks. |
| `embeddings/` | Encoder loading, tokenizer checks, encoding settings, dimension checks; no cross-model vector mixing. |
| `llm/`, `extraction/` | Provider adapters/usage limits; candidate extraction, source-quote validation and alias suggestions. No approvals. |
| `review/` | Review export/import, revision eligibility, audit history, invalidation and preparation-cost records. |
| `graph/` | Constraints/indexes, idempotent persistence, fixed Cypher templates, bounded reads, snapshot/rebuild operations. |
| `retrieval/` | Four retrievers, RRF, candidate ordering, shared evidence renderer/assembler, budget checks and fallback. |
| `generation/` | Grounded answer/comparison generation and citation-ID/source validation. |
| `evaluation/` | Question manifests, context-based gold-fact scoring, blinded exports, timings and experiment reports. |
| `cli.py`, `__main__.py`, `ui/app.py` | Thin entry points calling shared services; Streamlit holds temporary presentation state. |

Dependency direction: entry points call services; services use contracts and explicit provider/repository interfaces. Graph storage never imports the UI; evaluation invokes the same retrieval and generation services as the product.

## Shared contracts and artifacts

Implement and validate these before their first consumers; use the domain fields in spec section 4 rather than maintaining a second schema here.

- **Source identity:** `PaperManifestEntry`, `Chunk`, `SourceExcerpt` and `SourceSpanRef` use spec section 4's immutable normalized text and offset/hash convention. Validate multi-page support and pass only actually rendered spans to scoring.
- **Claims/review:** `ClaimRevision` covers Evaluation/Finding payloads and supporting excerpts. `ReviewDecision` binds reviewer, decision, reason, timestamp and source/entity revisions. Only current human-approved revisions produce `FactText` or authoritative graph candidates.
- **Providers:** `LLMClient` returns validated text/structured results plus usage/model metadata, or an explicit error. Capture full request identity for caches; errors and unavailable usage are not successful zero-cost responses.
- **Retrieval:** `QueryRequest` carries question, requested mode and snapshot identity. `RetrievalResult` contains assembled `EvidenceItem[]`, estimated token count, requested/effective mode, fallback reason, and candidate/path audit records. Apply the spec's six-unit/excerpt/token limits after rendering.
- **Answer/run:** `AnswerResult` references returned excerpt IDs and distinguishes insufficient evidence. `RunArtifact` joins configuration/snapshot hashes, retrieval result, rendered-context hash, provider output, timings and scores. Citation existence is machine-checkable; semantic support still requires evaluation.
- **Evaluation:** `EvaluationQuestion` and a graph-independent gold JSONL implement section 4's annotation contract. Unit-test alternative fact sets, alternative passage sets, jointly required spans, truncation and graph-ID independence before M2. Store blinded `HumanScore` separately from the reveal mapping. Gold annotations are evaluator inputs, never retrieval inputs.

Keep public configuration, synthetic fixtures and sanitized manifests under version control. Use ignored local `data/` and `runs/` for source/review/run artifacts. Development annotations may live there; held-out questions/gold/reveal mapping live in an evaluator-controlled **external** directory, not a repository file hidden only by `.gitignore`. Define JSONL/CSV columns and round-trip tests when introduced. CLI operations cover manifest validation, ingest, review export/import, index build, query, snapshot export/restore and evaluate; record executable flags when available.

## Recovery and freeze procedure (implement by M3)

1. Quiesce application writes; export a consistent snapshot into a new directory: stable-ID-sorted nodes/relationships including embeddings, schema/index definitions, review log, source/chunk manifests, code/config/prompt identities and checksums. Keep source documents or verified local copies available for reconstruction.
2. Verify export hashes; restore through the graph repository into a **fresh disposable Neo4j volume** with the pinned image. Recreate indexes and await `ONLINE`; never import over the working volume.
3. Compare semantic export checksums, IDs/counts, approval eligibility, support links and vector dimensions. Run development queries/acceptance scenarios, revocation fixtures and offline scoring replay. A rebuilt approximate index need not reproduce identical top-k ranks; preserve original run candidates/contexts.
4. Record exact export/restore commands, image, volume targets and outcomes in the milestone evidence. This tested logical route is required; an untested backup file is insufficient.
5. Optional native backup: schedule database downtime, stop the owning service, and use matching-version admin tools in a one-off container for `neo4j-admin database dump neo4j --to-path=/backups`. Load with `neo4j-admin database load neo4j --from-path=/backups` into a fresh offline target. Record actual Compose mounts/flags before use, restart the service and check health. Do not copy a running database's files or overwrite a working volume.
6. M4 freeze records hashes of corpus/graph/review exports, lockfile/code, prompts/configuration, annotation files and the restore verification record. Protect the frozen snapshot with an application write guard; do not assume Community Edition supplies Enterprise access-control features. The evaluator supplies private-file hashes without exposing content to the development agent.

## M0 — Environment and dependency gate

- [ ] **M0.1 — Runtime/lock:** Record Python 3.11, `uv`, Docker/Ollama availability, GPU driver and memory. Create package/build settings, `.gitignore`, `.env.example`, pytest integration marker and Compose configuration when implementation begins. Resolve specified dependencies with `uv lock`; install with `uv sync --locked`, then use `uv run --locked`. Record required imports, CUDA/device checks, both encoder limits/dimensions and token estimator. Log conflicts instead of silently substituting versions; establish a Git baseline.
- [ ] **M0.2 — Core database:** Pin the image, persistent volumes, localhost ports and health check. Verify credentials, parameterized operations, vector/full-text procedures and disposable smoke indexes reaching `ONLINE`. Keep smoke data separate from the corpus and preserve existing volumes.
- [ ] **M0.3 — Provider/resource readiness:** Validate both SDKs/configuration; explicitly choose one provider for real text/structured probes, within user-approved paid limits if applicable. Record request/output/concurrency/retry controls, identity, latency and failures. Measure RAM/VRAM with Neo4j plus encoders and, when available, local Ollama; record offloading/context limits and any deferred simultaneous-operation check. Track the secondary provider as pending until M3.3 if unavailable.

**Gate:** M0.1–M0.2 establish core readiness; one chosen live provider enables the real M1 answer path. Missing credentials/budget or secondary-provider readiness never counts as a pass, but independent offline foundation/retrieval work can continue. Provider changes are explicit choices. No installations or smoke probes have been performed by this documentation task.

## M1 — One-paper vector baseline and shared foundation

- [ ] **M1.1 — Contracts first:** Implement shared contracts, selected provider adapter and graph foundation. Finalize the M1 design checkpoint and independent gold-annotation contract/scorer before M2; test raw-chunk/fact parity, multi-span AND/OR support, truncation and invalid source hashes using offline fixtures. Real development annotations follow in M2.3; the secondary adapter may remain pending.
- [ ] **M1.2 — Real baseline:** Parse the first pilot paper, freeze tokenizer-safe chunks, persist MiniLM embeddings and produce a vector-retrieved cited answer through the chosen provider/CLI. Establish shared rendering/budget enforcement, run artifacts and exact commands; claim review and graph expansion follow later.

**Gate:** A real paper-to-cited-answer run is inspectable. Offline tests cover stable source IDs, rerun idempotency, dimensions, budget enforcement, invalid citation IDs and insufficient evidence; live checks are recorded separately.

## M2 — Five-paper evidence and review pilot

- [ ] **M2.1 — Bounded pilot:** Select five accessible related papers; record reasons, rights, hashes, coverage and citation uncertainty. Inspect each PDF. Using the chosen provider, extract only the spec's bounded passages/candidates and prepare complete review bundles. Report generated/validated/approved/rejected/pending counts, uncovered sections, elapsed review time and API/indexing cost.
- [ ] **M2.2 — Human checkpoint:** Present bundles and wait for recorded human decisions before dependent approved-claim work. Timebox expiration leaves claims pending, not approved. Independent fixtures and other authorized work may continue. Import decisions, build approved FactText and test source/alias/support invalidation, wrong-paper contamination and contradictory findings.
- [ ] **M2.3 — Development evidence:** Prepare eight development questions in the prescribed category allocation and human-validated gold spans independent of graph IDs. Exercise qualitative limitations and multi-passage evidence. Keep synthetic adversarial fixtures separate from the real-paper benchmark; do not read held-out content.

**Gate:** Every pilot paper has an inspection/coverage record; approved evidence supports the planned discovery/comparison/limitations scenarios. Review round-trips and revocation pass, including wrong-paper/dataset contamination. If evidence is insufficient, adjust corpus/coverage before expansion.

## M3 — Retrieval conditions, UI and five-paper acceptance gate

- [ ] **M3.1 — Controlled retrievers:** Implement the M1 pooling/ordering contracts for Hybrid, Hybrid + Facts and Graph. Test four templates, bounded candidates, identical fact content, budget and fallback. Save `EXPLAIN` for each template and representative read-only `PROFILE` plans on fixture/pilot data; inspect seed-index use, rows/database hits and timeout behavior. `LIMIT 5` alone is not a work bound. Prove new cross-paper traversal with a controlled synthetic fixture, without requiring a real-corpus win.
- [ ] **M3.2 — Product acceptance:** Add minimal Streamlit workflows and CSV export via services. Run discovery, comparison, limitations and export development scenarios, including missing/incompatible conditions; inspect real-paper paths and correct fallback independently of performance gains.
- [ ] **M3.3 — Integrations/recovery:** Complete both adapters' real text/structured-output smoke tests and local resource checks. Execute the recovery procedure into a fresh disposable target; retain commands, checksums and successful acceptance/scoring replay.

**Gate:** Four retrieval conditions and all product scenarios pass on five papers; both provider integrations, synthetic traversal proof and restore test have evidence. Required human decisions are recorded. Only then expand; a secondary-provider failure blocks this final integration gate, not unrelated development.

## M4 — Corpus expansion and frozen research evaluation

- [ ] **M4.1 — Corpus/scoring readiness:** Record final corpus selection rules before expansion to 20–30 papers, without using observed graph gains/held-out questions. Apply review caps and complete required decisions. Validate scorer/blinded exports on development fixtures. An evaluator finalizes the 24-question stratified manifest and independent support annotations, keeping held-out content external.
- [ ] **M4.2 — Freeze checkpoint:** Produce and verify the hashed freeze manifest, restore record, budgets and complete run plan. Obtain explicit authorization for the final evaluation once; do not request approval for each already-budgeted call. The dedicated runner reads private evaluation inputs at runtime; ordinary agents/generation receive no gold answers. Acknowledge any prior exposure.
- [ ] **M4.3 — Run/score/report:** Run four conditions with MiniLM and one frozen generator; separately compare vector-only MiniLM/MPNet on identical chunks/questions. Save actual contexts, prompts, candidates, responses and timing/cache metadata. Score anonymous answers before mode reveal, then report paired results, costs, cases and limitations. If equivalent new support needs human adjudication, preserve frozen scores and report an amended annotation/rescore across all modes. Log bug corrections/reruns; never retune and relabel them as untouched held-out results.

**Gate:** Saved artifacts reproduce metric calculations and support the report, even if a fresh provider call or rebuilt approximate index differs. Encoder comparison and product acceptance remain independently verifiable; graph improvement is not required.

## Progress record

Checkboxes above are the actionable task register; all are unchecked. For each task, append `task_id | status (not_started/in_progress/waiting_for_human/blocked/done) | files/commit | exact checks + outcomes/skips | artifact paths | decision IDs | next action`. Pending human decisions block only dependent tasks. A milestone report summarizes these records; code existence is not verification. No implementation has been authorized by this documentation-editing task.

Operational references: [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/), [Neo4j dump/load](https://neo4j.com/docs/operations-manual/current/docker/dump-load/), [Neo4j 5 query tuning](https://neo4j.com/docs/cypher-manual/5/planning-and-tuning/query-tuning/). Check command flags against the pinned version before execution.
