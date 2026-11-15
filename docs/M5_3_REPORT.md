# M5.3 — Pinned model and common selector

**Complete, 2026-11-15.** One verified cross-encoder selector now applies to all four V2 modes. Exact input/score/runtime identity, request-wide caching, bounds, atomic packing and fallback are tested. The one-question engineering check changes evidence ordering but still selects no new Graph evidence. **Quality improvement and the full development ablation remain unmeasured until M5.4.**

## Model decision and environment

The [decision](../manifests/M5_3_MODEL_DECISION.md) and download intent were recorded **before adapter implementation**. Selected model: [cross-encoder/ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/tree/233902d25c440f23af6f7d6e94d2946bac0bee0a), immutable revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Its publisher describes English MS MARCO passage-ranking training and Apache-2.0 licensing. Selection was based on the existing stack and bounded CPU workload, not observed development/held-out quality. Published benchmark results do not establish quality on this corpus.

The [executable model manifest](../manifests/reranker-msmarco-minilm-l6-v1.json) pins seven files totaling **91,819,431 bytes** (~87.6 MiB), within the declared 150 MiB bound. Weights are safetensors, SHA-256 `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`. Canonical manifest SHA-256: `03717f73ce501290c63eabecff41eb599e948a9c84d414dec49297f584ef0030`. The historical config name mentions L12; actual config/loaded architecture has **six layers**, 384 hidden dimensions and one scalar logit. That mismatch is disclosed rather than used to choose a different model silently.

No application dependencies changed: **95 resolved / 79 installed compatible**; original `uv.lock`/`pyproject.toml` bytes remain unchanged. Verified runtime: torch **2.6.0+cu124**, transformers **4.57.6**, sentence-transformers **4.1.0**, safetensors **0.8.0**, huggingface-hub **0.36.2**. The adapter uses the existing Transformers tensor API so native lengths and raw logits are explicit; sentence-transformers remains the encoder stack. Optional Xet support was unavailable, so the existing Hub client used HTTP; no extra package was installed.

Local-only inference is CPU float32, single-pair batch, evaluation/inference mode, 12 intra-op / 12 inter-op threads, concurrency one and no automatic retry. Runtime/model/asset mismatches fail explicitly. Seven file hashes are revalidated before each request even when weights remain resident; no remote code, pickle fallback, implicit download, score clipping, sigmoid or softmax is used.

Pre-adapter resource check: MiniLM resident, existing Neo4j services running, **88 synthetic pairs in 2.23 s**; resident MiniLM load ~0.78 s and reranker load ~0.18 s with warm file caches. Available RAM was ~16.70 GB before/~16.62 GB after. This demonstrates this bounded CPU check, not simultaneous Qwen-generation capacity or a stable latency benchmark. Qwen generation was not exercised.

## Shared contracts and implementation

- `retrieval/reranker.py` owns manifest verification, local BERT scalar inference, native 512-token preflight, resident weights and single-inference locking. It validates the entire new stage before any forward pass. Overlength, nonfinite/wrong-shaped output, missing assets, incompatible runtime or busy inference stops the arm; it never becomes a retrieval fallback.
- `retrieval/selection.py` owns one feature/score/tie/cache/trace contract for **Vector, Hybrid, Hybrid + Facts and Graph**. Inputs are exact question + full normalized source chunk, or the exact current approved fact `embedding_text`. Shared fact validation moved from the product module to the catalog; display/export and scoring reuse it. Paths/origin/candidate IDs/gold/clipped context do not enter model features.
- Raw logits sort descending, then original fused/cosine baseline rank ascending, then stable ID. New graph-only items lack baseline rank. No graph slots or origin bonuses are introduced. The original vector eligibility threshold, channel pools/RRF, graph pre-pruning and six-unit/1,800-token atomic packer remain unchanged.
- One request-wide feature cache includes baseline/seed scoring in the **88 unique candidate** cap. Graph reuses baseline scores rather than scoring the full union again. Stage traces bind feature hashes, native lengths, logits, ranks and the actual common packer's exclusions. Unscored pre-pruned graph candidates retain no invented model score.
- Same-profile Graph fallback preserves the complete reranked fact-ablation evidence/context/aliases/budget/candidates. A high logit cannot override atomic evidence limits. Reference mode does not load/require a reranker; baseline + reranker is rejected explicitly.
- CLI `--selector cross_encoder` and UI **Evidence ordering → Shared reranker** are explicit. Default selector remains `reference`; the pilot/baseline defaults are unchanged. Requested/effective profile, selector and mode remain visible. Failed CLI/UI selection artifacts retain diagnostics; reruns/exports revalidate without inference. V2 synthesis remains disabled.

