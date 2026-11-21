# M8 plan for users to bring their own research papers

**Status: planned, 0% implemented.** The user requested this addition on 21 November 2026. This document and the synchronized specification define the next product milestone. Today's work adds planning and a class progress report only. It does not implement uploads, import documents, run models, approve claims or repeat either completed research study.

## User experience and first release

A user creates a named collection, uploads 1-10 text-based research PDFs or supplies supported links, watches processing status, and asks questions with exact source passages and page citations. Initial links support arXiv abstract/PDF URLs and direct public PDF URLs. Login-only pages, paywall access, unattended crawling, arbitrary HTML, scanned-document OCR and non-PDF formats remain outside the first release.

Vector and Hybrid become available after indexing. Hybrid + Approved Facts and Graph require that collection's own reviewed claims and current review projection. Extraction proposals are never automatically approved. A user can finish ordinary passage-based QA before deciding whether to review graph proposals. The existing pretrained local Qwen/embedding stack is reused without training; new-topic quality is not guaranteed.

## Boundaries and shared contracts

- Keep the two original curated collections as preserved examples; do not add user documents to their corpus IDs, source projections or review journals. Before writes, create an explicit isolated writable user-collection target/namespace and local storage/review root. Do not repoint any baseline, retained M5 or consumed evaluator scope. Resource preflight must account for existing services.
- Proposed `UserCollection` stores stable collection ID, name, immutable revision, document versions, corpus binding, review-directory binding and readiness by mode. Proposed `ImportJob` stores collection/revision, input identity, source/content hash, status, indexed coverage, duplicate/failure reason and output snapshot. Final typed fields and numeric limits are fixed in M8.1 before adapters/UI code.
- App services calculate source hashes and manifests from the inputs. Preserve URL or uploaded filename, PDF page coverage, source offsets and exact quotations. Unknown bibliographic metadata stays unknown; an unavailable OpenAlex match does not prevent passage-only QA. Repeated content is deduplicated within a collection, and later versions receive new immutable identities.
- `collections/` owns registry, jobs and collection/review bindings; `ingestion/` owns input resolution, PDF processing and indexing; `review/` owns proposal/decision eligibility. Existing retrieval/pipeline/generation/product/export services remain shared. CLI and Streamlit only call those services; no UI-owned Cypher, hidden cross-collection fallback or mode-specific validation copies.
- Reuse the six-unit/1,800-estimated-token evidence contract, source/citation checks, current-review-head guard, requested/effective mode and fallback visibility. Standard local generation retains 4096/512 bounds and explicit opt-in. New engineering probes require their own numerical scope/accounting before execution; used readiness/study allowances are not reused. No new paid allowance is granted by this plan.

## Verifiable task register

| Task | Planned work | Acceptance evidence | Implementation |
|---|---|---|---:|
| M8.1 | Finalize typed collection/job contracts, limits, isolated targets and persistent registry; retain existing preset bindings. | Registry survives restart; ownership/readiness checks reject mismatched targets/reviews and frozen writes; resource/URL/file/page limits recorded before adapters. | 0% |
| M8.2 | Add PDF uploads and supported link resolution with processing/duplicate/failure status. | A valid PDF and supported link create source-bound snapshots; duplicate, unreadable, oversized and unsupported inputs produce clear results without overwriting existing assets. URL requests/redirects stay within the fixed public-input policy. | 0% |
| M8.3 | Enable passage-based Vector/Hybrid QA, collection selection, citations and exports through existing services. | Questions retrieve only the selected collection/revision; changing selection clears stale results; citations replay to exact pages/excerpts and downloads do not regenerate. CLI/UI results share the contract. | 0% |
| M8.4 | Add optional in-app review of proposed claims/entities/relationships, then enable fact/Graph modes when eligible. | Recorded real human decisions bind exact revisions/sources/mappings; unknown conditions and unapproved proposals remain distinguishable; revocation/staleness blocks reads. Positive graph capability is tested with UUID-owned synthetic fixtures, not fabricated real approvals. | 0% |
| M8.5 | Verify and document the user workflow across at least two public research topics. | Relevant offline/new isolated integration tests; bounded public engineering import/QA checks; actual UI upload/link/question/citation/export demonstrations; documented failures, coverage and resource observations. No private test questions, new final study or superiority claim. | 0% |

M8 is complete only after these product gates pass. Planning alone does not complete an implementation task. No M8 dates, effort weights or quality gains are claimed. Corpus/topic changes apply to new user collections, not to the already reported frozen experiments. A future comparative research study would need a separate prospective protocol, fresh source validation/freeze and explicit numerical execution authorization.

## Scope differences from the finished class project

The completed M0-M7 project answers over manually prepared five- and twenty-paper collections. M8 adds self-service inputs and dynamic collections. It does not replace the original results, remove human-review rules, enable unattended approval or add cloud accounts/authentication. Graph schema/prompt changes for a new subject require explicit versioning rather than silently reinterpreting older reviewed entities.

The class progress report counts completed M0-M7 as eight accepted milestones and M8 as a ninth planned milestone. Its approximately 89% figure is an equal-milestone count, not effort-weighted completion, answer accuracy or M8 implementation progress. The original agreed project scope is complete; M8 is a future extension.
