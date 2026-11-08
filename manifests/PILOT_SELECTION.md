# M2.1 pilot selection record

Recorded before claim extraction or retrieval comparisons on the additional papers (2026-11-07).
This is a purposive feasibility sample, not a systematic review or unbiased performance sample.

## Eligibility and selection

Retain the user's GraphRAG survey (2501.00309v2). Add four accessible original research papers
that explicitly use graph-structured retrieval over text. Cover both global summarization and
multi-hop QA, including a method and its successor to exercise attribution and citation links.
Use the first arXiv version of each added paper consistently, rather than choosing versions by
reported results; these are historical versions, not claims to reproduce the latest publication.
Verify titles/rights on versioned arXiv landing pages and pin downloaded PDF SHA-256 values.
Record actual OpenAlex matches and reference availability; a missing record/edge remains unknown.

| Paper | Inclusion reason |
|---|---|
| 2501.00309v2 — Retrieval-Augmented Generation with Graphs (GraphRAG) | Existing user-selected survey; taxonomy and qualitative scope. Survey reports do not own cited studies' experiments. Preserve M1's partial pages 1–52. |
| 2404.16130v1 — From Local to Global: A Graph RAG Approach to Query-Focused Summarization | Entity/community graph retrieval; global summarization contrasts with factual multi-hop retrieval. |
| 2405.14831v1 — HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models | Graph traversal and multi-hop QA; original paper owns its reported evaluations. |
| 2410.05779v1 — LightRAG: Simple and Fast Retrieval-Augmented Generation | Graph/vector and dual-level retrieval; a distinct indexing/retrieval design. |
| 2502.14802v1 — From RAG to Memory: Non-Parametric Continual Learning for Large Language Models | HippoRAG 2 successor, passage integration, overlapping method/dataset vocabulary. |

No additional papers are included at this stage: five is the pilot cap. Pure vector RAG, tree-only
retrieval, unrelated graph domains, inaccessible PDFs and duplicate versions are outside this
selection. No paper is selected because Graph RAG wins a test or because of held-out questions.
The existing survey predates HippoRAG 2, so its bibliography cannot establish that later citation.
Any final corpus expansion needs a separately recorded selection protocol and must disclose this pilot.

## Coverage and extraction policy

Inspect title/method/results/limitations pages, table reading order and bibliography boundaries.
For added papers, select readable main-body pages through the discussion/limitations before the
bibliography. Appendices are initially omitted; pages with mixed body/references are documented.
The source manifest records exact coverage and omissions; selection is not full-paper verification.

Each paper has at most eight longer, page/section-aware extraction passages and 12 generated
scientific-claim candidates in total. Prefer method/dataset descriptions, experimental setup and
qualitative limitations. Do not infer table values from flattened text or transfer baseline results
to the reporting paper's proposed method. Exact quote checks are mechanical validation only.
Passage choice/configuration is frozen before inference. Each request may return at most two
claims (the final request is restricted by the remaining allowance); no model retries or hidden
repair calls. Failed requests consume the configured request allowance. Uncovered sections and
unused allowance remain explicit. Human review starts later, with an initial 20-minute allowance
per paper; agents never populate approval decisions.

Development amendment D22: the first prompt under-extracted qualitative findings (five empty
batches, followed by one two-candidate dataset batch). One in-flight request was interrupted;
its possible candidates remain reserved. A versioned prompt clarifies that supported method
descriptions and survey challenges qualify as findings. At most eight cumulative requests per
paper are now allowed, including the first run, while the eight-distinct-passage and 12-candidate
caps are unchanged. This is an explicit development amendment, not an automatic retry or a
claim of extraction accuracy. Original prompts/responses and empty bundles are preserved.
