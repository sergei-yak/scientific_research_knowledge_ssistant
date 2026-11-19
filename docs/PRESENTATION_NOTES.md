# Presentation and demonstration notes

Sergei Iakovlev | DBU Deep Learning | 19 November 2026

Suggested pacing is about eight minutes for the ten slides plus three to five minutes for the demonstration. This is a rehearsal suggestion, not a course time limit or a measured rehearsal. Full references and both result tables are in the report.

## Slide 1 - Scientific Research Knowledge Assistant

I built a local assistant for reading scientific papers and checking the evidence behind its answers. The research question is whether graph traversal improves retrieval and answers over carefully matched alternatives. The product works, but the experiments did not show a held-out traversal benefit. Those two outcomes should be assessed separately.

The implementation takes ideas from GraphRAG research; it is not a reproduction of the full Microsoft GraphRAG or HippoRAG architecture. Source: `project_spec.md`; report introduction.

## Slide 2 - Does graph traversal add useful evidence?

Vector retrieves semantically similar chunks. Hybrid combines semantic and lexical search. Hybrid + Facts adds searchable human-approved claims. Graph starts from that same pool and can add evidence through reviewed relationships. The key comparison is Graph versus Hybrid + Facts, because it controls for the benefit of having approved claims available at all.

Each mode uses at most six evidence units and 1,800 estimated tokens. If no new graph evidence survives selection, the Graph request returns the exact matching fact-augmented context and reports fallback. That is a defined behavior, not a hidden algorithm switch. Source: `project_spec.md`, sections 3-4; `docs/M3_1_REPORT.md`.

## Slide 3 - Pretrained neural models power the pipeline

The bi-encoder independently embeds questions and passages, allowing passage vectors to be precomputed. MiniLM produces 384 dimensions; MPNet produces 768 in the separate vector-only comparison. The cross-encoder processes a question/evidence pair jointly and returns a relevance logit. It can capture interactions that independent embeddings lose, but it needs more per-query inference.

The selected reranker runs on CPU in float32, with a 512-token native pair limit and at most 88 candidates. The local generator uses the recorded 27.3B Q4_K_M asset with 4,096 context and 512 output tokens. Its installed alias is `qwen3.8:latest`; that local label is not a verified official release name. No network was trained or fine-tuned. The deep learning work is pretrained inference, retrieval/ranking design and evaluation.

