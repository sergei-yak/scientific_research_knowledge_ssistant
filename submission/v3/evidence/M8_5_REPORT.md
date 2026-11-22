# M8.5 — Cross-topic product verification

**Status: complete, 2026-11-21.** M8.1–M8.5 meet the bounded local first-release gates. Use [the user guide](M8_USER_GUIDE.md), `START_M8.ps1` and port **8504** in `C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections`, branch `codex/m8-user-collections`. This verifies operation on different topics; it is not another research experiment, a Graph quality gain or a general reliability claim.

## M8.5 scope and existing human decisions

The user approved two Attention-paper claims in the actual UI and explicitly updated the reviewed index before this increment. Live readiness verifies **two current approvals**, not agent-authored decisions. Collection `uc-d1feda43d1b1404b9ff2899fd2bba4ae`, revision 2, retains two PDFs/632 chunks, head `8098df21bd0e3022b98a85995536c2958db0df2ea1aeb32f8e67c1f5a554426c` and review head `a9186baf29125d7158d9a077154066e792689a731569ebc458add131eaab53d6`. No decision, mapping, source or projection was changed by M8.5. M8.4's earlier zero-approval state remains historical.

A prospective local plan fixed a second topic, four questions and numerical bounds before execution. The new physics collection imports **[Observation of Gravitational Waves from a Binary Black Hole Merger, arXiv:1602.03837v1](https://arxiv.org/abs/1602.03837v1)** through its versioned PDF URL. Collection `uc-9cb2f792abda4bd587c99f945db0ef4c`, revision 2, has **16 indexed/readable pages and 148 chunks**, head `fa72b4d3f231b413c7ec9239ab1491aad41400ac89b99336a30351759b745f01`. PDF SHA-256 is `e5e864c23d015b69be17e5b5d51b5b462d2829353a867513414b6728f54589c4`. Its bytes/chunk cache were absent at preflight: this is a cold **document-cache** import, not a controlled cold OS/model-cache experiment. No physics claim was proposed or approved.

## Actual workflow outcomes

| Check | Observed result |
|---|---|
| Link import, then upload | One public download created the physics snapshot. Uploading those exact bytes reported a duplicate, preserving the collection head, documents and index without another document-embedding call. |
| Invalid input | A deliberately corrupt PDF failed as `pdf_parse_failed`. Its failed job remains recorded; the valid physics collection/head/source/index stayed ready and unchanged. |
| Reviewed AI collection | Vector evidence search, Hybrid generation, approved-fact evidence search and Graph generation all completed. Four requested modes used the same shared service contracts. |
| Real Graph behavior | Graph returned effective `hybrid_facts`, reason `no_new_eligible_graph_candidates`. Its entire evidence context exactly matches the fact-mode context. The two reviewed design claims have no entity mappings/cross-paper connections; no positive traversal result is claimed. M8.4's separately labeled synthetic native traversal/revocation proof remains the capability check. |
| New topic | Physics Vector and Hybrid produced cited answers identifying the paper's event/observatory from the selected paper. Each returned six source-bound units within the shared 1,800-estimated-token limit. |
| Topic isolation | Asking the physics collection about Transformer positional encodings, and the AI collection about GW150914, both returned `insufficient_evidence=true` with empty citations. These are two observed abstentions, not a guarantee. Cross-collection output validation also refused a mismatched collection. |
| Human-review gates | Physics fact and Graph requests were explicitly refused before encoding: no approved claims in that collection. AI approvals were not inherited. |
| CLI, sources and downloads | Physics CLI/Hybrid context exactly matches the browser context. All 148 new chunks replay to normalized PDF offsets. Actual browser CSV/JSON exports for physics and AI Graph match their saved runs; the downloaded physics PDF matches the source SHA. Sixty exported excerpt rows were checked, retaining source attribution and review eligibility. |
| Final UI | A fresh ordinary server and evidence-only approved-fact question verify the final code. Paper labels are readable in the claim table. A Streamlit AppTest replays the actual failed-import outcome to verify an actionable PDF error while preserving its original diagnostic record. |

Nine saved successful runs cover the main matrix, plus two expected gate refusals. A final restarted-server evidence query adds a tenth saved successful run. This is twelve logical submissions, including the two refusals; no automatic retries or changed questions were used to obtain favorable answers.

Two small display fixes resulted from real testing: parser failures now show a useful instruction rather than an internal path in the main banner, and the approved-claim table uses existing readable paper labels. Detailed import history, source IDs, exports, algorithms, shared contracts and approval rules remain intact. No dependency, model, schema or prompt changed.

## Verification, accounting and preservation

- Locked environment: `uv lock --check --offline` and `uv pip check` pass; no package/model download or upgrade.
- Final offline suite: **495 passed, 11 integration cases deselected**, with five existing PyMuPDF/SWIG warnings. Earlier offline verification also passed 495 cases before the final label polish.
- New opt-in actual-artifact/native verification: **1 passed** in 5.64 seconds. It reads the live owned indexes and saved public operations, checks sources/exports/current reviews/parity/gates, and forbids encoder/provider calls. Ten other integrations were not rerun; historical consumed engineering fixtures/studies were not replayed.
- Preserved: **118 baseline + 208 retained M5 frozen files**, both original canonical graph hashes, 26 local model files, `uv.lock`, and retained M6/M5/publication heads. M6 source, both consumed studies, private evaluation areas, class progress PDF and M7 packages are unchanged. Documentation alone is mirrored to the original checkout; M8 source remains on its feature branch.

| Engineering operation | Prospective maximum | Actual including final handoff |
|---|---:|---:|
| Imports | 3 | 3: ready / duplicate / expected failure |
| Download chains / external HTTP attempts | 1 / 4 | 1 / 1 |
| Logical query submissions / question embeddings | 14 / 14 | 12 / 10 |
| Document embedding calls / texts | 1 / 600 | 1 / 148 |
| Local answer-generation attempts | 6 | 6 successful |
| Extraction / new human decisions / paid spend | 0 / 0 / $0 | 0 / 0 / $0 |

Generation used pinned local Qwen digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`, context/output 4096/512, concurrency one and zero automatic retries. The UI timeout was 300 seconds; CLI inherited 180 seconds, within the 300-second plan maximum. Existing PDF-wide extraction reservations were not reset. The M8.5 engineering scope closes at handoff, including unused capacity; ordinary explicit local product operations remain available. No paid/private/final-study authority follows.

Generation alone ranged **22.99–54.15 seconds** across the six calls (49–113 output tokens). A cold-process AI Vector CLI operation took **38.36 seconds** including startup/source/model readiness; the later approved-fact operation took **10.60 seconds**. Those whole-operation observations differ from inner `retrieval_ms`. Model loading/keep-alive and caches varied; no controlled latency or endurance benchmark is claimed. Initial free RAM was approximately 14.4 GiB; GPU usage was about 2.2/12.0 GiB before model loading. These observations do not establish peak resource requirements or concurrent-user capacity.

## Limitations, skips and blockers

There is **no M8 implementation blocker**. Clean-machine provisioning, independent human usability testing and broader topic/format/security/endurance testing remain unperformed. This local single-user procedural scope is not an adversarial sandbox or production deployment. Limits intentionally exclude OCR, arbitrary websites, paywalls, cloud accounts and non-PDF inputs.

Source replay verifies exact passages and attribution, not independent scientific truth, table/equation accuracy or complete answer support. The generated physics example includes approximate mass values from prose; numerical tables/uncertainties were not independently certified. Actual answers remain local for source inspection. Broader accuracy, better graph coverage and comparative research quality are not demonstrated. Existing negative Graph findings and the accepted research author-context limitation are unchanged. Do not select favorable papers/questions or reopen a consumed freeze to turn this product pass into a research improvement claim.

## Local evidence

`runs/m8/m8-5/` retains the prospective plan and hash-chained reservations, preflight/import/source proof, nine-case manifest, query outcomes, actual downloaded CSV/JSON/PDF copies, original invalid-input outcome, screenshots, final offline/native JUnit/proof, preservation and handoff/acceptance receipts. Individual immutable runs live under `runs/user-collections/queries/<run_id>/run.json`. These raw sources/outputs, reviewer inputs, caches and database data stay ignored/local; public source/tests, this report and the user guide are version-controlled.