Model readiness/cache timing and scope-inclusive `request_elapsed_ms` are separate from the existing inner `retrieval_ms` boundary. Future latency reports must state the boundary and warm/resident state. These engineering measurements are not directly comparable with the old frozen study's timing.

Specification **6.3** records the model/backend pin without changing R2 algorithms or budgets; exact 6.2 main/submission archives are retained alongside 6.1. The source corpus/review scope and original completed evaluation are unchanged.

## Actual verification

**235 offline tests passed; seven integration cases deselected.** New coverage includes request-wide 48+40 caching/caps, identical features/scores under path/pool changes, stable ties with missing baseline ranks, raw negative logits, vector pre-eligibility, all-mode plumbing, immutable fact/raw inputs, overlength-before-any-forward, score/count/length failures, asset/runtime/path tampering, concurrency, exact atomic fallback and saved failure diagnostics. Existing tests continue to pass.

**Five configured integration cases passed:** preserved native retrieval/review/MPNet guards, V2 route fixture, and real pinned-model contracts. The real model returns exactly repeated scores under reversed single-pair order, accepts a native 512-token boundary and rejects 513 tokens before any forward pass. Fixtures clean only UUID-owned data; no production reviews are simulated or edited.

**Native-length feasibility:** all eight unchanged public development questions and all 1,427 chunks/51 canonical fact texts were counted without relevance scoring or gold answers. Maximum question/chunk/fact lengths: **58 / 198 / 166**; three special pair tokens yield an upper bound of **259**, below 512. Arbitrary user inputs still require explicit native preflight.

**Engineering matrix:** one existing public discovery question, two V2 selectors × four modes, eight retrieval-only runs. All four reference context hashes match M5.2. Overlapping candidate features have **exactly matching** cross-encoder logits across modes. Results:

| Cross-encoder mode | Unique candidates / model pairs | Selected units | Estimated tokens | Effective mode |
|---|---:|---:|---:|---|
| Vector | 12 / 12 | 6 | 1,434 | vector |
| Hybrid | 24 / 24 | 6 | 1,434 | hybrid |
| Hybrid + Facts | 43 / 43 | 6 | 1,443 | hybrid_facts |
| Graph | 44 / 44 | 6 | 1,443 | hybrid_facts (exact fallback) |

Graph's second stage inferred **one new pair**, reusing its 43 baseline pairs; it returned 65 source-backed rows and selected no novel graph candidate. The 44 distinct feature hashes are the union, not 44 features shared by every mode. No gold recall or answer-quality score was calculated. A real CLI call and an actual query on the restarted UI additionally passed shared source/export validation; the UI shows the selected reranker, requested Graph/effective fact ablation and disabled synthesis.

## Preservation, artifacts and next task

Development target remains `dbu-m4-recovery-m5dev-2d43d2b9a2fa`, scope head `03724d5d24329b73ff53ca69bebc2df4b7e3707576ea15c8b7ccd12687019c64`. All **51** original approvals and catalog hash `8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989` remain unchanged. Target fingerprint is `58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe`; original graph is `e56b78bc3d96e1517f249433518f20087707bf872f5990ca116c412b663f5325`. Final acceptance verifies source/ledger/model preservation and the **118 frozen files** from the original checkout; the consumed target remains stopped.

Evidence under `runs/retrieval-v2/m5-3/`: pre-adapter `model-preflight-v1/`, `native-length-feasibility.json`, offline/native XML reports, `native-model-verified.json`, `engineering-smoke/`, `cli-reranked-graph.json`, UI provenance, acceptance and handoff. Model assets stay ignored. An initial UI restart guard safely refused the shared interpreter child; its known development-venv parent was verified before stopping/restarting only that service. No unresolved application failure remains.

**Skipped/pending by stage:** full M5.4 development ablations/candidate-vs-final recall/go-no-go; claim enrichment/human decisions; Qwen/paid generation; fresh private annotations/final study. Generation/extraction/paid calls, private access and dependency upgrades: **zero**. One authorized model download occurred; no corpus/index/review write occurred outside disposable native fixtures. No M5.3 blocker remains.

Continue in `C:/Users/serge/DBU-GraphRAG-Worktrees/retrieval-v2-m52-54d8b329`. **M5.4 is next:** run the recorded matched development matrix, score saved candidates and final contexts offline, and make the recorded go/no-go decision. The old private set stays retired; this milestone grants no final-run authorization.
