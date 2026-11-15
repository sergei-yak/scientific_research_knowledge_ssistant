# Blind answer scoring

Score the anonymous answer packet locally in the external evaluator directory. Do not attach/paste questions, answers, packets, completed forms or reveal mappings into development chat. All 96 answers require real human scores before the runner reveals conditions. The earlier gold-annotation approvals do not score these generated answers.

For each answer, read the question, answer and cited source quotations. Check whether the answer addresses all requested parts, preserves attribution/conditions and avoids invented measurements. Use the indexed-corpus scope; a missing retrieved passage does not make an answerable question unanswerable. Do not infer a method from answer style or open the reveal map. If more source checking is needed, use the private review/source materials locally and record uncertainty in notes.

| Field | Human decision |
|---|---|
| `correctness` | `0`: wrong/unsupported; `0.5`: partly correct/supported; `1`: correct, fully supported and appropriately qualified. A justified corpus-scoped abstention can receive 1. |
| `citation_support` | Independently use `0`, `0.5`, or `1` for how completely the cited excerpts support the answer. A justified abstention without supporting-answer citations receives 0 here; its success is recorded separately. |
| `correct_abstention` | `true`: justified abstention for a corpus-unanswerable question. `false`: invented answer to an unanswerable question, or unjustified abstention on an answerable question. Blank: no abstention judgment applies. |
| `reviewer` | Your name. Use a second reviewer if feasible; otherwise disclose the single-reviewer limitation. |
| `scored_at` | Actual timezone-aware scoring timestamp, e.g. `2026-11-14T19:30:00-06:00`. Do not invent a review date/time. |
| `notes` | Short explanation, including any partial support, missing part, qualification or uncertainty. |

Keep the exact seven-column CSV order: `answer_id,correctness,citation_support,correct_abstention,reviewer,scored_at,notes`. Preserve every original anonymous answer ID, one row per answer; do not infer scores for unseen answers, omit difficult rows or prefill judgments. Work in manageable batches and retain the original blank form. Save the completed form inside the same private execution directory, preferably under a new filename such as `scores-completed.csv`.

The local `score-review.html` displays eight answers/page and saves drafts for that exact packet. Its three judgment controls start unset; choose N/A explicitly when an abstention judgment does not apply. Reviewer identity can be prefilled, but scores/timestamps are created only through your edits. Keep draft backups if reviewing across sessions. Completed export is enabled only after all answers have manual judgments and notes; its downloaded CSV name includes the packet fingerprint. Save/move that file beside the HTML inside the external execution directory, preserving the original `scores.csv`. Exact paths are in `runs/m4-3/blind-scoring-handoff-20261115T015647005058Z.json`.

When the whole form is complete, tell the agent only its local filename/path and that human scoring is complete. The guarded runner validates IDs/fields/timestamps and seals the full form before it reads the reveal map. Only aggregate results return to development; both development and held-out partitions are reported separately. Any newly proposed equivalent evidence requires a disclosed, versioned human adjudication across all modes, preserving the original frozen score.
