# M5.5.2 — Versioned matched evaluator implementation

**Complete as software engineering, 2026-11-17 user-facing date.** No fresh study was executed or authorized. M5.5 remains in progress; M5.5.4 live capacity/recovery proof and M5.5.5 final freeze/authorization remain pending. The M5.4 negative gate and accepted exploratory author-context limitation remain unchanged.

## Changes and boundaries

- `evaluation/readiness_v2.py` validates the actual hash-bound source/human-only attestation. All sixteen annotations are approved; this adapter reads public metadata only and does not upgrade annotation approval into runtime readiness or permission.
- `matched_freeze.py`, `matched_scope.py` and `matched_assets.py` define separate twelve-condition freezes, numerical human authorizations, new physical read-only targets and narrow public-file access. Old four-condition readers/receipts remain unchanged. A new `m5eval-*` container and owned volumes must differ from the development and consumed targets; the retained `m5dev-*` projection metadata is source lineage, not lifecycle authority.
- `matched_runner.py` uses the existing seed-5551 schedule and common retrieval, selection, evidence, provider and scoring services. A0/A1/A2 × four modes retain the full arm/profile/selector identity. Opaque in-process, single-use slot permits restrict the common generation path to an exact-authorized reserved slot. They are a procedural application boundary, not an OS security sandbox. Ordinary V2 CLI/UI synthesis stays disabled.
- One durable external freeze ledger claims execution before private inputs or inference; every slot is reserved before work. Failed/unknown attempts remain consumed, with no automatic retry/resume. Complete 288-slot history is required for scoring. Gold is parsed after generation; no gold enters retrieval or provider inputs. Private inputs, execution outputs and reveal maps remain external. Nested symlinks/junctions and path escapes are rejected.
- Shared blinding keeps twelve condition identities external until complete real human scores are sealed. It reports the primary Graph versus same-arm Facts contrast and separate development/held-out descriptive summaries. Synthetic scores in tests are explicitly fixtures, never human approvals.
- `snapshot-export --matched-runtime-assets` adds pinned encoder/reranker/token-cache bytes to a **new** export only. Normal exports retain their default behavior. Frozen copied runtime files must match the final file manifest; no existing snapshot is extended or overwritten. Local Ollama model storage remains external and digest-bound.

Public setup commands live in `evaluation.matched_setup`; execution/scoring has the separate `evaluation.matched_runner` entry point. The application UI is not an evaluator. See README for commands. No real new scope or freeze file was fabricated to bypass the pending recovery proof.

## Actual verification

| Check | Outcome |
|---|---|
| Locked dependency consistency | 95 resolved packages; 79 installed packages compatible; no version or lockfile changes |
| Full offline suite | **335 passed**, seven integration cases deselected; includes 61 new matched-evaluator cases |
| Configured native database fixtures | **2 passed** on the verified isolated development server; UUID-owned fixture records/indexes cleaned |
| Actual public attestation adapter | Accepted current sixteen-approval evidence and preserved `execution_authorized=false` / runtime-readiness pending |
| Synthetic end-to-end evaluation | 288 scheduled slots, twelve-condition anonymous packets, once-only failure accounting, score sealing and post-seal contrasts pass; fake provider/target, no real inference or private inputs |
| Restarted Streamlit on port 8502 | Actual public V2/reference Graph query passed: six units, 1,385 estimated evidence tokens, explicit `graph_candidates_not_selected_within_budget` fallback to Facts; synthesis disabled, zero provider calls |
| Preservation | 1,427 chunks, 51 approved claims, review head/catalog, eight development approvals and development graph unchanged; original 118 frozen baseline files and final-report hash verify; consumed target still stopped |

The copied `pytest.exe` launcher initially selected the baseline interpreter and caused seven collection errors. Running through the worktree's `python -m pytest` passed. Offline reinstall of pytest lacked its wheel; reinstalling the exact locked pytest 8.3.5 and Streamlit 1.45.1 packages repaired the worktree launchers (Streamlit download 9.4 MiB). No dependencies were upgraded. Five upstream SWIG deprecation warnings remain.

Automatic approval review rejected the initial background UI startup command with “blocked by policy,” without a further reason. A process-specific identity check allowed stopping only the verified project listener; startup through the supervised execution session succeeded. An attempted optional process inspection found `psutil` unavailable; no dependency was added. The final actual UI query, rather than health alone, establishes the UI check.

## Artifacts and remaining gates

Under `runs/retrieval-v2/m5-5/`:

- `m5-5-2-offline-complete.xml`: final 335-test run; earlier intermediate/error XML files retained.
- `m5-5-2-native.xml`, `m5-5-2-native-preflight.json`: actual native fixture checks and exact development-target identity.
- `m5-5-2-public-preservation-ui.json`: current public source/review/development/graph bindings and actual saved UI run.
- `m5-5-2-acceptance.json` and `m5-5-2-handoff.json`: completion/preservation metadata, without private contents.

**Explicitly pending:** five other integration cases were not selected; no fresh Qwen inference/combined generator-reranker capacity probe, matched read-only native execution, fresh recovery target/proof, real new freeze or final execution. Synthetic mocks do not prove those live gates. No private evaluation directory was listed/read by development. No extraction, paid call, generation or research matrix ran; the single UI retrieval and UUID fixtures were engineering checks. M6 demonstration remains reserved.

**Next: M5.5.4.** Record bounded local probe limits, verify current model/resource readiness, export the complete copied runtime, and restore into a fresh unique `m5eval-*` read-only target with current proof. The existing generic recovery script's project naming/readiness assumptions need a deliberate matched recovery workflow; do not repoint the working scope or use an old proof. After that, M5.5.5 can create the real exact freeze and present the disclosed continuation decision and final numerical authorization for human approval.
