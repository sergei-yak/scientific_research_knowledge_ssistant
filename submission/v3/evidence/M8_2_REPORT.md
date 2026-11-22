# M8.2 - PDF uploads and supported links

**Status: complete, 21 November 2026.** M8.2 supplies the actual foreground import worker and CLI. The collection upload/QA interface is M8.3 and is not available yet. Existing M6 source and both completed research studies remain unchanged. No Qwen generation, scientific claim extraction/approval, paid call or private evaluation access occurred.

## Implemented behavior

- Upload one or several binary PDF streams, provide supported public HTTPS/arXiv links, or combine both in one batch. Names and declared MIME/size are not trusted as file validation. The importer checks actual streamed bytes, PDF signature, encryption, page count, readable text, unique membership and total collection limits.
- Resolve DNS in a bounded child process, reject every non-public/mixed/transitional address answer, connect directly to a checked numeric IP, and verify TLS against the original hostname. Proxies, credential URLs and automatic retries are not used. Every redirect is revalidated; each attempted request is durably reserved before DNS/network work. At most three redirects/four requests per input, with one 30-second overall download deadline covering TCP/TLS/headers/body. A watchdog stops continuously dribbling responses; timeout-induced EOF cannot become a successful download.
- Inspect each PDF in a child process with a 60-second deadline; reject encrypted, corrupt, non-PDF and wholly unreadable/scanned files. No OCR. Bound extracted text to 100,000 characters/page and 2,000,000/PDF before tokenization. Explicitly retain omitted blank/image-only page numbers and selected readable coverage. Figures, tables, equations and section labels are not certified by text parsing.
- Deduplicate by actual PDF SHA-256, within the batch and the selected collection, before counting new members. Duplicate-only imports leave an indexed collection revision unchanged, including when it already contains ten documents. Same-named files with different bytes remain distinct document versions.
- Use shared parsing/chunking/embedding/index services, with actual total chunks checked before embedding/index writes. `pipeline.index_prepared_paper` was extracted from the existing ingestion entry point without changing its historical identity/default behavior. Parser/chunker additions are explicit keyword limits; old calls keep their defaults.
- Keep one durable foreground job/worker reservation. Record resolving/parsing/indexing and terminal ready/duplicate/failed/interrupted outcomes. Preserve earlier revisions, partial files, failed attempts and caches; do not auto-resume, clear locks or retry. New collection/index publication requires an exact final commit receipt. Partial multi-file/index failure cannot grant product readiness; later investigation must preserve its history.

Raw PDFs and per-paper caches remain under owned `data/user-collections/`. Derived aggregate snapshots use this M8 checkout's shared `data/processed/<corpus-id>/` location. Corpus IDs bind scope, collection, revision and source membership; model/source hashes are retained. No new framework or dependency was added.

Original URL/upload name lives in `DocumentVersion.source` and the import outcome. Source chunks use `userpdf://<SHA-256>` as a **content identifier**, not a public web URL. This avoids conflicting chunk metadata if identical bytes arrive under different filenames/URLs or collections. M8.3 must show the original reference and an owned PDF download alongside exact page citations. No OpenAlex match is required or requested here; citation metadata and redistribution rights remain unverified/unknown rather than invented.

## Actual verification

