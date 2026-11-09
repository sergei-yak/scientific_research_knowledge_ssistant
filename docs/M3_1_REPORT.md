# M3.1 — Controlled retrieval and bounded graph traversal

**Status: complete.** Vector, Hybrid, Hybrid + Approved Facts and Graph are executable through
shared services and the CLI. The isolated native fixture proves source-backed cross-paper graph
expansion beyond the exact Hybrid + Facts pool. All four templates have saved EXPLAIN/PROFILE
plans on fixture and pilot data. M3.2 product acceptance and M3.3 integrations/recovery remain open;
corpus expansion and final evaluation have not begun.

**Material result:** all eight real development Graph requests fell back to Hybrid + Facts, with
identical assembled baseline contexts. This pilot shows no additional graph evidence reaching the
generator context. The synthetic traversal proof is a capability check, not evidence of superiority.

## Task outcomes and boundaries

| M3.1 requirement | Actual outcome |
|---|---|
| Controlled conditions | Preserved the M1 vector pool/threshold. Added native lexical search and equal-contribution RRF; fact modes share the same four channel rankings and fact representation. |
| Real graph traversal | Shared dataset, shared method, incoming/outgoing citation and method/evaluation finding routes execute fixed parameterized Cypher. Every target retains its reporting paper and current approved support. |
| Common evidence contract | One renderer/packer enforces six units, three excerpts per fact and 1,800 estimated tokens, including serialized paths. All 32 pilot reads passed; maximum observed context was 1,585 tokens. |
| Bounded selection and fallback | Up to four assembled baseline seeds, five ordered rows per seed/template, 80 returned rows and 40 retained graph candidates. Shortest then lexically stable paths deduplicate targets. No surviving new unit means exact baseline fallback. |
| Integrity | Current journal head, sources, claim revisions, paper owners, support edges, conditions and entity/alias definitions are checked. Stale data, wrong ownership/dataset links and service failures raise errors rather than mode fallback. |
| Query work inspection | All four fixture/pilot plans use unique index seeks and no AllNodesScan. Actual intermediate cardinalities and database hits are recorded; final LIMIT 5 is not claimed as a database-work bound. |

`graph/search.py` owns index setup, guarded read transactions, native search and graph-materialization
checks. `graph/templates.py` owns the four routes. `retrieval/catalog.py` consumes the existing shared
review eligibility projection, resolves aliases and supplies retrieval primitives; `retrieval/service.py`
owns fusion, expansion, selection and fallback. CLI/answer entry points call these services. No gold
annotations or reference answers enter retrieval or generation services.

The raw source-cache verifier is now shared across vector, hybrid and fact support reads. Existing
M1 vector ranking, chunk boundaries and embeddings were preserved. `RetrievalResult.audit` records
channels, native scores, RRF order, review head, seeds, graph calls, paths and selection decisions;
only the shared rendered evidence context goes to generation. `ask --mode` uses that same result.

## Clarifications and implementation decisions

- Existing alias fallback was underspecified across entity types. It is now explicitly **per kind**:
  question method aliases take precedence over seed method aliases, and likewise for datasets.
  A method mention therefore does not suppress a reviewed dataset shown in a seed. The spec,
  submission summary and decision log are synchronized. Seed-only aliases never increase question
  overlap; NFKC/casefold word-boundary matching retains ambiguous candidates without merging them.
- Graph seeds are the first four assembled Hybrid + Facts units. Fixed paths remain within the
  selected corpus. Citation metadata is discovery only; a cited/citing target must independently
  be a current, source-backed approved fact. The pilot contains method-linked findings; the
  evaluation-specific finding branch is also exercised by explicit synthetic fixture topology.
- Hybrid vector channels use the declared top-12 rankings without M1's vector-only 0.30 threshold.
  ANN overfetch is 24, followed by actual-cosine ordering; full-text lists are top 12 by native rank
  and stable ID. Question text becomes at most 128 unique literal lexical terms. Native lexical
  and vector scores are recorded but never numerically combined. RRF remains `k=60`.
- Explicit `search-setup` adds chunk full-text and method/dataset alias indexes; queries never create
  indexes or synchronize approvals automatically. Alias indexes retain historical definitions;
  exact question matching uses the current reviewed catalog, not historical index hits.
- `GRAPH_QUERY_TIMEOUT_SECONDS` defaults to 30 and accepts 0.001–30 seconds. It bounds the entire
  retrieval read transaction, including channel/catalog/traversal reads. The server's timeout
  monitor has scheduling granularity; this is not an exact wall-clock service-level guarantee.
- Fact queries hold the review-store lock and check the graph head before/after their read transaction.
  Graph errors do not silently downgrade a request. Only a successful no-new-selected-evidence case
  returns `effective_mode=hybrid_facts` with a recorded fallback reason.

No dependency versions changed. There were no additional papers, claim approvals or review-limit
extensions. The two deferred GraphRAG drafts remain unapproved. No incompatible requirement remains
unresolved; the alias-fallback ambiguity was clarified rather than left implicit in implementation.

## Actual verification

- `uv run --locked --offline pytest -m "not integration"`: **95 passed**, four integration cases
  deselected; 99 collected. Twenty new offline cases exercise rank-only fusion consumers, ambiguity,
  per-kind fallback, source mismatch, wrong-paper rejection, exact fallback including rejected/oversized
  graph candidates, path accounting, timeout validation, bounded candidates and answer-service wiring.