Sources: [Sentence-BERT](https://arxiv.org/abs/1908.10084); [MiniLM](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2); [MPNet](https://huggingface.co/sentence-transformers/all-mpnet-base-v2); [reranker](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2); pinned project manifests.

## Slide 4 - A small, source-bound scientific knowledge graph

The five-paper acceptance gate came before expansion to twenty papers, 1,427 indexed chunks and 51 approved claims: 23 pilot plus 28 expansion claims. Preparation retains the paper version, page and source offsets. Human review binds a decision to an exact claim, source and entity revision. Retrieval checks current approval state rather than trusting a stale cached label.

The Python services own retrieval, evidence validation and generation. CLI and Streamlit call the same pipeline. Unknown experimental conditions stay unknown. A shared benchmark name does not establish matching versions, splits or protocols. Approval means that the source supports the claim, not that its experiment has been independently replicated. Sources: `project_spec.md`; `docs/M4_1_REPORT.md`; `docs/M5_1_REPORT.md`.

## Slide 5 - Two frozen studies, two held-out samples

Each study uses eight development and sixteen held-out questions, stratified into direct, cross-paper, multi-hop and unanswerable categories. The original study has four modes and 96 answer slots, plus 48 encoder-only retrieval reads. The follow-up has three arms across four modes and 288 answer slots. Human scores were sealed before condition reveal; each answer-scoring stage took about sixty active minutes from one human.

Correctness is a mean rating on 0, 0.5 and 1, not an accuracy percentage. Recall measures registered gold facts in the actual assembled source evidence and averages over the twelve answerable held-out questions; unanswerable recall is N/A. The follow-up author received prior outcome summaries, and the study continued after a negative development gate with explicit disclosure. It is exploratory. The different held-out questions do not support an across-study improvement claim. Sources: both evaluation reports; `docs/M5_5_STUDY_AMENDMENT.md`.

## Slide 6 - Original study: Hybrid leads this held-out sample

On the original held-out sample, Hybrid has mean correctness 0.71875 versus Vector 0.53125, with six paired wins, nine ties and one loss. Facts and Graph both score 0.5625. All sixteen held-out Graph requests fall back; all twenty-four Graph requests overall have the same contexts as their matched fact ablation. There is no demonstrated selected-traversal contribution.

The separate encoder comparison has held-out recall 0.1528 for MiniLM and 0.2083 for MPNet, with medians approximately 151 and 386 milliseconds. Development recall favors MiniLM and pooled recall ties. The common 0.30 threshold may be differently calibrated, so these data do not justify an unconditional MPNet upgrade. Source: `evidence/baseline-aggregates.json`; `docs/FINAL_EVALUATION_REPORT.md`.

## Slide 7 - Follow-up: reranking has mode-dependent trade-offs

A0 is the reference implementation. A1 broadens graph routes with the reference selector. A2 uses broader routes plus one shared cross-encoder across every mode. A0 and A1 have identical held-out quality metrics. A2 raises Hybrid correctness from 0.7500 to 0.8125 and Facts from 0.6875 to 0.8125, while Vector falls from 0.71875 to 0.65625.

The paired A2/A1 counts are Vector 0/14/2, Hybrid 3/12/1 and Facts/Graph 4/12/0. These are end-to-end policy trade-offs: reranking can change anchors and final selection. All held-out Graph requests still fall back, so the observed gains are not traversal gains. Keep the small sample and author-exposure limitation in view. Source: `evidence/followup-aggregates.json`; `docs/M5_6_EVALUATION_REPORT.md`.

## Slide 8 - Primary contrast: no held-out traversal benefit

The primary A2 Graph versus A2 Facts comparison has zero correctness wins, sixteen ties and zero losses. Both have correctness 0.8125, citation support 0.6250 and recall 0.4861. Reranked Hybrid reaches the same quality metrics with lower observed retrieval latency, about 507 milliseconds versus 922 for Facts and 998 for Graph.

Those medians include integrity checks and selector work but exclude generation. They are not cold-start speed guarantees. No new graph evidence reached generation on the held-out sample, so the study cannot estimate the benefit of selected graph evidence. Sparse reviewed links and low-ranked new candidates help explain the negative development result. Synthetic positive-path tests show capability, not real-corpus quality. Sources: follow-up aggregate/report; `docs/M5_1_REPORT.md`; `docs/M5_4_REPORT.md`.

## Slide 9 - A working product with inspectable evidence

The actual M6 screenshot shows the public LightRAG demonstration in Standard/Hybrid over the twenty-paper corpus. The generated answer took about 42 seconds and its cited excerpts were checked on PDF page 4. Normal answers in the service checks took 35-76 seconds; initial loading can add time.

Users can inspect exact excerpts, reviewed claims and selected graph connections, and download CSV or JSON without generating again. Raw excerpts are not approved claims, and a valid citation does not certify every generated sentence. The current demo uses Standard modes; the retained V2 research scope is separate and is not enabled for ordinary product synthesis. M6 recorded 374 offline passes, twelve service checks, two browser queries and an exact six-row CSV match, with seven integration cases deselected. Sources: `docs/M6_REPORT.md`; `docs/M6_DEMO_GUIDE.md`; actual M6 screenshot.

## Slide 10 - Evidence first; report the negative Graph result

The working product provides local QA with traceable sources and explicit fallback. The research result is no held-out traversal benefit and a mode-dependent reranker quality/latency trade-off. The main limits are small purposive samples, one rater, incomplete source coverage and follow-up question-author exposure.

Future research could enrich reviewed cross-paper chains and use independent raters and a fresh evaluation authored without outcome exposure. That is proposed work, not a completed experiment or a reason to rerun the used tests. AI assistance supported system building and documentation; human source review and ratings remained separately recorded. Full citations and provenance are in the report.

## Live demonstration - three to five minutes

Use the prepared M6 checkout and its existing local data. Follow `M6_DEMO_GUIDE.md` for startup. These steps are for Sergei's deliberate presentation; M7 did not execute new queries or rehearse them.

1. Open `http://127.0.0.1:8503/`. Choose **Twenty-paper research corpus / Standard / Ask / Hybrid**.
2. Enter `What do LightRAG low-level and high-level retrieval strategies retrieve?` Enable **Generate an answer with the configured model** and submit once. Allow about a minute; explain bi-encoder versus cross-encoder while it runs. Initial loading can take longer.
3. Read the answer. Open its actual cited source cards and PDF page links. Explain low-level entities/relationships versus high-level themes. Use the labels displayed by this run; E5/E6 were the recorded example, not a fixed future guarantee.
4. Download evidence CSV or run JSON. Explain that expanding/downloading uses saved evidence without another generation.
5. For a brief second view, turn synthesis off, choose **Comparison / Hybrid + Approved Facts**, and use its supplied public prompt. Point out known/unknown evaluation conditions and the no-controlled-ranking notice.
6. If time permits, use **Graph RAG** with synthesis off and a public guide prompt. Show requested/effective mode and any fallback. Do not imply a graph route was used if none was selected.

If services fail during presentation, show the included **actual M6 screenshots** and label them as a previously recorded working example. Do not describe a screenshot as a new live success. Do not restart an evaluation target, delete volumes, re-ingest the corpus or rerun the readiness harness to repair a demo. Extra generated examples take extra time; avoid repeated submissions while one is running.

## Likely questions

| Question | Short answer |
|---|---|
| Why use Graph RAG if it did not win? | The project tested that hypothesis under controlled evidence access; reporting a negative result is a valid contribution. |
| Where is the deep learning? | Transformer embeddings, joint neural reranking and quantized local generation; all weights were pretrained externally. |
| Did you train a model? | No. This is an inference/system evaluation project. Confirm separately that this meets the course's training requirements. |
| Is 0.8125 equal to 81.25% accuracy? | No. It is a mean human rating on a 0/0.5/1 rubric, including unanswerable questions. |
| Is the second study an improvement over the first? | Their different held-out questions prevent that comparison; compare matched conditions within each study. |
| Why not just change papers until Graph wins? | That would bias selection. A changed corpus needs a new, prospectively specified study. |
| Can a citation still be wrong? | Yes. IDs/provenance can be valid while synthesis overstates the quoted evidence. Inspect the excerpt. |
| Can another machine run this ZIP immediately? | It contains locked source, not model weights, PDFs, reviewed data or database volumes. Setup and asset provisioning are still required. |
