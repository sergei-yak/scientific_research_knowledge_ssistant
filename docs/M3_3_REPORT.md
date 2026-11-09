# M3.3 — Provider readiness and verified recovery

**Status: complete.** Both SDK adapters passed real plain-text and validated-JSON probes. Local
resources were measured with the CPU encoder and healthy production Neo4j. A final logical snapshot
restored exactly into new disposable volumes, with copied-source retrieval/scoring/product acceptance
and native guard checks. The M3 five-paper gate passed; M4.1/final evaluation have not started.

## Implemented boundaries

- The shared `llm.create_client` selects only the configured extraction/generation provider. CLI,
  pipeline, extraction and UI use the same adapters/contracts; Qwen remains selected. No automatic
  provider/model substitution, SDK retries or dependency changes were introduced.
- The OpenAI Responses adapter preserves raw replies, native usage/model identity, request settings
  and failures. Fixed-field schemas use strict structured output; open mapping schemas use explicitly
  logged JSON mode and full Pydantic validation. Missing usage, refusal, truncation, malformed JSON,
  unexpected models and context/output violations fail visibly.
- Paid operations require scoped numerical approval. One project-root journal serializes paid calls
  across clients/processes and durably reserves a conservative token-cost bound before transport.
  All attempts count; failed/unknown reservations remain consumed. Readiness approval cannot fund
  application generation/extraction. The fixed ledger location prevents working-directory changes
  from resetting consumption; receipts never reset the journal.
- Logical recovery captures all project-owned current/historical graph data and schema using stable
  `(base label, id)` identities; IDs are not globally unique across different node types. It verifies
  current human eligibility/projection under the review lock and rejects changing graph/assets.
  Restore requires an attested, separate, empty Compose target and refuses existing data/schema.
  Property values remain parameterized; labels/types/schema identifiers are restricted. No deletes,
  source reset, working-volume overwrite or production database shutdown occurred.

## Actual checks

| Check | Observed result |
|---|---|
| Offline suite | **153 passed**, four integration cases deselected; existing SWIG/PyMuPDF deprecation warnings only. |
| Native integration guards | **2 passed** on each isolated restored target, including traversal/source ownership, revocation, indexes and timeout behavior; UUID fixture resources cleaned. |
| Local adapter | Text `READY` and JSON `{"status":"ok","value":2}` passed; two agent-initiated inference calls, context 4096/output 128, retries 0, concurrency 1. |
| OpenAI adapter | Same two probes passed with `gpt-6.1-terra` after credential replacement; three HTTP attempts total including the initial 401. |
| Locked environment | `uv lock --check --offline`: 95 resolved; `uv pip check`: 79 installed, compatible. Lockfile/package versions unchanged. |
| Restored workflows | Discovery, comparison, limitations and CSV export passed using copied source/review files and the restored database, with no LLM calls. |
| Scoring | All **32 saved-context scores reproduced exactly**; 32 fresh development retrievals scored. Four rebuilt-index contexts differed; covered facts and evidence-recall scores did not change. |
| Overwrite guard | A second restore into the now-nonempty target was refused; its data and the working graph remained unchanged. |
| UI handoff | Streamlit fully restarted after interface changes; actual browser discovery query passed with six units/1518 estimated tokens and explicit Hybrid + Facts fallback. Generation was disabled for this check. |

The local model digest remains
`22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`
(27.3B, Q4_K_M). Local text/JSON calls took approximately 21.12/3.15 seconds. The loaded-workload
observation had about 5.40 GiB available RAM and 11,668/12,282 MiB GPU usage. CPU MiniLM inference
ran between probes with Neo4j available. These are bounded coexistence observations, not a load-test SLA.
OpenAI text/JSON calls took approximately 2.84/1.60 seconds. Cloud identity is a provider model name,
not a cryptographic weights digest. Full request/response/model/resource metadata remains local.

## Paid authorization and the resolved failure

The user first approved $0.10 total, at most two requests, $0.05 per request, output 128, concurrency
one and zero retries. The first request failed with **401: API key expired**. No automatic retry ran.
After replacing the key, the user explicitly amended the request cap to **three total attempts**,
including the failure, with all monetary/output/concurrency/retry limits unchanged. Both remaining
probes then passed. Credentials were never printed, copied into snapshots or committed.

