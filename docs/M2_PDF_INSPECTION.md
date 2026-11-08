# M2.1 PDF inspection and coverage

Inspected locally on 2026-11-07. PDF hashes/rights/exact selected pages are in
`manifests/pilot-five-papers.json`; extraction anchors/limits are in `manifests/pilot-extraction.json`.
Rendered PNGs are ignored under `runs/m2/inspection/<arxiv-version>/page-<n>.png`.
This checks feasibility and selected prose, not every page or scientific correctness.

| Paper | PDF pages / retrieval coverage | Visually inspected pages | Findings and omissions |
|---|---|---|---|
| Survey, 2501.00309v2 | 88 / 1–52 | 1, 5, 50, 51; M1 also inspected 3 | Readable single-column prose, framework definitions and challenges. Page 53's remaining discussion and references are omitted. Framework extraction passage is partial; no claim is forced when the model returns empty. |
| GraphRAG, 2404.16130v1 | 15 / 1–11 | 1, 3, 6, 7, 11 | Single-column prose; method, two evaluation corpora, judge criteria and explicit limitations readable. Page 6 contains a table above the selected prose; the extraction anchor excludes that table. References start on 12. |
| HippoRAG, 2405.14831v1 | 28 / 1–10 | 1, 3, 5, 6, 9, 10 | Single-column prose and readable experimental setup. Flattened result tables on 5–6 are not numerically verified or used for result-value extraction. Limitations continue from 9 onto 10; page 10 also starts references, excluded from the selected extraction paragraph. Later references/appendices omitted. |
| LightRAG, 2410.05779v1 | 16 / 1–10 | 1, 3, 4, 5, 10 | Prose, dual-level retrieval and dataset-description paragraphs are readable. Figure 1's illustrative beekeeper entities are not scientific methods/datasets. Bibliography/appendices on 11–16 omitted. No dedicated limitations claim is invented. |
| HippoRAG 2, 2502.14802v1 | 18 / 1–8 | 1, 3, 4, 5, 6, 8, 9 | Two columns; selected blocks were visually compared with their prose paragraphs. Block order across columns is not a logical whole-page reading order. Page 9 interleaves conclusion/references and is omitted, including the conclusion tail. Tables on 4/6/8 are not numerically verified. The selected multi-hop dataset paragraph on 6 ends during an LV-Eval sentence; its incomplete detail cannot support a complete LV-Eval claim. |

All selected retrieval pages produced text and zero Unicode replacement characters after the fixed
M1 normalization. This does not establish faithful equations, symbols, diagrams or table alignment.
Line-wrap hyphen artifacts and combining-accent artifacts remain; quotations must match the frozen
normalized text exactly and humans should compare the PDF before approving.

## Known section-label issue

The M1 heading heuristic recognizes the first four papers reasonably, but does not recognize
HippoRAG 2's trailing punctuation. Its stored section label remains **Front matter**, even for body
pages. This is a known inaccurate parser label, not a verified section title. Do not regenerate M1
sources or silently change offsets to fix it. Packets warn reviewers and show exact PDF pages and
normalized intervals. The visually identified sections for the selected HippoRAG 2 passages are:

- Page 4, Offline Indexing: section 3.1, Overview.
- Page 5, online retrieval summary: section 3.5, Online Retrieval.
- Page 6, multi-hop datasets: section 4.2, Datasets.
- Page 8, retriever flexibility: section 6.3, Dense Retriever Flexibility.

A later parser improvement needs a new source/chunk identity and renewed support validation; it
must not rewrite existing offsets or claim approvals. Current claim proposals are unapproved.

## Bibliographic uncertainty

Five bounded anonymous OpenAlex singleton requests matched all five works. Their metadata is
work-level: LightRAG's matched record is a 2025 conference publication, while this pilot reads its
2024 arXiv v1. HippoRAG also resolves to a proceedings DOI. The survey's OpenAlex year is 2024,
consistent with its initial submission date, despite the arXiv identifier/PDF version being 2025.
Keep these dates/DOIs separate from pinned PDF versions. Six positive metadata citation edges were
recorded; an absent edge remains unknown, including missing links caused by duplicate/merged works.
Metadata edges support discovery, not attribution or approval of a scientific claim.