- With `RUN_RETRIEVAL_SMOKE=1` and `RUN_REVIEW_SMOKE=1`, separately ran
  `tests/integration/test_graph_retrieval_repository.py` and `test_review_repository.py`: **two passed**.
  UUID-owned synthetic data proved a new cross-paper item absent from the fused Hybrid + Facts pool
  after native channel top-12 selection,
  all four routes (including citation directions and evaluation-specific findings), stale-head
  rejection, wrong-paper/dataset rejection, revoked-fact removal from every channel/path, alias
  invalidation, active-only indexes and preserved history. Only fixture-owned nodes/indexes were
  cleaned up; shared schema and production data remain.
- Real timeout check: a 1 ms read transaction was allowed a bounded three-second idle interval;
  the subsequent read failed with `Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration`.
- `uv lock --check --offline`, `uv pip check`, CLI help and whitespace checks passed. The lockfile is
  unchanged; 95 resolved / 79 installed packages remain compatible. Five upstream PyMuPDF SWIG
  deprecation warnings occurred in pytest. Initial legacy subquery deprecation warnings were removed
  by using the pinned Neo4j 5.26 scoped CALL syntax.
- Read-only preservation checks passed: M1 corpus **325 chunks**, pilot **571**, **23 approved facts**,
  **six** metadata citation edges, unchanged review head and **eight** gold approvals. All six relevant
  search indexes are ONLINE, and the final fixture left zero owned nodes behind.

The two M0 Neo4j/Ollama pytest probes were not rerun. No LLM generation, answer-quality test,
secondary-provider live test or restore test was run in M3.1. Those checks are not passes. Secondary
provider completion/live access and recovery remain M3.3; paid calls still need a numerical budget.
There were **zero LLM/paid calls, zero new model downloads and zero held-out accesses**.

## Inspected query plans

Counts below are actual operator work, not a promise of constant work after corpus expansion.
Every plan has indexed seed/review-state starts; bounded products join unique lookup results.

| Template | Fixture rows / DB hits / max operator rows | Pilot rows / DB hits / max operator rows |
|---|---|---|
| Shared dataset | 1 / 237 / 14 | 5 / 330 / 59 |
| Shared method | 1 / 238 / 14 | 5 / 496 / 118 |
| Citation | 5 / 456 / 14 | 5 / 1,694 / 66 |
| Finding | 2 / 334 / 14 | 5 / 791 / 66 |

Raw plans and parameters are retained, so these summaries can be checked independently. Planning
and profiling use driver query summaries; see the [Neo4j driver reference](https://neo4j.com/docs/python-manual/current/result-summary/).
Full-text search uses the [Neo4j 5 procedure/index contract](https://neo4j.com/docs/cypher-manual/5/indexes/semantic-indexes/full-text-indexes/),
verified against the installed 5.26.32 service. Reinspect work after material corpus changes.

## Exploratory development reads

Saved **32 retrieval-only runs**: eight accepted development questions across four conditions. Gold
was loaded by an evaluation-only scorer after every retrieval artifact was saved; retrievers received
stripped question requests only. All fact content matched the shared approved representation.
Graph used the identical Hybrid + Facts channel lists. Seven fallbacks had new graph candidates
that did not survive selection/unit/token limits; one had no new eligible candidate. All eight
fallbacks preserved evidence, aliases, context text/hash, token count and packing decisions exactly.
Maximum returned graph rows were 78; maximum retained unique graph candidates were ten.

| Condition | Mean evidence-fact recall, six answerable development questions | Median retrieval ms, eight requests |
|---|---:|---:|
| Vector | 0.278 | 46.91 |
| Hybrid | 0.500 | 45.23 |
| Hybrid + Approved Facts | 0.750 | 94.22 |
| Graph (all effective Hybrid + Facts) | 0.750 | 147.39 |

Unanswerable evidence recall is N/A. These are small, unblinded development observations with warm
indexes, not held-out findings, generation correctness or population superiority claims. DEV-C2's
actual assembled contexts did not cover its sufficient gold set; the comparison workflow is not
claimed as passed. Inspect retrieval/equivalent support during product acceptance; do not silently
rewrite gold to credit a mode. The verified batch's encoder load took 5.67 s separately. An initial
CLI probe took 52.24 s including startup versus 4.55 s retrieval, so the warm medians are not cold
end-to-end latency guarantees.

## Corrections, artifacts and next step

Initial fixture corrections are retained in the development history: repeated synthetic source
spans were deduplicated to one seed until distinct pages were used; a remote target with no alias
advantage correctly lost selection until the controlled fixture exercised explicit reviewed aliases;
a fast arithmetic probe completed before timeout monitoring, so a bounded idle transaction replaced
it. An early plan summarizer read `records` instead of the driver's `rows`; raw plans were intact,
and final summaries use actual rows. The initial global alias fallback suppressed dataset expansion
for method-only questions; a per-kind regression test and synchronized clarification corrected it.

- Native fixture proof/plans: `runs/m3/fixture-proof-acceptance.json`.
- Verified real reads, scores and raw plans: `runs/m3/pilot-verified/`, especially `summary.json` and
  `plans.json`. Earlier initial/first-pilot artifacts remain preserved without overwrite.
- Preservation/index audit: `runs/m3/preservation-final.json`; earlier audits remain preserved.
- Setup/CLI probe: `runs/m3/search-setup-initial.json`, `runs/m3/initial-graph-read.json`.
- Reproduction scripts are local under `runs/m3/`; executable service commands are in README.
  Artifacts record code/source/review identities while implementation was uncommitted; the exact
  source-tree hashes are preserved. Real source/gold/run data and receipts remain outside Git.

There is no remaining M3.1 blocker. Next is **M3.2**: Streamlit discovery/comparison/limitations and
CSV export using the same services, with honest missing-evidence and mode/fallback displays.
M3.3 still owns secondary-provider/resource checks and a verified restore into a fresh target.
Only the full five-paper acceptance gate permits expansion; M4 still owns freeze and final evaluation.
