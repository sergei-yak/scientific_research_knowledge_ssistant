# Presentation rehearsal notes

The current deck has **11 slides**. Read [the simple storytelling speech](PRESENTATION_SPEECH.md). It contains the words to say for every slide, with the same headings as the PowerPoint. The same speech is embedded under **SPEECH** in each slide's speaker notes. **SOURCES AND PRESENTER NOTES** below it are reference material, not part of the spoken script.

The opening researcher/team is an imagined example. Intended business benefits are easier research and source checking. Time savings, financial return and real-user business impact have not been measured. The revised language keeps the negative Graph result, exploratory limits and no-training disclosure.

## Rehearsal flow

1. Slides 1-2 introduce the team's problem and explain traditional RAG versus Graph RAG with a library example. Both can use several documents; graph links are an additional retrieval option.
2. Slides 3-5 explain the fair comparison, three AI roles and small reviewed paper library. Explain the role of a tool instead of reading model names or dimensions aloud.
3. Slide 6 explains how the idea was tested. Slides 7-9 present the results. A score out of one is a reviewer rating, not an accuracy percentage.
4. Slide 10 introduces the working product. Pause here for the optional public demonstration below, then return to slide 11 for the business conclusion.

The script has approximately 1,250 spoken words. Plan roughly 10-12 minutes, plus 3-5 minutes for a demo, and measure your own rehearsal. No course time limit or native PowerPoint/projector rehearsal has been supplied/performed. If you need a shorter talk, preserve the research limitations while shortening model-detail explanations.

## Words in everyday language

| Term on a slide | Simple explanation |
|---|---|
| RAG | Look up source material before writing an answer |
| Graph | A map of recorded connections |
| Dataset | A collection of data or questions used to test a method |
| Hybrid | Search by meaning and matching words together |
| Reranker | Give the possible passages a closer relevance check |
| Held-out questions | Test questions kept separate from development |
| Fallback | The connection search added nothing to the final evidence, so the system used its matching simpler result |
| Evidence recall | How much of the required source support reached the answer writer |

## Short product demonstration after slide 10

Follow [the M6 startup guide](M6_DEMO_GUIDE.md). M7 presentation editing did not issue new queries or run a rehearsal.

1. Open `http://127.0.0.1:8503/`. Choose **Twenty-paper research corpus / Standard / Ask / Hybrid**.
2. Ask `What do LightRAG low-level and high-level retrieval strategies retrieve?` Enable **Generate an answer with the configured model** and submit once. Explain source checking while waiting. The recorded product checks took 35-76 seconds, with extra time possible for initial loading.
3. Read the answer and open its actual cited excerpts/PDF pages. Explain that a citation is a place to check the answer, not proof that every sentence is correct. Use the displayed labels, rather than assuming the saved example's E5/E6 labels will always recur.
4. Download evidence CSV or run JSON. Expanding/downloading the saved result does not generate a second answer.
5. If time permits, switch synthesis off and show a supplied public Comparison prompt with **Hybrid + Approved Facts**. Point out unknown conditions and the no-controlled-ranking notice. A Graph request may show explicit fallback; do not claim a path was selected if none was.
6. Return to slide 11. The demo is the Standard product. The experimental V2 synthesis scope remains separate.

If services fail during your presentation, use the included actual M6 screenshots and label them as a previously recorded example. Do not call them a fresh live success. Do not reset data, restart a consumed evaluation target or rerun readiness/study harnesses to repair a demo.

## Reference material

Full technical evidence and references remain in [the project report](PROJECT_REPORT.md), [original results](FINAL_EVALUATION_REPORT.md), [exploratory results](M5_6_EVALUATION_REPORT.md), [study amendment](M5_5_STUDY_AMENDMENT.md) and [product checks](M6_REPORT.md). Each exported slide keeps its own source notes below the spoken speech. Historical ten-slide technical notes remain in the original M7 package and commit f9b1ff4.
