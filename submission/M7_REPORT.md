# M7 - Final submission preparation

**Current presentation update:** The later user-requested revision adds an early RAG comparison and simple storytelling speech for all eleven slides. See [revision checks](M7_PRESENTATION_REVISION.md) and [current guide](START_HERE.md). The original completion record below describes the preserved ten-slide v1 package. The ten-page report/results and all frozen studies are unchanged.

Completed 2026-11-19. The user requested M7 and approved the concise defaults: approximately 8-10 report pages and ten slides. This milestone consolidates completed work; it does not change an application, model, algorithm, score, study freeze or approval. The actual course rubric/template/time limit was not supplied. Package preparation is complete; course submission is not performed.

## Tasks and deliverables

| Task | Actual outcome |
|---|---|
| M7.1 report | Ten-page PDF plus editable Markdown covering the problem, pretrained neural components, source/review architecture, controlled modes, both study designs/results, limitations and working product. Ten research/model references and five project-evidence groups. Tables reconcile to saved public aggregates; separate held-out samples are never treated as an across-study improvement. |
| M7.2 presentation | Ten editable slides authored in Artifact Session, exported to PowerPoint with five native tables, two native charts and ten source-bearing speaker notes. Readable presentation notes include public demo steps, suggested pacing and likely questions. Actual M6 screenshot is embedded, not an external link. |
| M7.3 package | Complete submission ZIP, exact tested M6 source ZIP (197 tracked files, commit 9b9b6c884d5616d044bbf3e0d98344e43ec91635), public aggregate JSONs/source reports, actual demo screenshots, figures, checklist and file-hash manifest. Private evaluation rows/questions/answers/gold/maps, credentials, downloaded papers, model weights, caches and volumes are excluded. |
| M7.4 verification/handoff | Sixteen public content/preservation groups pass; all ten report pages and ten exact re-imported exported slides inspected individually. Final presentation package/layout/import/portable-workbook checks pass with zero layout findings or warnings. ZIP contents and hashes are checked separately. Public artifacts/navigation are mirrored to the original project; retained M5 code stays unchanged. |

See [submission guide](START_HERE.md), [report source](Project_Report.md), [presentation/demo notes](Presentation_Notes.md) and [checklist](Submission_Checklist.md). Artifacts are under ignored `runs/m7/`; build intermediates are separate from `submission/`. Final bundle: `runs/m7/DBU_Deep_Learning_Submission.zip`.

## Scientific and product claims

The original study's held-out Hybrid mean correctness is 0.71875. The exploratory A2 Hybrid/Facts/Graph mean is 0.8125; primary Graph/Facts paired correctness is 0/16/0, with 16/16 held-out Graph fallbacks in every arm. Different held-out questions prohibit an across-study gain claim. Tables/figures use public means of 0/0.5/1 human ratings, not accuracy percentages. Recall averages over twelve answerable held-out questions and is N/A for unanswerable items.

The report retains the negative development gate, accepted author-outcome exposure, small purposive sets, one rater, incomplete coverage, cache/timing limits and unknown follow-up provider-response totals. No new private details or distributions are inferred. It explicitly states that all neural weights were pretrained and no network was trained/fine-tuned. Any class model-training requirement remains a rubric question for Sergei, not an invented completed task.

The existing Standard product remains at localhost 8503 in the M6 checkout, with either named corpus, all four modes and explicit opt-in local synthesis. The retained V2 research scope is not newly provisioned for ordinary product generation. M6's actual 374 offline passes/twelve service cases/two browser queries and 7/8 bounded local model attempts remain historical M6 evidence, not M7 reruns. Source cards, approved claims and selected graph connections remain distinct; the script explains fallback without pretending a graph path was selected.

## Actual checks and preservation

`runs/m7/content-validation-v1.json` records sixteen passed groups: report length/nonempty pages,64 result-table numeric cells, sixteen rendered PDF result rows, slide/table counts, twelve exact native chart values, nine primary-slide numeric values, ten retained speaker notes, exact embedded screenshot bytes/no external image link, finalizer/import/workbooks, paired contrasts, two exact public aggregate copies,118+208 frozen files,197-file exact source inventory/exclusions, unchanged runtime/retained M5 tree, references/disclosures/placeholders, and ten re-imported slide renders. Visual inspection is an agent authoring check, not human scientific approval.

The finalizer passes OOXML structure, ten-slide geometry, chosen Arial encodings, five native table owners, native chart values/workbook references and first-party re-import. Literal chart workbooks are deliberately new snapshots of the complete public chart values; no source formulas are claimed. This does not establish native PowerPoint/projector behavior. Archive verification checks byte inventory, nested source ZIP and manifest hashes; a final additive receipt records package/copy identities.

No application/interface/dependency edits occurred, so no application tests, browser query, service fixture or provider call were repeated. Both freeze JSON hashes and all 118 original / 208 follow-up assets still match. No used target was started, no data restored/reset, no paid ledger touched and no private filesystem accessed. Model/data assets remain in their original locations.

## Resolved authoring issues and skips

The bundled authoring Python lacked Matplotlib and PyMuPDF; the report uses available ReportLab charts and bundled Poppler rendering instead, without changing project dependencies. The initial layout overflowed to thirteen pages; compact table padding and shorter text produced ten reviewed pages. The live presentation API did not provide the expected local PPTX blob; the live model was exported through the documented serialization/local file adapter. Required table-policy/runtime settings and a receipt-name conflict were corrected before final validation. Earlier drafts/failed attempts remain in the ignored build directory.

Critically, a first standalone deck lost its session-managed screenshot on re-import. The final export reattaches the exact unchanged public image bytes. Re-imported final slide 9 and an exact embedded-image hash check now pass. Two overlapping chart-title text frames were shortened; the final layout has zero warnings. Initial aggregate staging files had equivalent JSON with different formatting; final evidence copies use the original exact bytes. No scientific value changed.

Skipped/pending: native Microsoft PowerPoint and projector rehearsal; a new clean-machine runtime/data setup; course rubric/format/AI disclosure/time-limit checks; actual course-portal upload. These are explicit checklist items, not claimed passes. No video, hosted deployment or DOCX was required by the approved defaults; deliverables are PDF/Markdown and editable PPTX. M7 has no remaining authoring blocker. Sergei should review the package, check the actual rubric, rehearse and submit through the course portal.
