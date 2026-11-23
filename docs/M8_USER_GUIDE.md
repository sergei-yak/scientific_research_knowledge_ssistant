# Use your own research papers

M8 is the local first release for user-provided documents. Start it from `C:/Users/serge/DBU-GraphRAG-Worktrees/m8-user-collections` with `START_M8.ps1`, then open **http://127.0.0.1:8504/**. The preserved class demo remains on port 8503. See [verification and limits](M8_5_REPORT.md).

## 1. Create a collection and add papers

Enter a collection name in the sidebar and choose **Create collection**. Under **Add papers**, upload text-based PDFs or paste public PDF/arXiv links, one per line. Choose **Import documents** and wait for the ready message. **Papers and indexed coverage** shows how many pages were readable and indexed.

Use a separate collection for a different topic. The app searches only the selected collection. Switching collections clears the previous answer. Adding papers creates a new collection revision; previously reviewed claims do not automatically approve that new revision.

The first release allows up to 10 unique papers per collection, 25 MiB/100 pages per PDF, and 100 MiB/300 pages/3,000 passages per collection. Import one batch at a time. Re-uploading identical bytes reports a duplicate without creating another revision. An unreadable PDF produces an error; existing valid papers remain available. **Import history** retains processing details, including failures. Do not remove locks or history to retry interrupted work.

Supported links are HTTPS arXiv abstract/PDF URLs and direct public PDF URLs. Login-only pages, paywalls, arbitrary webpages, crawling, scanned-PDF OCR, encrypted PDFs and non-PDF files are outside this release.

## 2. Ask a question

Select a ready collection, enter a question, and choose a retrieval mode:

| Mode | What you receive | Needs claim review? |
|---|---|---|
| Vector | Passages with similar meaning | No |
| Hybrid | Passages found through meaning and keywords; a useful starting point | No |
| Hybrid + Approved Facts | Passage search plus claims you have checked against their sources | Yes, with a current reviewed index |
| Graph | The approved-fact search plus evidence reached through reviewed connections | Yes, with a current reviewed index |

Leave **Generate an answer** unchecked to inspect evidence only. Check it to ask the configured local Qwen model to write a cited answer, then click **Ask question**. Local answers can take a minute or more; evidence-only search also includes source/index checks and model loading. Submit once and wait. Downloads and ordinary page reruns reuse the saved result.

The app can say that the evidence is insufficient. A relevant-looking passage or valid citation does not guarantee a correct answer. Check the source before relying on a claim. Tables, figures and equations are not independently validated.

## 3. Understand the sources and connections

**Source excerpts** are the actual PDF passages provided to the model. Each E-label identifies an evidence item; its card shows the paper, PDF page, quotation, original input reference and a checked PDF download. These let you inspect what supports the answer.

**Approved claims** are source-bound statements that a real person has reviewed. Approval means the paper supports that statement; it does not independently prove the science. **Graph connections** show reviewed links used to reach additional evidence, such as a method connected to a shared benchmark and another paper. Merely importing PDFs does not create approved connections.

If Graph finds no new eligible evidence, the app visibly switches to **Hybrid + Approved Facts** and gives the reason. This is expected for collections whose approved claims have no useful connections. It is not evidence of a Graph quality improvement. Missing indexes, stale reviews or service errors remain errors.

## 4. Optionally review claims

Ordinary Vector/Hybrid QA works without this step. To enable reviewed modes, expand **Review claims and connections**. Select a passage and explicitly request a local draft, or supply a manual proposal. Inspect the complete claim, exact quotations, source spans and any proposed method/dataset identities or connections. Correct an inaccurate proposal before reviewing its new revision.

Enter your reviewer identity, choose **approve**, **reject** or **needs_review**, give your reason, and confirm the displayed review scope. Enter review time only if measured. Save your decision, then choose **Update reviewed index**. Reviewed modes become available only if current source-valid approvals and the live index match. A changed claim/source/mapping or revoked decision requires review/publication again; the app blocks stale reviewed results.

Drafts are never approved automatically. Each PDF retains cumulative extraction limits across collections: eight requests/eight passages/twelve generated-or-unknown candidates, at most two candidates per request. Failed and interrupted attempts count. No paid extraction is enabled.

## 5. Explore the collection graph

Select a ready collection and tick **Show collection graph**. This opens the map independently of a question and makes no AI/model call. You can inspect document structure even before reviewing claims.

- The **overview** shows the collection, papers and current published approved claims/entities. Passages and derived search records are hidden for readability, with exact visible/total counts.
- Tick **Full graph (include passages and search records)** to see every current logical node and edge. Dense maps are easier to explore by zooming and selecting a node.
- Use **+**, **−**, the mouse wheel or **Fit graph**. Drag the background to pan, or drag a node to rearrange it. These movements affect only the display.
- Click a node, use **Find a node**, or choose it from **Select a node**. The detail panel shows its full statement, source quotations and PDF pages. Click a relationship to inspect its direction and meaning. Nodes/relationships also support keyboard selection.
- **Download current graph JSON** saves the complete validated map. Use **Graph source PDF** to select and download an original checked paper.

Colors distinguish papers, passages, findings/evaluations, methods, datasets and search records. A paper-to-passage link means document ownership, not a scientific finding. Dotted **mentions** links remain discovery-only. A reviewed claim means the paper supports its wording, not independently verified scientific truth.

This is the selected collection's current logical source/review map, not a raw database administration view. Old revisions, rejected/pending claims, unrelated collections and administrative records are excluded. Missing method/dataset mappings remain absent. Stale published approvals, changed sources or unavailable indexes block the reviewed view rather than displaying old claims. The AI demo currently has5 overview nodes/4 edges, or639 nodes/642 edges with passages/search records. Its two approved claims have no named method/dataset mappings. Physics has2 overview nodes/1 edge, or150 nodes/149 edges, with no approved claims. These counts describe current examples, not a Graph retrieval-quality result.

## 6. Save or demonstrate a result

Use **Download evidence CSV** for evidence rows and **Download run JSON** for the full saved answer, source/mode bindings and diagnostics. Source-card PDF downloads return the checked original bytes. Exports are revalidated against the selected collection and current reviews.

Two existing examples are ready locally:

- **Research papers demo:** ask “What are positional encodings used for in the Transformer?” Two genuine approvals are published. All four modes are available; Graph currently falls back because these claims create no cross-paper connections.
- **Gravitational-wave research:** ask “What physical event produced the gravitational-wave signal described in this paper, and which observatory detected it?” Vector/Hybrid work over the imported physics paper. Fact/Graph remain unavailable until that collection has its own reviewed claims.

These are functional examples, not a quality benchmark. No training or new research evaluation is needed to try another supported topic. The app is a local single-user product; it has no cloud accounts or shared-user access control. A fresh machine still needs the locked environment, local model assets, owned database and source/index data described in the setup reports; Git intentionally excludes these assets and secrets.
