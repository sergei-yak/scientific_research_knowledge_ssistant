# M2.2 — Human review and approved-fact publication

**Status: complete for the bounded initial review pass.** All five papers have approved evidence:
**23 current human-approved claims**, **two deferred `needs_review` drafts**, zero rejected.
M2.3 and the full five-paper product acceptance gate remain unfinished; corpus expansion is closed.
This report supersedes intermediate review counts without replacing their immutable artifacts.

## Task outcomes

| Task | Result |
|---|---|
| M2.2 — Human checkpoint | Nine small batches reviewed in chat; explicit decisions imported against the exact displayed revision/source/entity hashes. Only these decisions grant approval. |
| M2.2 — Corrections and mappings | Eight of M2.1's ten flagged drafts corrected as new source-backed proposals, then explicitly reviewed. Additional support expansions and method identities also received fresh review. Two GraphRAG drafts retain unresolved mappings and no decision. |
| M2.2 — Approved facts | 16 qualitative Findings and seven paper-owned Evaluations published as 23 searchable FactText records using the frozen CPU MiniLM encoder. Vector and full-text indexes are `ONLINE`. |
| M2.2 — Integrity | Offline import/revision/invalidation checks and a separate live synthetic fixture passed. Real readback verifies attribution, shared benchmark identity and source preservation. |

Combined corpus: `74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329`.
Final review head: `0108e74ee7e9a4126145e8b2d16d8f0976d7c0bb344e5c7e581ea61168fe1203`.
Historical M2.1 packets remain unchanged. Eligibility comes from the current journal and synchronized
projection, not the pending labels in an older packet.

## Human decisions and preparation limits

| Paper / pinned revision | Approved | Deferred | Reported approximate review minutes |
|---|---:|---:|---:|
| GraphRAG survey, 2501.00309v2 | 3 | 0 | 15 |
| Edge et al. GraphRAG, 2404.16130v1 | 6 | 2 | 20 |
| Original HippoRAG, 2405.14831v1 | 5 | 0 | 20 |
| LightRAG, 2410.05779v1 | 5 | 0 | 10 |
| HippoRAG 2, 2502.14802v1 | 4 | 0 | 20 |
| **Total** | **23** | **2** | **85** |

Durations are user-reported batch observations, totaling approximately 5,100 seconds. Per-claim
review times remain unknown. Two late time reports are separate immutable observations; original
receipts are preserved. All reported paper totals remain within the initial 20-minute allowance.
The two GraphRAG drafts were deferred when that allowance was reached. No approval or rejection
was inferred from the time limit. Extending their review requires a recorded development decision.

Nine batches were shown. Folder `batch-08` contains prepared but unshown redundant GraphRAG drafts;
the final two HippoRAG 2 batches are in `batch-09` and `batch-10`. The reviewer approved Kx1 and
reported five minutes for the last batch. Verbatim responses and identity remain in ignored local
receipts, outside Git.

Corrections retained the reporting paper, exact normalized quotations and support offsets. An
initial GraphRAG protocol correction failed exact-quotation validation; its failed result remains
preserved, and a corrected proposal received human review. No extraction request was repeated.
The M2.1 count of 25 known candidates, 27 request reservations and the interrupted request's two
reserved possible candidates is unchanged. Preparation now includes human curation and the above
review effort, not merely automated extraction cost.

## Implemented boundaries and contracts

- Shared `ReviewDecision` and review contracts bind claim revision, full revision hash, PDF hash,
  entity definitions, reviewer, timezone-aware timestamp, reason and provenance. Blank CSV rows
  stay pending. Entire imports validate before one decision event is appended.
- `review/store.py` owns append-only hash-chained history, current state, CSV import/export and
  proposed revisions. Exact replay is idempotent; old approval replay cannot undo a later rejection.
  Source, support, assertion or alias changes invalidate eligibility and require fresh review.
- `review/batches.py` exports immutable small packets with quotations, mappings and source locations;
  it captures only supplied chat decisions and actual batch time. `review/revisions.py` constructs
  source-backed corrections without granting approval. Neither validation nor elapsed time approves.
- `review/facts.py` supplies one eligibility predicate and deterministic `fact-text-v1` content for
  future Hybrid + Facts and Graph consumers. Canonical method/dataset and unknown conditions are
  included in the shared evidence bundle. Embedding text follows the M1 recipe; oversized input
  fails rather than truncating conditions. Full quotations are attached separately.
- `graph/reviews.py` atomically publishes current claim status, facts and review head. Active-only,
  corpus-scoped indexes exclude revoked/inactive facts while preserving historical nodes. Reads
  require the current local head; an unsynchronized or rolled-back journal fails closed. Frozen
  corpora reject publication. Import and synchronization are separate recoverable operations.