| Check | Actual outcome |
|---|---|
| Locked environment | `uv sync --locked --offline`, `uv lock --check --offline`, and dependency compatibility passed; lock/dependency files unchanged. |
| Final offline suite | **457 passed, 9 integration cases deselected**, 5 existing PyMuPDF/SWIG deprecation warnings. Includes 43 new M8.2 offline checks. |
| Separate bounded native import/index check | **1 passed** in 133.35 seconds. One mixed batch imported the existing survey upload and one pinned arXiv PDF. A second job re-uploaded duplicate bytes with a new filename and changed no collection revision. |
| Actual source coverage | Survey `2501.00309v2`: all 88 readable PDF pages, 569 chunks. Attention paper `1706.03762v7`: 15 readable pages, 63 chunks. **2 documents / 632 chunks**, no omitted pages in these two inputs. This is a new user collection; the old research corpus's selected-page coverage was not changed. |
| Actual network/models | Initial proof: **1 HTTP request**, 2 local MiniLM embedding calls / 632 texts, 3 logical index checks; concurrency 1, retries 0, Qwen generation 0, paid $0. Existing pinned MiniLM/MPNet assets were locally provisioned and checked; no model download/training/fine-tuning. Only MiniLM embeddings and the existing MPNet tokenizer were exercised. |
| Index/source proof | Shared aggregate snapshot replay, ONLINE vector/full-text/alias indexes and a native vector lookup using an already-indexed vector passed. All returned chunks belonged to the selected corpus. This establishes index functionality, not answer quality or a Graph improvement. |
| Final transport regression | After timeout/TLS hardening, a separate prospective transport-only scope downloaded the same pinned PDF once with no index/model operations. Exact SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`, 2,215,244 bytes, matched the initial import. Offline real-socket tests cover dribbling headers, detached HTTP sockets and timeout-induced EOF rejection. |
| Cached-source replay | Every one of the **632 chunks** equals its normalized source-page substring at its recorded offsets; source PDF hashes, canonical content URIs and the collection binding replay exactly. |
| Preservation | Both old canonical graph captures match before/after. All **118 baseline + 208 retained M5 frozen files** and 26 provisioned model/cache asset hashes are unchanged. Existing M6 source, class progress PDF, M7 artifacts and dependency lock are preserved. |

The initial engineering plan was recorded before execution: maximum 3 jobs, 1 download chain/4 HTTP attempts, 2 embedding calls/1,000 texts, 4 index checks, concurrency 1/retries 0/$0. Actual use is 2 jobs/1 request/2 embedding calls/632 texts/3 reads. It is now closed; unused capacity is not permission to restart its once-only runner. The post-hardening transport check had a separate explicit scope of 1 chain/4 requests and zero model/index operations; actual use was 1 request. Across both checks: **2 HTTP requests**, 2 embedding calls and zero generation/paid/private calls. All old/new receipts and reservations are retained.

The first local-source preflight found that the M6 demo did not provision `data/raw/`; it was corrected to the exact known original public PDF path and expected hash before any request/encoding. No HTTP request or model attempt was consumed by that failed path check. Focused/full offline runs passed throughout implementation. Review identified an absolute-timeout gap, which was corrected and tested rather than counted as an unavailable live service.

The M8 container `dbu-m8-user-c09ff451237f` / Bolt 65488 is **stopped and retained**, with its two-paper collection `uc-293c4fdafbd145eab4890b85558e177c`, corpus `9689bf313c9c9e760fec687ac436cbd05109e05c1d5bf9ea9302527a68913970`, sources/indexes and import history intact. No volume/data reset occurred. Metadata descriptions still expose no product modes until M8.3 supplies actual product readiness/selection checks.

## Commands

Run in `C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections`:

```powershell
docker compose up -d --pull never neo4j
& .venv/Scripts/python.exe -m research_assistant.collections scope-check
& .venv/Scripts/python.exe -m research_assistant.collections create --name 'My papers'
# Use the collection_id and sha256 returned by create/list:
& .venv/Scripts/python.exe -m research_assistant.collections import --collection <collection_id> --expected-head <sha256> --pdf 'C:/path/to/paper.pdf'
& .venv/Scripts/python.exe -m research_assistant.collections import --collection <collection_id> --expected-head <current_sha256> --url 'https://arxiv.org/abs/1706.03762v7'
& .venv/Scripts/python.exe -m research_assistant.collections jobs
& .venv/Scripts/python.exe -m research_assistant.collections job --job <job_id>
docker compose stop neo4j
```

Wait for database readiness before `scope-check`. Every explicit import creates a new job; do not rerun the consumed engineering test. URL syntax validation happens before fetch; runtime failures return stable outcomes and retained diagnostics. Fully scanned or encrypted PDFs need a different source, not hidden OCR or password handling. Stale worker locks, unknown interrupted work and incomplete publication require investigation; they are never removed to bypass history/caps.

## Scope and handoff

Eight other integration cases were not rerun. New UI, generated answers, human graph review and cross-topic product demonstrations remain M8.3-M8.5; they are not claimed as M8.2 passes. No Streamlit server loads M8 code, so no changed M8 UI was handed off or restarted; retained M6 runtime source is unchanged. The earlier class progress document remains a preimplementation snapshot.

Evidence: ignored `runs/m8/m8-2/engineering-plan-v1.json`, durable engineering/import reservations, native proof/job outcomes, final offline/native JUnit, transport plan/outcome, protected graph captures and `artifact-preservation-proof.json`. No keys, source PDFs, model weights, database volumes or private evaluation material enters Git.

No M8.2 blocker remains. **Next: M8.3**, selected-collection Vector/Hybrid QA, upload/link controls, checked source cards/PDF access and exports using the existing shared services. Keep fact/Graph modes disabled until that collection has its own actual source-bound human review.
