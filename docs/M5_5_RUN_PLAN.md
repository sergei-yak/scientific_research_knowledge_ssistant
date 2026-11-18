# M5.5.5 — Exact frozen exploratory run plan

**Prepared and verified; awaiting explicit human authorization. No new final study has started.** This plan finalizes the original matched proposal plus its mandatory author-context amendment. M5.4's negative gate remains recorded. M6 demonstration remains separate.

## Exact proposal and limits

Freeze: `runs/retrieval-v2/m5-5/freeze-matched-v1.json`.

**SHA-256: `c64da42c62fe46bbd51220738a0016d00742bb1c606575cbb68c4db21374329c`**

| Item | Frozen value |
|---|---|
| Questions | 24 total: eight unchanged human-validated development questions and sixteen fresh human-approved held-out annotations; six per category overall, two development/four held-out |
| Policies | Twelve conditions: A0 baseline/reference, A1 retrieval-v2/reference, A2 retrieval-v2/cross_encoder; each runs vector, hybrid, hybrid_facts and graph |
| Request ceilings | **288 logical retrieval attempts / at most 288 local generation attempts**; failed/unknown reservations retained; zero additional encoder-comparison reads |
| Generator | Local `qwen3.8:latest`, digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`; observed Qwen35 27.3B Q4_K_M metadata |
| Context/output | **4096 context / maximum 512 output tokens per request**, temperature 0, model request timeout 180 seconds |
| Concurrency/retries/spend | **1 / 0 automatic retries / $0 paid**; no model/provider substitution |
| Evidence | At most six units / 1,800 shared estimated tokens, exact normalized sources and current approvals; database read-transaction timeout 30 seconds |
| Data | Original twenty papers / 1,427 chunks / 51 approved claims; no extraction, new papers or approval enrichment |
| Ordering | Canonical question-ID sort, seed 5551 shuffle, twelve-condition rotation. Across all 24 questions each condition occupies each within-question position twice; no per-partition/cache balance claim |
| Human scoring | **288 anonymous answer rows**; correctness and citation support in {0, 0.5, 1}, correct abstention separately where applicable, real reviewer/timezone timestamps required; optional notes and actual review time retained as supplied |

The primary matched contrast is **A2 Graph versus A2 Hybrid + Facts**. Report development and held-out partitions separately; the eight tuned development questions are not an untouched test. A1 Graph/Facts, A2/A1 selector and A1/A0 route contrasts remain secondary/exploratory. Selector-dependent Graph anchors make A2/A1 Graph an end-to-end policy comparison, not a pure fixed-pool reranker effect. Include every predeclared condition; do not select a favorable arm after results.

## Required disclosures before approval

- **Negative gate:** M5.4 found no mean Graph benefit over the same-arm fact ablation on the development set. This study deliberately continues after that no-go to describe the frozen policies, not to claim the gate passed or require Graph to win.
- **Question selection:** the author received outcome summaries through startup context despite having no development-chat history. The user accepted explicitly exploratory use. Human source approval does not remove possible outcome-informed question-selection bias. Read the [mandatory amendment](M5_5_STUDY_AMENDMENT.md); its original pending-review wording is historical, while the later sixteen exact-bound approvals remain current.
- **Capacity:** two readiness probes passed, but sampled free RAM fell to ~2.90 GiB and GPU use reached 11,847/12,282 MiB. Cold text latency was 72.6 s and padded JSON 28.2 s. Maximum-length output and 288-request endurance were not tested. Keep the frozen bounds; do not silently retry, shrink context or change models to get a completed run.
- **Inference limits:** paired descriptive wins/ties/losses and aggregate means on this small source-validated set support no population superiority claim. Shared contexts/fallbacks remain visible; a Graph request that falls back is not evidence of selected traversal benefit. No old/new held-out mean is a paired improvement comparison.

## Accepted physical and executable scope

Only **`dbu-m4-recovery-m5eval-cf4d3a031091`** may be started for this study, with its exact frozen container/image IDs and two owned volumes. It is currently stopped, configured server-read-only, and uses loopback Bolt 60495/HTTP 60496. Do not recreate it, restore over it, rebuild indexes, repoint the development scope or start the consumed M4 target.

Inputs under `runs/retrieval-v2/m5-5/m5-5-4-corrected-cf4d3a031091/`:

- `scope.json`: `8bce666642a7d4459b7c35dcb43f17fdd48a1e60ddad92dd5481f02a4ff5bf6f`.
- `snapshot/manifest.json`: `ae8f853cd2418b05cd194a548a082127a6e82dd7ddf0d9b1ca1a613c18d9a4f4`.
- Complete `report.json`: `3ef2a4e9b99186daeb11bac367526e2032b9e17ffc6ebefb19c8c941149585a1`. Physical-only proof does not qualify.

The freeze verifies **208 runtime/config/model files**, pinned MiniLM/cross-encoder policies and runtime versions, all copied assets, current source/head/catalog/development bindings and the unchanged source/human attestation. Source-tree SHA-256 is `c671340e9c49b1cc8bff224b7bb5427b6d79356ce1e80c176d60908f95f0c0c1`; code provenance at proposal creation is `d41396b108721898cbe2bde31c9dcdaccdeb0bd4`. Documentation-only commits before launch do not change these authoritative executable bytes. Record the launch Git HEAD and keep it unchanged across all288 slots and anonymous-packet export: shared blinding requires consistent code provenance. Record progress in ignored append-only receipts; defer tracked edits/commits until execution and packet export finish.

No model weights, prompts, retrieval rules, source/annotation bytes or runtime file may change under this hash. The original consumed freeze `62feb4b6…` and results remain historical and unchanged. The two-request readiness allowance is separate and exhausted; it grants no final-study request.

## Private inputs, execution and scoring

Only the dedicated exact-authorized `evaluation.matched_runner` may consume the approved external snapshot under `C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1`. Public preparation reads counts/hashes/lexical paths only; it must not list, stat or read that directory. The retired `expansion-v1` inputs are not used. Context separation is procedural on the same account, not OS isolation.

The authorization check and public freeze replay precede private-path access. The runner claims a durable once-only external ledger before private inputs or inference and reserves every slot before work. New output directories or authorization IDs cannot reset a started freeze. Any failure/interruption retains its reservations and stops execution; no automatic retry/resume or relabeling as an untouched test. Stop and retain the exact owned target after the attempt, preserving working data.

The runner loads stripped prompts for generation. Gold is parsed only after all answer slots finish; it never enters retrieval, selection or provider messages. The common exact-span scorer records evidence-fact Recall@6, with unanswerable N/A. Shared fallback/source/approval/budget rules apply to every condition.

Outputs, diagnostics, evidence scores, anonymous packets and reveal mappings remain external. The developer receives status/public aggregates only. The user later scores all 288 anonymous answers. No agent fills human scores; a complete hash-bound human form must be sealed before condition reveal. Report paired counts, correctness/citation means, evidence recall, latency/fallback/cache boundaries and preparation effort with the stated limits. Abstention judgments and timing fields remain separately recorded, never inferred from missing information.

## Authorization checkpoint

Requirements source: [project specification](../project_spec.md), R2.7/R2.8 and the M5.5 readiness exception: “A subsequent final study requires an explicit disclosed decision to continue despite that negative gate and exact-freeze authorization with numerical bounds.”

The user's instruction to do this preparation is not that final authorization. Approval must name this exact freeze and accept the bounds, negative-gate continuation and exploratory limitation. Save a separate actual human receipt; **never edit the freeze or turn the source-only attestation into permission**. Verify all commitments again before any private access. If approved, M5.6 executes this one study; otherwise keep the target stopped and freeze intact. No paid calls or automatic human scores/reveal follow from preparation.
