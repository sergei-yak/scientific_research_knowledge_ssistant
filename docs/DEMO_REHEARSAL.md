# Presentation and demonstration rehearsal

Use the **v3 eleven-slide deck** and [matching simple speech](PRESENTATION_SPEECH.md). The working product is M8 at **http://127.0.0.1:8504/**; launch `START_M8.ps1` from the M8 checkout if needed. Follow [the user guide](M8_USER_GUIDE.md). The preserved M6 demo is optional historical material.

## Suggested running order

| Segment | What to explain | Planning allowance |
|---|---|---:|
| Slides 1-2 | A research team's problem; passage search versus reviewed connections | 2 minutes |
| Slides 3-6 | Fair comparison, pretrained AI roles, reviewed research corpus and evaluation limits | 4 minutes |
| Slides 7-9 | What the studies found; a reviewer rating is not an accuracy percentage | 3 minutes |
| Slide 10 + app | Bring your own papers; inspect evidence and export it | 3-5 minutes |
| Slide 11 | Intended business value, limits and possible future research | 1 minute |

These are estimates, not a measured spoken rehearsal or a course time limit. The script has approximately 1,270 spoken words. Shorten model-name explanations first if your actual limit is lower. Keep the negative Graph result, exploratory limitation and no-training disclosure.

## App demonstration after slide 10

1. Show **Add papers** and explain that a user can upload a text-based PDF or paste a supported public PDF/arXiv link. Existing collections avoid spending presentation time downloading/indexing another copy. Do not claim a fresh import if you only show the controls.
2. Select **Research papers demo**. Ask `What are positional encodings used for in the Transformer?` Choose **Hybrid** for ordinary search or **Hybrid + Approved Facts** for the two already-reviewed claims. Leave **Generate an answer** off for the shortest predictable live path. Submit once and wait.
3. Open a source card. Say: “This is the original wording and PDF page, so I can check the answer.” Explain that a reviewed claim records source support, not independent scientific proof. Download evidence CSV or run JSON.
4. Switch to **Gravitational-wave research**. The previous answer clears. Ask `What physical event produced the gravitational-wave signal described in this paper, and which observatory detected it?` Use **Hybrid**. This shows a different topic with its own sources and no borrowed AI approvals.
5. If demonstrating generation, explicitly enable it for one question and allow a minute or more. The M8.5 recorded physics answer is included as a fallback; label it as previously recorded. The delivery rehearsal itself used evidence only and made no new generator call.
6. Explain optional **Review claims and connections** and **Update reviewed index**. Do not create or approve new claims during the talk merely to enable a mode. The current AI Graph result has an explicit fallback because these claims create no cross-paper connections; physics fact/Graph remain unavailable without its own review.
7. Return to slide 11: “The workflow works on user-provided papers. Better graph answers and business time savings still need separate evidence.”

## Technical rehearsal actually performed

- Opened the final v3 file in Microsoft PowerPoint. It reports eleven slides with notes. Slide-show mode was started; the early RAG comparison, closing slide and M8 demonstration slide were visually checked. The deck remains open in normal view at slide 10. This is a native compatibility/screen check, not a timed spoken or projector rehearsal.
- In the actual app, inspected the existing reviewed AI result and exact PDF-page-6 quotations, downloaded its CSV, switched collections and verified the old result cleared, then submitted one new physics Hybrid evidence-only query. Six units/1,715 estimated tokens and PDF-page-1 support were displayed; run JSON downloaded successfully. No inference for answer generation, extraction, import or new human decision occurred.
- Both direct product examples remain separate from the frozen scientific studies. Do not rerun engineering/evaluation harnesses or reset data to prepare a presentation.

## Your final practice

- Read the speech aloud once in Presenter View and measure your real duration.
- Practice switching between slide 10 and the browser; check the actual projector/display scaling and network/service availability.
- If an answer is unsupported, show the evidence/abstention honestly. If services fail, use the included recorded screenshots and say they are recorded.
- Check the instructor's rubric, permitted AI-assistance disclosure, required files and any neural-training requirement. Upload only the requested materials and retain the portal receipt.
