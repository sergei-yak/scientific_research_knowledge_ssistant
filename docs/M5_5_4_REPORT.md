# M5.5.4 — Local capacity and fresh read-only recovery

**Complete, 2026-11-17 user-facing date.** The bounded readiness checks passed; the fresh target is stopped and retained. This is engineering readiness, not a new scientific evaluation or authorization. M5.4's negative gate and the accepted exploratory author-context limitation remain. M5.5.5 exact freeze and deliberate final-run authorization are next; M6 remains reserved.

## Actual results

| Check | Outcome |
|---|---|
| Offline suite | **363 passed**, seven integration cases deselected; 28 new readiness cases cover budgets, copied-context accounting, failure preservation and harness/lifecycle guards |
| Public engineering retrievals | **24 total**: twelve original working-copy reads retained/revalidated, twelve restored-copy reads; all passed; exact contexts and selected IDs match for **12/12 conditions** |
| Restore | **1,996 nodes / 2,191 relationships**, complete graph/schema equality; second restore into the nonempty target refused |
| Corrected native fixtures | **2 passed / 0 skipped** on UUID-owned records in the copied runtime; graph/schema unchanged after cleanup. The earlier two failed fixture attempts remain recorded, for four total attempts |
| Read-only enforcement | Server write refusal/rollback and frozen projection/source/review guards passed before/after restored queries |
| Local text probe | READY marker passed; **27 prompt / 2 output tokens**, **72.6 s** including cold model startup |
| Local structured probe | Validated synthetic JSON passed; **1,700 prompt / 13 output tokens**, **28.2 s** |
| Combined residency | Qwen, CPU MiniLM/reranker and restored Neo4j operated successfully with context **4096**, output ceiling **512**, concurrency **1**, retries **0**. Four extra synthetic reranker pairs and two encoder checks passed |
| Copied runtime | **981 files / 769,849,506 bytes** verified; all **208** required executable/config/model assets match the current worktree |
| Preservation | Working graph/source scope, 1,427 chunks, 51 approvals, eight development approvals and sixteen attested held-out approvals unchanged; original consumed target remains stopped |

There were exactly **two local generation attempts**, **zero paid calls**, no downloads or extraction, no MPNet inference repeat and no developer access to private questions/gold/notes. The fixed public discovery question was used only for engineering comparison; no gold scores or quality-gain claim were produced. The live checks did not run a 24-question or 288-answer study.

## Model/resource observations and limits

The existing configured alias `qwen3.8:latest` resolved to digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`. Ollama reports a **27.3B Qwen35 GGUF, Q4_K_M**, resident size 18,125,611,331 bytes and 9,447,397,128 bytes in VRAM, with context length 4096. These are observed local model metadata, not a renamed architecture or substitute model.

Across 96 timed samples, available host RAM fell to **3,110,072,320 bytes (~2.90 GiB)**. GPU allocation reached **11,847 / 12,282 MiB**, leaving approximately **435 MiB**. Headroom is tight. Sampling describes the whole host and may miss exact peaks; it is not process isolation. Two successful synthetic requests do not prove maximum-length 512-token output, every full-context prompt or endurance across 288 requests. Keep the recorded single-request/no-retry limits; do not silently shrink context, switch models or expand concurrency. A final-run failure must retain accounting and stop for a disclosed amendment.

## Corrections and retained failures

V1 was rejected before any task claim because a bare public artifact root was incorrectly checked as a file prefix. The positive preflight regression now passes; its decline record is retained.

V2 completed twelve working reads and an exact restore, then two native fixtures failed. Their original-checkout context correctly triggered the development write guard against the new endpoint. That target, its snapshot and failure/XML/log files were stopped and retained. No generation or restored-corpus query occurred in that attempt.

The disclosed V3 continuation runs fixtures inside the verified recovery copy with copied `PYTHONPATH` and the same locked interpreter. It changes no write guard or working scope. It revalidates/reuses the twelve original source-bound references, checks all retrieval/model/provider kernels remain unchanged, and retains the global ledger's original reservations. Only the two harness modules changed. Native fixture attempts were explicitly amended to four total; generation stayed capped at two and corpus retrieval at 24. One continuation is allowed; a new output/plan cannot reset the budget. See [the bounded plan and amendment](M5_5_4_PLAN.md).

Neo4j emitted existing `indexProvider` deprecation notifications while recreating the exact saved indexes; five upstream SWIG deprecation warnings remain. No index policy or dependency version was changed to suppress them. Locked checks still resolve 95 packages and verify 79 compatible installed packages.

## Current artifacts and handoff

All following paths are in the implementation checkout under `runs/retrieval-v2/m5-5/`:

- `m5-5-4-plan-v3.json`, SHA-256 `1df22fffb7bd1257ac65e56b92580b965f1e79561cb4eb1a7ea56dbd766ee640`: current exact readiness plan; V1/V2 remain historical.
- `m5-5-4-corrected-cf4d3a031091/report.json`, SHA-256 `3ef2a4e9b99186daeb11bac367526e2032b9e17ffc6ebefb19c8c941149585a1`: complete capacity/recovery report. The separate `physical-recovery.json` is insufficient for final freeze readiness.
- Same directory: `scope.json`, SHA-256 `8bce666642a7d4459b7c35dcb43f17fdd48a1e60ddad92dd5481f02a4ff5bf6f`; `snapshot/manifest.json`, SHA-256 `ae8f853cd2418b05cd194a548a082127a6e82dd7ddf0d9b1ca1a613c18d9a4f4`.
- `m5-5-4-offline-corrected.xml`, copied-context `native.xml`, retained working/restored artifacts, `m5-5-4-acceptance.json` and `m5-5-4-handoff.json`: actual checks and preservation metadata.

Accepted target: **`dbu-m4-recovery-m5eval-cf4d3a031091`**, loopback Bolt **60495**, HTTP **60496**, exact pinned image and two owned retained volumes. It is **stopped**. Failed first target `dbu-m4-recovery-m5eval-ffed5d75fa6d` is also stopped/retained. Working target `m5dev-2d43d2b9a2fa` and its declaration remain unchanged. Current executable source-tree SHA-256 is `c671340e9c49b1cc8bff224b7bb5427b6d79356ce1e80c176d60908f95f0c0c1`.

**Pending:** five other integration cases were not selected; no fresh final freeze or final-run authorization exists. Use these actual accepted inputs for M5.5.5; do not rerun consumed readiness probes, repoint the working scope, rebuild the retained indexes or use the old 96-run receipt. Prepare the complete reviewable freeze/limits, preserve the negative-gate and author-context disclosures, and obtain exact numerical human authorization before any private input consumption or final execution.
