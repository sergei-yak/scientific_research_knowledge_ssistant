# M8.1 - User collection foundation

**Status: complete, 21 November 2026.** This is the first implementation increment of M8, not completion of the upload/QA product. The user authorized starting M8. M8.2-M8.5 remain not_started. The existing M6 demonstration and both completed studies are preserved. No inference, paid call, PDF import or private evaluation access occurred.

## Changes and boundaries

- Worktree: `C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections`, branch `codex/m8-user-collections`. Source is based on preserved M6 commit `14ec3a4`; M6 runtime source was not changed.
- `collections/contracts.py`: frozen, versioned `UserCollection`, `DocumentVersion`, `CorpusBinding`, `ImportJob`, input and resource contracts. Stable collection IDs and corpus identities bind collection/revision/source membership. Source IDs bind actual PDF hashes; documents cannot borrow curated paper IDs. Exact review paths are derived per collection/revision, never supplied by the UI.
- `collections/store.py`: create-only revision/status records, predecessor and content hashes, owner marker, exclusive writer/import lock and optimistic expected heads. Collection creation, rename/revision, listing, explicit queue/interrupt and restart replay use one shared service. No implicit overwrite, lock takeover, request, approval or ready status.
- `collections/scope.py` and the shared graph-write guard: match exact M8 container/image/project, loopback port, independent named writable volumes and workspace owner. Reject foreign checkout/settings, mixed M5/M8 declarations, read-only databases and frozen corpora. Registry metadata is available while the target is stopped; graph writes require live re-attestation.
- `collections/__main__.py`: thin list/create/show/rename/scope-check CLI over these services. Invalid configuration cannot echo credential URLs. Streamlit integration follows in M8.3.
- `scripts/setup_user_collections.py`: one-time, empty-target setup. Existing environment/scope/storage paths or UUID volume collisions stop setup. The script does not restore a snapshot, replace data, pull an image, grant paid access or create claims. Specification 6.7 and the plan record actual status; exact 6.6 planning specifications are archived.

The v1 numeric input/resource/network policy is fixed in [M8_PLAN.md](M8_PLAN.md). Actual download streaming, PDF parsing, byte/page/chunk counting and every DNS/redirect address check belong to M8.2. Current URL validation checks syntax only. Current collection descriptions deliberately return no available retrieval modes: an index binding alone does not prove index/review readiness.

## Environment and isolated target

Python 3.11.13 and the existing `uv.lock` are unchanged. The initial offline install could not find the cached CUDA PyTorch wheel. Exact local M6 dependency files were reused using filesystem hardlinks and private copies of editable metadata/launchers, then the new editable package was installed from this checkout. No dependency was upgraded or downloaded. Use Python module entry points to avoid copied console launchers carrying old absolute paths.

Both `uv sync --locked --offline` with the default new-worktree cache and `uv lock --check --offline` pass. `uv pip check --python .venv/Scripts/python.exe` passes (79 installed packages, 95 cross-platform lock entries). The imported package resolves to the M8 `src/` directory. Lockfile SHA-256 remains `5dea9230ac08c730024457f5e102690c0ba8e00f9f4140b25a0d93afdd9186fe`.

Initial resource observations: 31.84 GiB RAM, 17.16 GiB free RAM, 309.54 GiB free disk; after Docker startup and its two existing working containers, 13.22 GiB RAM was free before creating M8. Docker was initially unavailable. Starting Docker Desktop also restarted the baseline and retained development containers through their existing restart policies; no consumed evaluation target was started. Both working graph captures were compared before/after and stayed unchanged. This is setup evidence, not an inference-capacity or latency claim.

The new target is `dbu-m8-user-c09ff451237f`, Bolt `127.0.0.1:65488`, pinned image `sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f`. Its own `neo4j_data`/`neo4j_logs` volumes, container ID and checkout-local registry bind `m8user-c09ff451237f`. A new local password is kept only in ignored `.env`. No credential/review/accounting store was inherited. The database contains one M8 owner marker and no research/PDF records. One explicitly empty example collection is retained; its synthetic metadata-only import reservation was explicitly interrupted, preserving both events. **The M8 container is stopped and retained after verification.**

## Actual checks

| Check | Result |
|---|---|
| Locked environment and dependency compatibility | Passed; lock unchanged, no downloads/upgrades. |
| Initial focused collection tests | First collection failed on a missing brace, corrected before execution; then 34 passed. |
| Final offline suite | **414 passed, 8 integration cases deselected**, 5 existing PyMuPDF/SWIG deprecation warnings, no failures. This includes 40 new offline collection checks. |
| Separate M8 native integration | **1 passed** on the exact new target; no legacy target writes. |
| Native ownership/write capability | Physical identity and workspace owner passed; writable probe rolled back. A new UUID-owned frozen Corpus caused write refusal; only that test-owned node was then removed. Database returned to its original single owner marker. |
| Persistence/restart | Separate CLI processes returned identical registry JSON before/after an actual M8 container restart; exact container ownership and scope-check still passed. |
| Isolation/failure tests | Foreign roots, corpus/review revisions, default/rebound ports, container/image/volume substitution, read-only/frozen state, mixed research scopes, duplicate members, resource caps, stale heads/locks, corrupt history and unsupported URL/file syntax rejected. |
| Preserved working graphs | Baseline and retained M5 each remain 1,996 nodes / 2,191 relationships; complete canonical captures match their pre-setup hashes. |
| Preserved frozen runtime files | All **118 baseline + 208 retained M5** hashes replay unchanged. Existing M6 source, class report and M7 packages unchanged. |

The seven other historical integration cases were not rerun. No live URL/PDF, neural-model/generation, new UI query or human graph-review check was performed; those are dependent M8.2-M8.5 gates, not passes. No M8 UI server is running, and the retained M6 UI does not load changed M8 source.

Evidence is under ignored `runs/m8/m8-1/`: `environment-copy.json`, `target-plan.json`, `target-setup.json`, `offline-final-junit.xml`, `native-junit.xml`, `native-proof.json`, `restart-cli-proof.json`, `scope-check-cli.json`, before/after protected-target records, and final stopped-target state. Failed setup/test attempts are retained rather than rewritten as passes.

## Commands and next increment

Run from the M8 checkout in PowerShell:

```powershell
Set-Location 'C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections'
uv sync --locked --offline
& .venv/Scripts/python.exe -m research_assistant.collections list
& .venv/Scripts/python.exe -m research_assistant.collections create --name 'My research collection'
```

Listing/creation changes metadata only and works with the M8 database stopped. To verify its live write ownership, start **this checkout's own declared project** first:

```powershell
docker compose up -d --pull never neo4j
& .venv/Scripts/python.exe -m research_assistant.collections scope-check
docker compose stop neo4j
```

Never run setup again over the retained environment/registry/volumes, copy the scope to another checkout, or use a baseline/M5 target for M8. `scope-check` requires Neo4j to be ready; a service-start delay is not a reason to alter ownership declarations.

There is no unresolved M8.1 blocker. **Next: M8.2**, implementing the bounded PDF/upload/link worker and actual source snapshots using these contracts. M8 is still in progress; there is no upload button or user-document QA yet. The earlier class-progress PDF remains a preimplementation snapshot and is not recalculated by this code increment. M7 remains internal reporting/preparation, not a product feature.
