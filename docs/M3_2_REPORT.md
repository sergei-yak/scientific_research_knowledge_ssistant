# M3.2 — Research workflows and checked evidence export

**Status: complete.** Streamlit discovery, comparison, limitations and Ask use the shared Python
query service. Evidence CSV export and stored-result display check current sources/approvals.
The selected local Qwen passes bounded product scenarios after an explicitly recorded abstention
correction. M3.3 integrations/recovery, corpus expansion and final evaluation remain open.

## Changes and boundaries

- `pipeline.run_query` serves CLI and UI, including retrieval-only runs. `result=null` means no
  accepted answer, not abstention. Immutable artifacts identify the submitted request/workflow,
  corpus/context/code, generator and resource observations. Generation errors now carry actual
  retrieval plus any available raw reply; CLI/UI preserve these locally.
- `product.py` projects only assembled evidence. Discovery/comparison rows require selected approved
  evaluations; limitations rows require selected approved findings. Explicit reviewed method/dataset
  mentions filter the structured view, without changing retrieval or adding generator context.
  Claims remain owned by their reporting papers, with separate conditions and source citations.
- Display/export uses shared context/token/source-span validation, approval projection replay, current
  review-head comparison and graph-projection verification. Changed heads, revoked/altered facts or
  service failures disable current display/export. Raw-source modes can export from verified local
  caches without requiring a review store. Downloaded files remain historical snapshots after export.
- CSV contains one row per shown excerpt: paper, URL/PDF page, claim/revision, JSON conditions,
  exact quotation, source/chunk/offsets, paths and request/effective-mode/context identity.
  Reversible apostrophe escaping protects spreadsheet-sensitive cells; `escaped_fields` records it.
  Verbatim raw text remains in JSON. The UI avoids the table widget's separate CSV download path.
- Streamlit has no Cypher, retrieval ranking or approval policy. It caches the CPU encoder, keeps
  ephemeral presentation state and persists immutable runs under ignored `runs/ui/`. Only explicit
  submission retrieves/generates; synthesis is opt-in. Reruns/downloads validate without inference.
  Excerpts, approved claims, selected paths and LLM synthesis are separate, with visible mode/fallback,
  unknown conditions and unverified parsed-section/table caveats.

## Actual checks and pilot outcomes

| Check | Observed result |
|---|---|
| Offline implementation suite | **118 passed**, four integration cases deselected; existing PyMuPDF/SWIG deprecation warnings only. |
| Explicitly enabled Neo4j fixtures | **2 passed**: controlled graph retrieval and review repository. Only fixture-owned resources cleaned; no production reset. |
| Lock/installed compatibility | `uv lock --check --offline`: 95 resolved; `uv pip check`: 79 installed, compatible. No dependency/lockfile changes. |
| Streamlit AppTest | Submission/rerun identity, no repeated generation, stale export disabling and old-result clearing pass with synthetic services. |
| Live UI | Discovery/comparison inspected in the browser; approved/raw panels, mode/fallback and missing/differing-condition notices present. Evidence download matches service output byte-for-byte after BOM decoding. |
| Source/review preservation | Original 325-chunk and pilot 571-chunk corpora, 23 current approved facts, unchanged review head and six metadata citation edges; six required indexes ONLINE. |
| Development replay | All **32 M3.1 contexts** pass shared integrity/source checks. Eight exact-bound human gold approvals remain ready. No gold entered retrieval/generation; no held-out access. |

Final scenario artifacts are listed in `runs/m3-2/acceptance-final.json`:

| Scenario | Observed source-backed view | Units / estimated tokens | CSV excerpt rows |
|---|---|---:|---:|
| Discovery on MuSiQue | Original HippoRAG and HippoRAG 2; two reporting papers, three approved evaluation rows with citations. | 6 / 1518 | 13 |
| Comparison on MuSiQue | Same two reporting papers; versions/splits/metrics/protocols explicitly missing or differing per claim. No controlled numerical ranking asserted. | 6 / 1564 | 10 |
| Original HippoRAG limitations | Two approved findings: NER/OpenIE errors and scalability beyond tested benchmarks, with exact evidence. | 6 / 1294 | 9 |
| Missing measured fine-tuning gain | Final answer scopes absence to provided evidence, flags insufficient evidence and has no supporting citations. | 6 / 1313 | 9 |