The ledger contains three reservations totaling **$0.070360**. This is a conservative reserved upper
bound, **not an invoice**. The two completed calls reported 94 input/21 output tokens; at the checked
Standard text rates their usage-based estimate is $0.000199. Billing was not independently retrieved,
and the failed request's complete reservation remains retained. The request allowance is exhausted;
no further paid operations are authorized by these receipts.

Receipts are under `data/accounting/approvals/`, with the initial/amended verbatim user responses and
the amendment's parent hash. `data/accounting/openai.jsonl` preserves the hash-chained reservations,
the failed attempt and completed response identities/usage. The approval was applied only to probe
settings; `.env` provider selection was not changed by the agent. Model/rates and the Responses schema
were checked against official [model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
and [structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
The adapter's conservative price review expires after 14 days and requires deliberate re-verification.

## Snapshot and restore evidence

Final snapshot: `runs/m3-3/snapshot-final/`; **993 nodes, 1,056 relationships, 395 checksummed files**.
This includes historical data, not only the active pilot: 923 chunk nodes, seven corpus nodes,
26 fact representations (23 active), five papers and the current review/entity records. Original
325-chunk/pilot 571-chunk corpora, 23 approved claims, six citation edges and eight human gold
approvals remain intact; no new scientific approvals were created.

- Semantic graph/schema SHA-256:
  `304de9e5660277e2649e35a26613c2199e69a641abca9535764e0bbac8861a09`.
- Snapshot manifest SHA-256:
  `846fb4930472670bc92b3f2bae2d24f0e5bb0e2944dad50dce65ae9d76fbed09`.
- Final target: `dbu-m3-recovery-cdf59e239ca1`, loopback Bolt 8765/HTTP 8475, with its own
  `_neo4j_data` and `_neo4j_logs` volumes. It is stopped and retained for inspection.
- Neo4j 5.26.32 Community image:
  `sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f`.
- `recovery-final/report.json` records exact commands, target/image/volume identities, unchanged
  source/backup assets, successful second-restore refusal and eight approved development bindings.
  `scoring-replay.json`, `fresh-retrieval/`, `products/` and `native-guards.log` retain detailed results.
  Earlier `snapshot-v1/`/`recovery-v1/` remain historical and their separate target is also stopped.

Fresh rebuilt-index context changes were DEV-D2 and DEV-U1 in Vector/Hybrid. No coverage score changed.
This illustrates why saved contexts/scores are preserved rather than assuming rebuilt ANN indexes
produce identical rankings. DEV-C2's known coverage limitation and the pilot's lack of selected new
graph evidence remain; no retuning, gold edits, graph advantage or blinded answer-quality result is claimed.

## Limits, skipped checks and next milestone

No required M3.3 check remains pending. Optional native offline dump/load was not used; the tested
logical route kept the working database online. Recovery requires the locked Python environment and
separately cached pinned encoder weights; these large caches are not part of the snapshot. OpenAI's
open-map JSON-mode branch is offline-tested, with no extra paid live test beyond the required strict
JSON probe. Original live probe artifacts retain their adapter-default prompt-version labels and exact
dummy messages; the current entry point assigns a separate readiness prompt version for future probes.
Neo4j emitted index-provider deprecation/unused optional relationship notifications during reconstruction;
semantic equality, native guards and actual retrieval passed. Four optional integration cases were
deselected from the offline run; two native guards and adapter CLI probes were run explicitly.

`runs/m3-3/acceptance-final.json` binds both successful provider records and final recovery evidence.
`verification-final.json` records the final 153-test checkpoint, including explicit provider-check failure
exit codes. The snapshot preserves code at export time; the later CLI exit-status correction is tracked
in the final Git checkpoint without altering historical snapshots or repeating paid probes.
The initial 401 report remains `openai-authorized.json`; success is in `openai-replacement-key.json`.
`providers-initial.json` contains the successful local probes and the then-pending OpenAI configuration.
Snapshot/report data, financial journals, review receipts, raw PDFs and development gold stay outside Git.
No held-out directory was listed/read. No corpus expansion, MPNet experiment or final evaluation occurred.

**Next: M4.1**, record final corpus selection rules and scoring readiness before expanding. M4.2 still
requires an explicit frozen final-run authorization. The selected generator remains local Qwen.
