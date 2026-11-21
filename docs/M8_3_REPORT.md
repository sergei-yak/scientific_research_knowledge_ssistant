# M8.3 - User collection questions, sources and exports

**Complete, 21 November 2026.** The separate M8 product now lets a user create/select a collection, upload PDFs or supply public PDF/arXiv links, import them, and ask Vector/Hybrid questions with optional local Qwen answers. Open **http://127.0.0.1:8504/**. M8.4 human graph review and M8.5 broader product verification remain pending; neither is implied by this completion.

## Use the workspace

Run `START_M8.ps1` from `C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections`. It uses the locked offline environment, attests and starts only the exact retained M8 container, then starts the new Streamlit application on loopback port 8504. It never recreates a target or resets data. The local scope, model/tokenizer caches and credentials must already be provisioned; Git alone does not include them. The retained M6 demonstration remains separate on port 8503.

1. Create a collection, or select **Research papers demo** (two papers / 632 passages) or **Paper workspace demo** (survey only / 569 passages).
2. Open **Add papers**. Select text-based PDFs and/or enter supported links, then click **Import documents**. Observe success, duplicate or failure status; **Papers and indexed coverage** shows actual page coverage. Existing first-release size/page/text/chunk limits still apply.
3. Enter a question. **Vector** finds semantically related passages; **Hybrid** combines semantic and keyword search. Select **Generate an answer** to request local Qwen synthesis; otherwise only evidence is retrieved. Click **Ask question**. Local answers took approximately 46-49 seconds in these two checks, including model loading where applicable; this is not a general latency guarantee.
4. Check the cited source card, original reference, PDF page and exact excerpt. Linked inputs offer the original web link; both uploads and links offer a hash-checked local PDF download. Download evidence CSV or run JSON without another retrieval/model request.

For the two-paper example, try: `What are positional encodings used for in the Transformer?` Hybrid with answer generation produced a supported explanation citing the Attention paper's PDF page 6. New questions/topics can still miss useful passages or produce an abstention; inspect the excerpts.

## Module and state boundaries

- `collections.workspace` is the common QA/import/export boundary for CLI and UI. Before questions and every saved-result display/export it verifies the exact current collection/revision, final import commit, physical scope owner, snapshot, source PDF bytes, confined member-cache paths, source chunks and actual ONLINE indexes. Saved runs must match that binding and contain only passage evidence. Metadata-only `list/show` deliberately does not advertise verified modes; the QA service checks readiness live.
- `ui.collections_app` owns forms, selection, progress and result state only. It calls the shared import, retrieval, generation and checked product/export services. The existing renderer accepts source-label/PDF adapters without changing legacy defaults. Collection/revision changes, imports and failures clear old answers/downloads. Page reruns/downloads only revalidate saved output.
- `CollectionRegistry.query_lock` serializes questions with imports and revision edits across local sessions. Active/reserved jobs block queries; stale locks remain explicit errors. This is a local single-user application, not a multi-tenant security boundary. Processing callbacks cannot turn a display failure into a failed durable import.
- `collections query` and `export` use the same services; output paths must be new. Completed and generation-failure run artifacts are retained under `runs/user-collections/queries/`. Source chunks retain their canonical `userpdf://<sha>` content identity; the UI and CSV expose the original URL/filename separately, without inventing bibliographic metadata.
- Fact/Graph modes are absent from this UI and rejected at the collection query boundary. No import extracts/approves claims. M8.4 must add actual collection-specific human review before those modes can be offered. Standard baseline/reference evidence budgets and provider controls remain unchanged; no cross-encoder or hidden collection/provider fallback was added.

## Actual verification