All four Graph requests effectively use **Hybrid + Facts**: discovery/comparison/abstention report
`graph_candidates_not_selected_within_budget`; limitations reports `no_new_eligible_graph_candidates`.
Their audit reads contain 65/69/50/50 bounded graph rows respectively and **zero selected graph paths**.
Representative actual shared-dataset, shared-method, citation and finding routes were inspected in
`real-path-inspection.json`, including HippoRAG 2 → MuSiQue → original HippoRAG and the outgoing
HippoRAG 2 → Graph RAG citation route. Reporting ownership/current revision/support checks pass.
These are inspected retrieval attempts, not hidden answer context or proof of a graph advantage.

## Development failure, correction and limits

There were **nine local generation calls total**, zero paid calls and no automatic retries/provider
substitution. Initial prompt output explained the missing measurement but incorrectly set
`insufficient_evidence=false`. Shared prompt `grounded-evidence-v2` clarified that explaining an
unavailable requested result is still abstention. The eighth call then flagged abstention but supplied
contextual citations, which the strict validator rejected. Its raw reply/timing were not retained by
the older failure path; this gap is disclosed rather than reconstructed.

The final correction does not infer semantic correctness: when the model itself flags abstention,
the shared answer boundary removes supporting citations, preserving raw output and recording
`answer_normalization` with discarded IDs. The ninth call passes; its original E1/E6 citations remain
in the raw reply and normalization record. Non-abstention invalid/missing citations still fail.
Future generation failures preserve available raw replies and source-backed retrieval artifacts.
Focused synthetic tests cover both this normalization and failure preservation.

The accepted final generation times were approximately 42.19/36.52/28.11/11.21 seconds, excluding
encoder loading. A concurrent resource probe observed about 6.12 GiB available RAM and 10,751 MiB
GPU usage with the local workload and healthy Neo4j. This is a point observation, not M3.3's complete
resource/provider acceptance. Model digest, native usage, prompts and settings are in each run.

These are small, unblinded development checks. Structured-row availability is not answer correctness
or completeness. Qwen can use shown raw excerpts beyond the approved claim fields; such synthesis
does not change approval/conditions. No human/blinded answer-quality score is claimed. The existing
DEV-C2 retrieval-coverage failure is unchanged; a separate MuSiQue comparison demonstrates the
product workflow without retuning rankings, editing gold or claiming that DEV-C2 now passes.

## Artifacts and next milestone

- Final accepted runs: `runs/m3-2/local-product-v2/{discovery,comparison,limitations}/run.json` and
  `runs/m3-2/abstention-final/abstention/run.json`; accompanying views/CSV stay local.
- Initial outcomes: `runs/m3-2/local-product/`; earlier successful outputs and the failed-call note
  remain historical. Final preservation/CSV checks: `runs/m3-2/acceptance-final.json`.
- Current gold readiness: `development-readiness-final.json`; resources: `resources-during-local.json`.
- Browser proof: `ui-comparison-final.png`; checked UI run under
  `runs/ui/f89f9305a7b14eeeb92199fb87861809/`. Download remains in the user's Downloads directory.
- Reproduction: `scripts/accept_m3_2.py`; executable commands and CSV rules are in README.
  Real source/review/run artifacts, screenshots and private annotations remain outside Git.

No M3.2 blocker remains. **Next: M3.3**, both adapters' live readiness and a verified restore into a
fresh disposable target. OpenAI credentials/approved numerical paid budget remain unavailable;
paid checks stay pending. No recovery test, corpus expansion, MPNet comparison or final evaluation
was performed in M3.2. The full five-paper gate remains closed until the remaining requirements pass.
