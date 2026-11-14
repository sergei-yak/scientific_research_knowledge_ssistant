# M4.2 — Freeze preparation

**Status: in progress; final execution is unauthorized.** M4.1's 8/16 public commitments remain unchanged. No private evaluation content has entered the development context. Work is performed against the locked environment and existing data.

| Task | Actual result |
|---|---|
| M4.2.1 encoder condition | MPNet revision `e8c3b32edf5434bc2275fc9bab85f82640a19130`, CPU/768-D/normalized, explicitly indexed on the unchanged 1,427 chunks. MiniLM remains revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, CPU/384-D. Shared ANN/cosine/tie/threshold/packing rules are unchanged. All old node properties/labels/relationships/schema survive; only MPNet fields/index/cache were added. Forty development retrievals passed source/context contracts and were scored from actual rendered excerpts, with no generation. |
| M4.2.2 runner | Authorization precedes private-path access. A durable external marker/reservation ledger prevents output/receipt changes from resetting execution. The provider receives stripped questions/context only; gold is parsed after generation. Shared blinding/scoring retains the development-only public API guards. Full synthetic workflow exercises 96 answer runs + 48 separate vector reads, incomplete-form/reveal rejection, once-only execution and no private console error text. Synthetic scores are not research results. |
| M4.2.3 recovery | Fresh expanded export/restore and server-enforced read-only verification pending. Export freezes only the target copy's corpus flag. Working data/volumes are never reset. |
| M4.2.4 freeze | Concrete manifest, run plan and final authorization pending recovery/remaining checks. |

Environment: uv 0.10.10 / Python 3.11.13, healthy Neo4j 5.26.32 Community; 95 locked / 79 installed packages compatible. Selected generator remains local `qwen3.8:latest`, digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`, Q4_K_M. No dependency/model downloads or upgrades.

Checks recorded so far: `runs/m4-2/offline-before-recovery.xml`: **186 passed / 5 deselected**, five existing PyMuPDF/SWIG warnings. Earlier targeted run: 26 passed; native UUID-owned encoder fixture: one passed. `development-encoders/summary.json` contains 40 actual development reads and preservation checks. The isolated evaluator separately confirmed all 16 private questions match their byte commitment and fit both tokenizers (maximum 61 tokens including specials; 297 characters). Only aggregate counts/revisions returned here; no private retrieval/generation was performed.

Planned final bounds: four MiniLM conditions on all 24 questions (at most 96 local generation requests), then 48 vector-only retrievals alternating encoder order. Context 4,096/output 512, concurrency one, zero retries, $0 paid budget. Requested/effective modes and fallback remain saved; condition results stay private until complete blind human scores are sealed. Report development and held-out partitions separately. Latency includes source/index guards; query encoding/fetch timings and order/cache limitations are recorded. No implicit reruns after a started failure; preserve the original and use a disclosed amendment.

The [Neo4j configuration reference](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/#config_server.databases.default_to_read_only) documents server read-only configuration; its actual behavior on the pinned 5.26.32 Community target must pass the transactional write-refusal probe. No source database downtime/offline dump is planned; only the new disposable target is restarted/stopped, with its volumes retained.

AI-authored purposive gold and single-human-review limitations remain. Public attestations do not independently verify private content. A freeze proposal is not final-run authorization; M3.3's paid allowance is exhausted.
