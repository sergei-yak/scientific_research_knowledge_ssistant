# M5.6 - Frozen exploratory execution; human scoring pending

**Execution and anonymous export passed on 2026-11-18 (America/Chicago). M5.6 remains incomplete until real human scoring, sealing, guarded reveal and reporting finish. M6 remains reserved.** No condition-quality results are available at this checkpoint.

## Authorization and unchanged design

The user explicitly answered **"Authorize this frozen exploratory run"** to the exact freeze and numerical limits, acknowledging continuation despite M5.4's negative gate, possible outcome-informed question-selection bias and tight resource headroom. Human source validation does not remove the author's outcome-context exposure. This study remains exploratory.

- Freeze: `runs/retrieval-v2/m5-5/freeze-matched-v1.json`, SHA-256 `c64da42c62fe46bbd51220738a0016d00742bb1c606575cbb68c4db21374329c`.
- Actual authorization: `runs/retrieval-v2/m5-5/final-run-authorization-v1.json`, SHA-256 `6e4871c6b316005bf5ed9b34a043cae12e0f4459fdefa1531da927bf1e757897`; ID `a31d5335a3ea4d7e829607a42ded8a3d`.
- Verbatim question/reply: `runs/retrieval-v2/m5-5/m5-6/human-final-run-response-v1.json`. Recorded receipt time is not a human review-session time.
- The [approved run plan](M5_5_RUN_PLAN.md), [freeze report](M5_5_5_REPORT.md) and their original pending wording remain byte-for-byte historical records. Actual authorization/outcomes are separate additive receipts.

The unchanged design is 24 questions x 12 matched conditions (three profile/selector arms x four modes), at most 288 local Qwen generation attempts and 288 logical retrievals, context/output 4096/512, concurrency one, zero retries, $0 paid and no extra encoder comparison. All tracked files and launch HEAD `d8b9ba5b5433abce1bf62650267634cf3103ce23` remained fixed through generation and blind-packet export. No algorithm, source, model, dependency, lockfile or frozen runtime change was made.

## Actual execution and checks

| Check | Observed outcome |
|---|---|
| Dedicated runner | One invocation, exit code 0; `awaiting_blind_human_scores` |
| Answer matrix and anonymous export | **288 completed answer runs**, packet ready; no execution failure reported |
| Spending / additional comparison | **$0 paid**, zero extra encoder reads, no automatic retry or second invocation |
| Exact retained evaluation target | Runner checked the final read-only graph fingerprint; exact `m5eval-cf4d3a031091` container is stopped and retained |
| Frozen runtime and copied snapshot | **208** executable/config/model assets plus copied snapshot verified unchanged |
| Source preservation | Working graph, 1,427 chunks, current review head/catalog and **51** approved claims unchanged; development human/source replay ready |
| Original baseline | **118** frozen files, consumed freeze and final results report unchanged; baseline graph preserved; consumed target still stopped |
| Independent public preservation replay | **17 checks passed**; no new generation or retrieval request |
| Private separation | Dedicated runner alone consumed private inputs/outputs; development read/listed no private content |

`answer_runs` counts completed answer slots, including possible deterministic no-evidence abstentions. The public completion result does not expose exact actual provider-call/reservation totals, so **288 provider responses is not claimed**. These details remain in the evaluator-controlled records; development did not open them for a count.

RAM/VRAM samples were tight during execution. This one matrix completed under the approved configuration; it does not establish broader endurance, maximum-output performance on every call or production reliability.

Two **postexecution verification-harness** attempts were retained: the first mistakenly expected default settings to select the recorded source URI; the second used an unconfigured `Settings` constructor and failed authentication before source capture. Correcting the check to `Settings.from_env()` with the exact recorded source URI produced the 17 passing checks. These were public read-only checks, not failed study attempts, retries or changes to the frozen runner.

## Artifacts and remaining human checkpoint

Public receipts under `runs/retrieval-v2/m5-5/m5-6/`:

- `public-prelaunch-v1.json`, `public-launch-intent-v1.json`: actual authorization, file/model/target verification and launch provenance.
- `public-execution-outcome-v1.json`: actual runner completion/status and external packet locator.
- `public-postexecution-preservation-v1.json`: 17 passing checks; `postexecution-check-attempt-01.json` / `-02.json` preserve the corrected harness failures.
- `resource-status*.json`: public OS/service samples only; no private progress files were inspected.

The returned anonymous packet directory is `C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1/matched-executions/a31d5335a3ea4d7e829607a42ded8a3d/b379233668ed4804b764d3ee057aee05/blind/public`. User entry files: [anonymous answers](C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1/matched-executions/a31d5335a3ea4d7e829607a42ded8a3d/b379233668ed4804b764d3ee057aee05/blind/public/answers.json) and [blank scoring CSV](C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1/matched-executions/a31d5335a3ea4d7e829607a42ded8a3d/b379233668ed4804b764d3ee057aee05/blind/public/scores.csv). These links come from the runner's returned locator and fixed export contract; development has not opened/stat-tested the private files.

Follow the [human scoring guide](M5_6_HUMAN_SCORING.md). Make a **new** `scores-completed.csv` in that same packet directory, rate all 288 opaque answer IDs, and supply the completed file path. Preserve originals and use real decisions, identity and timezone-aware recording timestamps. Record actual active review time separately, or say not measured. Earlier source-annotation approvals are not answer-quality scores.

**Pending, not passed:** human answer scores, complete immutable score seal, guarded condition reveal, aggregate comparisons and final M5.6 report. No scores were inferred, no condition results revealed, and no new Graph-quality claim is made. Prior 363 offline/two corrected native passes retain their historical scope; no tests were rerun for these documentation-only updates. No other live provider, UI demonstration, new model/extraction or paid check was attempted. M6 remains unstarted.

The freeze has been used once. **Do not rerun/resume the evaluation, reset accounting, repeat immutable exports or restart the target.** Proceed only to actual human scoring and then the dedicated runner's bound seal/reveal workflow. Keep all private answers, notes, scores, ledgers and reveal maps outside development context.
