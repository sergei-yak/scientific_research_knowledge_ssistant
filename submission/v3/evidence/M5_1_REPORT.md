# M5.1 — Read-only diagnostic baseline

**Complete, 2026-11-15.** The saved development evidence points to two separate constraints: sparse approved cross-paper links and a selector that leaves new graph candidates below the evidence cutoff. Broader routes and shared ranking are reasonable experiments; neither has been implemented or shown to improve answers. Keep the existing papers for the first controlled comparison.

This is a post-evaluation diagnosis using the **eight public development questions**. It neither reopens the consumed final study nor reads its private questions, answers, scores or reveal mapping. Requirements remain [specification 6.2, R2.1–R2.8](../project_spec.md#planned-iteration-retrieval-v2).

## Scope, environment and preservation

Artifacts: [diagnostic directory](../runs/retrieval-v2/diagnostics/m5-1-20261115T203824Z-a4189b/). The immutable `diagnostic-manifest.json` records hypotheses H1–H4 and the bounded witness policy before the audit. Successful outputs are in `attempt-02/`; the initial failed helper attempt remains alongside them.

- `uv lock --check --offline`: **95 packages resolved**; `uv pip check`: **79 installed packages compatible**. No dependency changes or downloads.
- Docker was initially unavailable. `docker desktop start --detach` started the installed service; the existing working Neo4j container resumed and became healthy. No Compose recreation, pull, restore, volume reset or graph setup occurred. Neo4j **5.26.32 Community**, image ID `sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f`, is unchanged. The old evaluation target remained **exited**.
- RTX 4070 Ti: **12,282 MiB** total / **2,193 MiB** used at the recorded inspection. RAM: **33,387,216 KiB** total / **17,422,372 KiB** free. Ollama metadata identifies the pinned Qwen digest; no model was loaded at inspection. These are availability measurements, not a reranker fit or inference-performance test.
- All **118 frozen executable/model/configuration files**, runtime/source-tree bindings and snapshot/recovery commitments validate before and after. The old final report and acceptance file match their completed-handoff hashes. No final runner was launched.
- The working graph remains **1,996 nodes / 2,191 relationships**, fingerprint `e56b78bc3d96e1517f249433518f20087707bf872f5990ca116c412b663f5325`. Source chunks, current review head, active fact materialization and required ONLINE indexes validate using existing shared loaders/repository guards under the review lock.

Source corpus: `298e3cafbda1ffdf95c8ee66fa2b9ba3a81dc8d5e26bfb94816655ca41de3fbf`; source snapshot SHA-256: `157be4963f7a8afac6e5e3c3f174a4e5843cfc8ba09c3f949f75ebafa18b706d`. Review head remains `03724d5d24329b73ff53ca69bebc2df4b7e3707576ea15c8b7ccd12687019c64`; catalog SHA-256: `8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989`. Input bindings include the 32 saved runs, their original score summary, development manifest/source identity and diagnostic helper hashes.

## Findings

### H1/H2: reviewed connectivity limits the routes

The 20-paper / 1,427-chunk catalog has **51 approved claims: 43 Findings and eight Evaluations**. Findings cover all 20 papers; Evaluations cover only five. Three legacy route families—shared dataset, shared method and finding linkage—require an Evaluation at the starting paper; citation does not. This is a structural restriction, not a measured count of queries that would improve after removing it.

There are **21 reviewed entity IDs**. Only **MuSiQue** has the same reviewed method/dataset identity in multiple reporting papers: original HippoRAG and HippoRAG 2. The undirected paper projection of these shared semantic identities has one edge and **19 components**. Citation metadata supplies **16 separate directed links**, with ten undirected components (largest: 11 papers). Citation connectivity is not shared-benchmark evidence, approval of a new relation role, or proof of comparable conditions. Missing metadata is not proof of no citation.

### H3: candidates arrive, but do not survive selection

All **32 saved contexts and source-span scores replay exactly**, including six-unit / 1,800-token bounds. All eight saved Graph contexts equal their Hybrid + Facts counterparts. These are the **pre-restore M4.2 development-encoder artifacts**, not a new execution or the final study's development subset; rebuilt ANN indexes previously changed some contexts/scores.

The eight saved Graph traces contain **128 historical calls / 344 returned rows**. Deduplication leaves 64 candidate occurrences across questions: 36 already in their full fact-ablation pools and **28 new occurrences representing 16 distinct facts**. All were below the selected evidence cutoff:

| Question | Returned rows | Unique graph candidates | New outside full ablation pool | New merged ranks |
|---|---:|---:|---:|---|
| DEV-D1 | 33 | 10 | 5 | 33, 36, 38, 39, 40 |
| DEV-D2 | 50 | 7 | 2 | 36, 38 |
| DEV-C1 | 20 | 5 | 3 | 37, 39, 43 |
| DEV-C2 | 50 | 9 | 3 | 13, 18, 42 |
| DEV-M1 | 58 | 8 | 3 | 34, 35, 37 |
| DEV-M2 | 43 | 10 | 5 | 34, 35, 39, 44, 47 |
| DEV-U1 | 50 | 8 | 5 | 29, 31, 32, 36, 38 |
| DEV-U2 | 40 | 7 | 2 | 36, 39 |

Reassembling the recorded merged order with the **existing shared packer**, exact approved evidence and saved deterministic paths yields `unit_limit` for all 28 new occurrences. These are **reconstructed reasons**. The legacy fallback artifact retained the baseline's decisions; its original pre-fallback exclusion telemetry is unavailable and has not been overwritten or relabeled as observed.

The provisional merged order also changes baseline selection. Its reconstructed recall is lower than the eventual fallback on **five of six answerable questions**, equal on the sixth. None selects a new graph item. Exact fallback therefore preserves useful support in these cases. Forcing graph slots or simply retaining the provisional assembly would be unjustified.

### H4: some omissions are selection problems

The preregistered diagnostic probe scores existing candidates individually and up to 128 source-page-matching subsets per pool using the same bounded packer/scorer. It performs **804 offline probes**; 18 answerable-pool best witnesses replay exactly. Gold guides this diagnostic only, after saved retrieval, and never enters a retriever or selector.

For **DEV-C1**, the fact-ablation final recall is **0.5**, but two candidates already in that pool give complete registered support in **397 estimated tokens / two units**. The graph-merged pool admits the same result; no new graph-only support is needed. For DEV-M1, a Hybrid pool witness reaches 2/3 versus its saved final 1/3. Thus selection deserves attention independently of traversal.

No graph-merged witness exceeds the corresponding fact-ablation witness in these probes. DEV-C2's best found witness remains 0.5 in both. This does not prove absence or an optimal attainable score. These are **gold-assisted positive feasibility lower bounds**, not candidate Recall@K, retrieval performance or a deployable gold-aware selection strategy. Unanswerable recall/witnesses are **N/A**. Exact legacy candidate-support recall remains unavailable.

## Recorded next comparison and resolved ambiguities

The current [development comparison manifest](../runs/retrieval-v2/diagnostics/m5-1-20261115T203824Z-a4189b/development-comparison-manifest-v2.json) has SHA-256 `94ffd77ec1e71a83d8825e7e81b562a818cea18209c043f28a575d8e6f7b7269`. It fixes all eight unchanged public questions and all four modes in three planned arms, initially with the **same 51 approvals**:

| Arm | Routes | Selector |
|---|---|---|
| A0 | Implemented legacy reference | Recorded reference policy |
| A1 | R2 Finding/Evaluation/direct-entity starts | Same reference policy |
| A2 | Same R2 route policy | One shared cross-encoder across all four modes |

The future retrieval-only matrix is 96 reads, concurrency one, no retries, generation or paid calls. Run matched arms against the **same future isolated copy/indexes**; do not use saved pre-restore contexts as the paired reference for a fresh algorithm claim. Exact scope, code, model/native-input/score/feature and cache bindings must be recorded at the M5.2/M5.3 gates before execution. No reranker model has been chosen or downloaded here.

One comparison ambiguity was caught before execution: changing the selector can change the leading assembled seed evidence, hence Graph anchors and candidate pools. A2-versus-A1 Graph results therefore include that interaction; they cannot establish a pure fixed-pool reranker effect. **Manifest V2 corrects V1**, which remains historical. Non-Graph pool parity is still required. Additional fixed-pool attribution would need an explicitly recorded comparison, not an implied extra arm.

The operational advance gate requires all contracts to pass and, within A1 or A2, at least one selected novel graph item supplying a registered fact missing from paired fact-ablation context **and** greater mean final Graph recall over all six answerable questions. Otherwise record no-go for a larger Graph answer study under this hypothesis. This is a stopping policy, not a requirement to manufacture a graph win or a guarantee of answer quality. Enriched approvals, different papers, changed budgets and reranker-only research are separately recorded scope decisions.

## Actual checks, skips and handoff

- **875 audit assertions pass**: identity, current approval/materialization, saved source/context/score replay, graph-row ownership/path bounds and preservation. These are diagnostic assertions, not 875 unit tests.
- A second verification passes **1,594 assertions**, checking adjacency of all **1,567 path hops in 344 saved rows**, current graph identity and all **18 positive witnesses**; six unanswerable-pool entries remain N/A.
- New retrieval executions, generation/extraction requests, paid calls, downloads, application-data mutations and private access: **zero**. Writes are new diagnostic/report files and the normal owned review-lock lifecycle; service startup can write operational logs.
- Initial helper failure: wrong encoder-map key (`minilm`) caused a `KeyError` before materialization validation; corrected to the frozen `all-MiniLM-L6-v2` key and rerun into fresh `attempt-02/`. Earlier output and failure receipt remain. An exploratory Windows text read also required explicit UTF-8; application code was unaffected.
- **Not run:** fresh retrieval or latency trials, generation, encoder/reranker inference or fit tests, native fixtures that write test nodes, whole application test suite, UI restart/query, and held-out operations. No shared application interfaces changed. Original missing candidate-recall/pre-fallback/stage-work telemetry stays unavailable, not zero. Model compatibility and fresh-scope readiness are later gates.

Successful machine evidence: `attempt-02/audit-summary.json`, `checks.json`, `environment.json`, `catalog-and-integrity.json`, `input-bindings.json`, `saved-context-replays.json`, `graph-candidate-reconstruction.json`, `positive-feasibility-witnesses.json`, and root `routes-and-witnesses-verification.json`. Final documentation/integrity checks are in root `acceptance-final.json`.

**M5.1 has no remaining blocker. M5.2 is next and has not started:** create a separate implementation checkout and verified isolated Neo4j/review scope, then implement the profile and broader bounded routes. Source corpus/catalog enrichment and model selection remain separate factors. Original final results stay intact.