- CLI commands: `review-prepare`, `review-import`, `review-revise`, `review-status`, `review-sync`.
  Executable arguments and isolated integration instructions are in README. No dependencies changed.

Human review explicitly distinguishes original HippoRAG from HippoRAG 2. Their approved MuSiQue
mappings share one **base benchmark identity**. Each Evaluation retains its own reporting paper,
subset/split/metric/protocol fields and unknown values; a shared benchmark name does not establish
comparable experiments. GraphRAG and LightRAG also retain separately reviewed method identities.
Unknown numerical outcomes remain unknown. Approved setup counts and qualitative author reports
are not independently established performance results.

CSV/chat provenance is a trusted input boundary, not cryptographic proof of reviewer identity.
Synthetic decisions are confined to temporary files and a UUID-owned fixture project. Production
approval receipts, source data, caches and journals are excluded from Git.

## Verification actually run

| Check | Actual outcome |
|---|---|
| `uv run --locked --offline pytest -m "not integration"` | **67 passed**, three integration cases deselected; 70 collected. |
| `RUN_REVIEW_SMOKE=1`, then `uv run --locked --offline pytest -m integration tests/integration/test_review_repository.py` | **One passed** against the local Neo4j service. |
| `uv lock --check --offline` | Passed; 95 resolved packages, lock unchanged. |
| `uv pip check` | Passed; 79 installed packages compatible. |
| CLI help / whitespace check | `python -m research_assistant --help` lists the five review commands; `git diff --check` passed. |
| Real journal/projection/readback | Exactly 23 eligible facts, matching active graph IDs; two pending IDs match the explicit deferral record. |
| Native fact indexes | Both `ONLINE`; lexical probe returned all 23; vector top-12 probe returned 12 active facts. These are readiness checks, not retrieval accuracy scores. |
| Shared MuSiQue attribution | Three approved evaluations across two reporting papers and two distinct methods link to one dataset node; zero wrong-paper owners. Unknown result values remain null. |
| Embedding/evidence bounds | Maximum fact embedding input 154 MiniLM tokens; all 23 facts fit individually. A deterministic six-unit sample covering five papers uses **988 estimated tokens**, including all displayed content. No generator call. |
| Source preservation | Original M1 corpus still 325 chunks; combined corpus 571; six OpenAlex work-level citation edges remain. No volume reset or production deletion. |

Offline coverage includes CSV round trips, stale and wrong source bindings, exact quotations,
source/support/assertion/alias invalidation, revocation, replay, conflicting paper-specific findings,
ambiguous normalized aliases, named-entity bindings, journal tampering, source-backed correction and
chat label/time handling. The live fixture uses two conflicting paper-owned evaluations and checks
method/dataset endpoints, conditions, unknown values, idempotent publication, active-only native
indexes, revocation, alias invalidation and stale-head/rollback/frozen guards. Cleanup removes only
that invocation's UUID-owned nodes/indexes; static schema constraints and production data remain.

Five upstream PyMuPDF SWIG deprecation warnings occurred. The real read-only query also reported
Neo4j's missing-property warning for `value`, because all current performance values are unknown
and Neo4j does not store null properties; readback correctly returned null. Neither was a failure.
The two M0 service pytest cases were not rerun. Ollama inference and OpenAI live calls were not
needed for this milestone. OpenAI integration remains pending credentials and an approved numerical
budget for M3.3. There were **zero new LLM calls and zero paid calls** in M2.2.
The final `review-sync` command took 8.46 seconds of observed wall time, including process startup,
cached encoder loading, embedding, publication and readback. Cumulative compute time across earlier
publications was not measured; do not present this final command as total preparation time.

These checks establish storage, eligibility and evidence-budget readiness. M3 graph traversal,
query plans, fallback, answer quality, UI/export and recovery are not claimed as passed.

## Local artifacts and next step

- Final machine-readable checks: `runs/m2/review-final-verification.json`.
- Final import/publication: `runs/m2/review-import-hipporag2-final.json`, `runs/m2/review-sync-final.json`.
- Current journal and immutable projections: `data/reviews/pilot/`.
- Current handoff index: `runs/m2/m2-2-session/FINAL_STATUS.md`.
- Deferred drafts: `data/reviews/pilot/review-limits/graphrag-initial-pass.json`.
- Earlier proposals, failed validation and intermediate imports/publications remain under `runs/m2/`;
  original M2.1 packets and per-PDF extraction journals are preserved.

There is no remaining blocker to M2.3's development-question work. Prepare eight development
questions, two per primary category, with graph-independent source-span gold annotations and human
validation, including qualitative limitations and multi-passage evidence. Do not claim a completed
numerical comparison dataset: current approvals mostly describe design, setup and qualitative
reports. Keep held-out inputs external and untouched. The two deferred drafts do not authorize more
review/extraction by themselves; revisit them only if the development evidence demonstrates a need.
