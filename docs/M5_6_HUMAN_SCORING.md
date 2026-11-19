# M5.6 human answer scoring

**Completed:** all 288 submitted human rows have been sealed and aggregate conditions revealed. Do not repeat scoring/seal/reveal or edit the sealed scores. See [final results](M5_6_EVALUATION_REPORT.md). The instructions below describe the completed workflow.

This guide contains no private questions, answers, scores or condition mapping. The frozen run has completed; use the packet linked below. Source-annotation approvals are separate from these new answer-quality ratings.

1. Open [anonymous answers](C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1/matched-executions/a31d5335a3ea4d7e829607a42ded8a3d/b379233668ed4804b764d3ee057aee05/blind/public/answers.json) and [blank scores](C:/Users/serge/DBU-GraphRAG-Evaluation/retrieval-v2-fresh-v1/matched-executions/a31d5335a3ea4d7e829607a42ded8a3d/b379233668ed4804b764d3ee057aee05/blind/public/scores.csv) in the returned `blind/public` packet: `answers.json` contains anonymous questions, answers and cited source quotations; `scores.csv` is the blank form.
2. Make a **new copy** of `scores.csv` named `scores-completed.csv` **inside that same packet directory**. Preserve original files. Keep the exact header/order and every `answer_id` unchanged, with one row per anonymous answer. Do not open the private reveal mapping or seek mode labels before scoring is sealed.
3. Match each form row to its `answer_id` in `answers.json`. Judge each answer against the registered source scope, your reference annotations and the displayed quotations. Do not substitute newer papers, omitted pages or incomparable experimental conditions.
4. Enter your actual judgments using the table below. Score all 288 answers; an agent must not fill scores for you. Optional notes can remain blank. If you cannot judge an answer, leave it unresolved and ask for clarification rather than guess; an incomplete form cannot be sealed.
5. Use your real reviewer identity and timezone-aware `scored_at` recording timestamp. Preserve truthful supplied times; do not invent per-answer review durations. A batch recording timestamp is distinct from granular review time. Report active total review minutes separately, or say “not measured.”
6. Save the completed copy as CSV while retaining all seven columns. Treat `answer_id` and timestamps as text; do not let spreadsheet formatting truncate or rewrite them.
7. Send the completed file's path. The authorized runner validates the complete form and immutable answer bindings, seals the actual human rows, and only then permits condition reveal. Do not edit scores after seeing condition results; later corrections require a disclosed amendment.

| CSV column | What to enter |
|---|---|
| `answer_id` | Keep the original opaque identifier exactly. |
| `correctness` | `0` wrong, `0.5` partial, `1` correct and fully supported. Proper qualifications may earn full credit. |
| `citation_support` | `0` unsupported/no citations, `0.5` partially supported, `1` main factual assertions supported by the provided cited quotations. A well-formed citation ID alone is not support. |
| `correct_abstention` | `true` for justified abstention on a corpus-unanswerable question; `false` for an incorrect abstention judgment, including an invented answer to an unanswerable question or a retrieval miss on an answerable question; blank where N/A. Distinguish corpus answerability from a retriever's missing evidence. |
| `reviewer` | Your real reviewer name. |
| `scored_at` | Actual decision/recording date-time including a timezone (`Z` or an explicit UTC offset). |
| `notes` | Optional rationale, uncertainty or qualification; retain the column even when blank. |

A correct no-citation abstention may receive full correctness and a true abstention judgment while receiving zero citation-support credit; these are separate dimensions. Keep negative and partial ratings when warranted. Scores are ratings, not accuracy percentages, and should not be changed to favor Graph or any other condition.

The form's exact columns are `answer_id,correctness,citation_support,correct_abstention,reviewer,scored_at,notes`. No scores or timestamps have been prefilled by this guide.