| Check | Actual result |
|---|---|
| Final offline suite | **476 passed, 9 integration cases deselected**, five existing PyMuPDF/SWIG deprecation warnings. **19 new offline checks** cover source/index/binding corruption, path escapes, unsupported modes, mutual exclusion, failure artifacts, shared CLI/export behavior and Streamlit state/import/generation/download behavior. |
| Locked environment | `uv lock --check --offline` and `uv pip check` passed. Existing dependency/lock/model bytes unchanged; no packages/models downloaded or upgraded. One existing tokenizer asset was copied locally from M6 before live checks. |
| Actual browser imports | Mixed survey upload + pinned Attention arXiv link succeeded: two documents / 632 passages. A second upload-only collection succeeded: one document / 569 passages and stayed selected after indexing. Existing source/vector caches were reused; no document embedding inference occurred. All earlier collections/jobs remain intact. |
| Actual browser questions | Hybrid + Qwen on each new collection, and Vector evidence-only on the two-paper collection succeeded. Every returned passage belongs to its selected collection/revision. Changing collection cleared the previous answer and exports. The restarted server completed actual queries, not just an HTTP health check. |
| CLI parity | An additional Hybrid evidence-only CLI query returned the **exact context bytes/hash** of the first browser Hybrid query. CLI CSV export matches the browser download bytes. |
| Local generation | Two attempts, both completed with the pinned Qwen digest and 4096 context / 512 output cap, concurrency one, zero retries. Positional-encoding answer: 76 output tokens, 48,692 ms, source citation E1/PDF p.6. Survey question: 110 output tokens, 46,263 ms, insufficient evidence. No provider substitution or paid call. |
| Source/export checks | Actual downloaded CSV has six exact excerpt rows with original source references; JSON matches the saved run; downloaded PDF matches SHA-256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`. Uploaded-source cards offer the owned PDF; linked cards offer the original URL with the authoritative page fragment. Downloads/reruns created no extra query or generation artifact. |
| Preservation | Both prior canonical working graph hashes still match M8.2. All **118 baseline + 208 retained M5 frozen files**, 26 provisioned model files, dependency lock and retained M6/M5/publication heads are unchanged. No private evaluation directory was accessed. Class progress PDF and M7 packages remain unchanged. |

The prospective public engineering scope allowed at most three imports, one download chain/four HTTP attempts, six logical queries, two Qwen attempts, eight encoder calls/1,100 texts, concurrency one, zero retries and $0 paid. **Actual: two imports, one HTTP request, four queries, four question-embedding calls/four texts, two generation attempts, $0 paid.** The two imports reused document vectors. The initial harness reserved operations automatically; after a source-change restart the remaining explicit actions were reserved prospectively in the same append-only hash-chained ledger. No cap/history was reset. This engineering scope is closed; unused capacity does not authorize restarting its once-only harness or either completed study. Ordinary user-triggered local product use remains available.

## Findings, corrections and limits

The first browser import exposed a Streamlit restriction against nesting a status expander inside another expander. It failed before the worker/network/model started; plain progress messages now work inside the import form. A second issue caused collection options to reorder after an empty collection became ready. Selection now uses a separate persistent collection ID and a stable widget key for each membership list. A subsequent offline regression caught a switch-back reset in the intermediate fix; the final 476-test run and actual browser selection/query pass. The failed test result and initial logs remain retained rather than counted as passes. Local verification-script CSV/digest field mistakes were corrected without rerunning inference.

The survey question is a **retrieval miss**, not proof the survey lacks scalability content: its selected excerpts did not include the relevant discussion. Qwen returned insufficient evidence instead of supplying a supported cited answer. Vector's top excerpt for the positional question was broader attention background; Hybrid selected the directly relevant page-6 passage. These checks establish product operation, not a quality benchmark, universal abstention reliability or a Graph improvement. No tuning, new research evaluation or favorable question replacement followed the miss. Parsed section labels, numerical tables/figures, new-topic quality and bibliographic metadata remain unverified.

The launcher disables Streamlit file watching to avoid the existing PyTorch watcher incompatibility; restart after source/interface edits. It supplies a process-only 300-second request timeout when unset, without editing credentials or changing 4096/512 model bounds. Low memory, unavailable services, corrupt sources/indexes and stale jobs/locks fail explicitly. No automatic retry/recovery or swallowed readiness failure is permitted.

Nine configured integration tests were not rerun; their prior results are historical. This increment used the bounded actual browser/CLI/database/model checks above. Broad cross-topic coverage, cold-cache endurance, adversarial input/security review, OCR, arbitrary HTML, cloud accounts and graphical claim approval are not claimed. **No M8.3 blocker remains. Next: M8.4 optional in-app proposal review and eligible fact/Graph modes.**

## CLI examples

Run from the M8 checkout; substitute the current collection ID/head and a new output path:

```powershell
& .venv/Scripts/python.exe -m research_assistant.collections list
& .venv/Scripts/python.exe -m research_assistant.collections query --collection <id> --expected-head <sha256> --mode hybrid --question 'What problem does the method solve?' --generate --output runs/my-new-answer.json
& .venv/Scripts/python.exe -m research_assistant.collections export --collection <id> --run runs/my-new-answer.json --format csv --output runs/my-new-evidence.csv
```

Public/local engineering evidence remains ignored under `runs/m8/m8-3/`: prospective plan and durable reservations, JUnit results (including the intermediate failure), downloaded-artifact proof, actual query artifacts, preservation proof, server logs/PIDs, screenshots and final acceptance receipt. PDFs, caches, credentials, volumes and private material stay out of Git. Source code and this report are on `codex/m8-user-collections`; main remains the preserved completed demonstration.
