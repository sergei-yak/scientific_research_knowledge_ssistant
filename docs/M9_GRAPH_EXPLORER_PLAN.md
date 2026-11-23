# M9 - Collection graph explorer

The user requests a visual map of nodes, edges and connections in the frontend. This adds a read-only product view after completed M8, without reopening either research study or changing retrieval. Use the existing M8 checkout/owned target and port8504. Preserve source/review/accounting data, old checkouts, frozen assets and all v1-v5 submission packages.

| ID | Work | Acceptance | Status |
|---|---|---|---|
| M9.1 | Typed collection-map contracts and shared source/current-review validation | Collection/head/source mismatch and stale/revoked/changed mappings cannot expose old claims. No encoding or generation. | Complete |
| M9.2 | Interactive frontend with zoom/pan, node/edge selection, source details and complete-view controls | All current logical document/review nodes and edges are available. Counts identify hidden passages/search records. Actual sparse graphs remain sparse. | Complete |
| M9.3 | Offline integrity/UI tests, read-only live checks and restarted actual browser | Verify both existing collections, sources, full counts and interactions; preserve data, original assets and dependencies. Report actual checks/skips. | Complete |

The map represents the current collection's logical source and published-review structure: collection, papers, passages, approved Findings/Evaluations, Method/Dataset definitions and their searchable FactText records. It is not an unrestricted Neo4j administration browser. Old revisions, rejected/pending proposals, other collections and database administration nodes are excluded. Unknown scientific mappings stay absent. MENTIONS keeps its discovery-only meaning. Paper/source ownership is not a scientific conclusion. Overview may hide passages/search records for readability; a full view exposes them with exact visible/total counts and no silent truncation.

Use existing locked Streamlit HTML iframe support and local HTML/JavaScript with no external CDN or new dependency. Render untrusted labels/quotes as text and escape embedded JSON. Do not add generated graph links, approval mutations or automatic extraction. Source PDF controls remain checked through shared collection verification. The view is independent of a question and must not be described as evidence that Graph retrieval improved an answer.

Fresh engineering bounds: at most24 explicit graph snapshot loads and8 supplemental read-only captures, zero model/provider/encoder/import/extraction/new-review/paid operations, zero retries. Offline synthetic tests do not create genuine approvals. The retained target alone may start/restart as needed. No writes to its scientific records or histories. Closed M8/study allowances are not reused. These limits are recorded prospectively in runs/m9/graph-explorer/plan-and-preservation-before.json.

Initial known limitation: the real AI collection has two approved claims without method/dataset mappings. Its map cannot show invented shared-method/benchmark links. Physics has no approved claims and can display document structure only. Neither is a new research quality test.

Actual outcomes and remaining limits are recorded in [M9_GRAPH_EXPLORER_REPORT.md](M9_GRAPH_EXPLORER_REPORT.md). The initial plan/bounds remain retained in the local immutable before record. [Pinned Streamlit HTML API reference](https://docs.streamlit.io/1.45.0/develop/api-reference/custom-components/st.components.v1.html).
