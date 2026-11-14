# M4.1 evaluator handoff

**Pending human/evaluator work. No final evaluation is authorized.** The development agent must not create, list, search or read held-out questions, gold or reveal mappings. Use an evaluator-controlled directory outside this repository; do not paste private content into this chat. A Git ignore rule does not establish that boundary.

## Inputs and deliverables

The expanded corpus's claim review is complete (28 new approvals, 51 active claims). All eight development annotations in `data/evaluation/development/expansion-v1/` have fresh exact-bound human validations; source/receipt replay reports ready. Use the specification's evaluation and source-span contracts; reference answers must be supported independently of the approved graph. Shared Python models: `EvaluationQuestion`, `GoldFact`, `SourceSpanRef`; annotation scoring: `evaluation/scoring.py`. Source offsets are half-open offsets in the frozen normalized chunk, not the PDF bytes. Alternative support sets are OR; all spans within one set are AND. Include facts missing from the graph where warranted. Do not require an observed graph advantage.

- Final manifest: **24 questions**, six per primary category (direct, cross-paper, multi-hop, unanswerable); **8 development** (two/category) and **16 held-out** (four/category). Apply category precedence from the specification. Store stripped questions separately from answers/support annotations. No mode, graph claim ID or gold text enters retrieval/generation inputs.
- Preserve both the eight original five-paper validations and the eight fresh expanded-corpus validations. The expanded version rechecks answer/span coverage and scoped unanswerability across the 1,427 indexed chunks; it inherits no pilot approval. The two absence rationales are revision 3. A source hash check alone does not establish unanswerability. Any annotation edit requires a versioned amendment and fresh validation. Commit the reviewed version before authoring/finalizing the private partition; the M4.2 experiment freeze is still pending.
- Prepare 16 held-out questions and annotations privately. Record the corpus scope and rationale for every unanswerable question, distinguish a missing measurement from an author's suggested benefit, and do not silently use omitted appendices or later PDF versions. This agent has not accessed private inputs.
- Return only public commitments: evaluator identity, timezone-aware validation date, exact corpus/review/development hashes, private question/annotation file SHA-256 values and category counts. `evaluation/readiness.py::EvaluatorAttestation` defines this receipt. Never return private content or a reveal map here. A validated receipt is an **attestation**, not independent inspection by the development agent; disclose any exposure and corrections.

Current public bindings, verified in `runs/m4-1/development-gold-acceptance.json`:

| Binding | Value |
|---|---|
| `corpus_id` | `298e3cafbda1ffdf95c8ee66fa2b9ba3a81dc8d5e26bfb94816655ca41de3fbf` |
| `review_head` | `03724d5d24329b73ff53ca69bebc2df4b7e3707576ea15c8b7ccd12687019c64` |
| `development_dataset_sha256` (canonical manifest fingerprint) | `656cb3b5d41463e3eaa110cd6634d6d16d4452a995077de853f56d64f8fc95a3` |
| Normalized source-chunk snapshot SHA-256 | `157be4963f7a8afac6e5e3c3f174a4e5843cfc8ba09c3f949f75ebafa18b706d` |
| Development counts | Two each: direct, cross-paper, multi-hop, unanswerable |

The evaluator still needs to prepare and validate the 16 private questions/annotations (four per category) outside the development workspace, hash those files locally, and return only the public attestation defined by `manifests/evaluator-attestation.schema.json`. No private-file hashes or validation claims have been supplied yet. Development readiness does not grant final-run authorization.

An AI-assisted drafting option is prepared in `docs/EVALUATOR_AGENT_TASK.md`. It requires a separately authorized evaluator agent with no development-chat history and external private outputs. It does not replace human validation, provide OS-level isolation, or authorize final execution. No evaluator agent has been dispatched and no private questions have been created by this development chat.

## Scoring rehearsal and rubric

`evaluation/blinding.py` currently supports **development-only rehearsals**, not private final execution. It requires a complete four-condition matrix and valid saved answers/contexts, assigns random anonymous IDs, shuffles answers and exports `public/answers.json` plus a blank `public/scores.csv`. Identity mapping stays in `private/reveal.json`; its hash is committed before scoring. Do not open the mapping until the completed form is sealed. Do not copy this development directory layout into the workspace for held-out data. M4.2 must supply a separately authorized evaluator-controlled final runner.

The public packet contains the unchanged question/answer, abstention flag and cited source quotations. It omits requested/effective modes, fallback, ranks, timing, graph paths, provider identity and internal item IDs. Answer wording and evidence can still hint at a condition; this is identity blinding, not a guarantee that a reviewer cannot infer a method. Use a second reviewer if feasible; disclose a single-reviewer limitation otherwise.

Score correctness **0** (wrong/unsupported), **0.5** (partly correct/supported), **1** (correct, fully supported and appropriately qualified). Score citation support separately at 0/0.5/1 for how completely the cited excerpts support the answer. A justified abstention has no supporting-answer citations; use citation score 0 and record its success separately rather than rewarding empty citations. Mark `correct_abstention=true` for a justified corpus-scoped abstention, `false` for invented answers to corpus-unanswerable questions or unjustified abstention on answerable questions, and leave blank when no abstention judgment is applicable. A retrieval miss does not make an answerable question corpus-unanswerable. Record reviewer, timezone-aware date and reasons; keep scores blind until sealed.

Report evidence recall separately (unanswerable N/A), correctness/citation distributions, abstention outcomes and paired wins/ties/losses over the same questions. Group by **requested condition** while retaining effective mode/fallback for disclosure. No automatic LLM judge or agent-authored human scores. Rehearsal fixture scores are explicitly synthetic and never enter scientific results. Failures/missing runs must be reported; the current exporter refuses to silently score an incomplete matrix.

## Remaining freeze requirements

M4.2 must complete MPNet's distinct 768-D vector-only condition, the expanded-corpus restore check, all frozen hashes/settings/prompts, final run bounds and explicit authorization. Existing MiniLM parameters and development scores remain unchanged. The exhausted M3.3 OpenAI probe allowance grants no M4 spending. Local Qwen remains the selected generator unless the user explicitly changes it.
