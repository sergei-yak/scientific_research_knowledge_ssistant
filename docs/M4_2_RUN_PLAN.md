# Frozen evaluation proposal — replacement being verified

The v1 artifact below is a historical draft, superseded before execution by stricter local-endpoint/immutable-image validation. A v2 snapshot/recovery/freeze is being verified; no approval is requested for v1. Preparing/verifying a proposal does not authorize generation on held-out questions.

## Committed state

- Freeze: `runs/m4-2/freeze-v1.json`, exact file SHA-256 **`9101694913b7b751090aa571473e87ccafe464c2e3b90c12cb3423487b71faf7`**.
- Code provenance: `ba150cadc59cb6104b82aecbc3d8577c672095de`. The manifest pins 118 executable/model/configuration files and runtime/lock versions. Later documentation-only commits are acceptable only while all frozen executable hashes still match.
- Snapshot: `runs/m4-2/snapshot-v1/`; 1,996 nodes, 2,191 relationships, 962 hashed assets. Expanded corpus: 20 papers / 1,427 unchanged chunks / 51 active approved claims.
- Public readiness: eight development questions plus 16 externally held-out questions, six total per category. Source/gold/review/file hashes and human approvals are committed without exposing private content here.
- Verified target: `dbu-m4-recovery-fa36ba3e391b`, Bolt `127.0.0.1:9765`, HTTP `127.0.0.1:9475`. Its volumes are retained/stopped; only this target will be started. Server read-only behavior and exact restore passed. The working database is separate.
- Generator: local `qwen3.8:latest`, digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`, temperature 0, thinking false. No provider substitution or model pull.

## Numerical limits and sequence

| Operation/control | Bound |
|---|---|
| Four-condition answer matrix | 24 questions × four MiniLM conditions = 96 runs |
| Local generation requests | At most **96**; failed/unknown attempts retain reservations |
| Separate encoder experiment | 24 questions × two encoders = **48 retrieval-only reads**, no additional generation |
| Logical retrieval requests | At most **144**; each uses the specification's bounded native queries, plus integrity/metadata checks |
| Model context / output | **4,096 / 512 tokens per request** |
| Concurrency / automatic retries | **1 / 0** |
| Paid-provider budget | **$0**; no OpenAI inference |
| Generation request timeout | 180 seconds |
| Native graph-query timeout | 30 seconds |

The question order uses frozen seed 4431. The four MiniLM conditions rotate by question position; no hidden question is used for warmup or tuning. MPNet remains a separate vector-only condition. Encoder order alternates within the separate experiment. Both use the same frozen chunks and the specification's ranking/threshold/evidence-budget contract. Query encoding/fetch timing and actual contexts are saved; latency includes integrity/index guards and does not claim a perfectly cold system cache.

The interpreter/libraries, cached encoder bytes/revisions, tokenizer/estimator assets, generator digest, executable files, graph/snapshot and public readiness commitments are checked before access to private inputs. Stripped questions are the only evaluation inputs passed to retrieval/generation. Gold is parsed for scoring after generation. The isolated evaluator has checked private query lengths; all fit both tokenizers.

## Private outputs, failure handling and scoring

Private inputs remain in `C:\Users\serge\DBU-GraphRAG-Evaluation\expansion-v1`. Runs, prompts, raw replies, contexts, evidence scores, source metadata, failure diagnostics, blind scoring packets and reveal mappings stay under its external execution directory. Even the scoring packet's `public/` subdirectory contains private questions/answers and must stay outside the development chat/repository.

A durable ledger keyed by the exact freeze SHA allows one started execution. A new directory or receipt cannot reset attempts. Missing authorization fails before private-path access; readiness/annotation approvals are not run authorization. Failed started studies retain their artifacts and require a disclosed amendment, never a silently repeated untouched test. Preflight failures before execution remain recorded without generation.

After the 96 answer runs and 48 encoder reads complete, the runner exports randomized anonymous answers and a blank human score form. It withholds condition results until all real human scores are complete and sealed. Correctness/citation support use the existing 0/0.5/1 rubric; abstention is separate. No AI-authored human scores or automatic LLM judge. The later reveal reports development and held-out results separately, paired wins/ties/losses, source-evidence recall (unanswerable N/A), encoder latency/recall, fallbacks and limitations.

## Authorization required

The user must explicitly approve this exact freeze and the bounds above once. That approval will be recorded in a new hash-bound `FinalRunAuthorization` receipt; the annotation-review receipt and exhausted M3.3 paid allowance do not qualify. No private/final execution has occurred during M4.2 preparation. Human score collection remains a later checkpoint after execution.
