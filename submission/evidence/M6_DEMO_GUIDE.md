# Demonstrating the Research Evidence Assistant

The working product is at **http://127.0.0.1:8503/**. It supports live local question answering over either the five-paper pilot or the twenty-paper corpus. Standard retrieval has all four modes; no new research study is needed to use it.

## Start and stop

Use the **demonstration checkout**, not either retained research checkout:

```powershell
cd C:\Users\serge\DBU-GraphRAG-Worktrees\m6-demonstration
.\START_DEMO.ps1
```

If PowerShell script execution is restricted, run the equivalent command from that same directory without changing the system policy:

```powershell
uv run --locked --offline python -m streamlit run src/research_assistant/ui/app.py --server.address 127.0.0.1 --server.port 8503 --server.headless true --browser.gatherUsageStats false
```

The launcher uses the locked environment, starts Streamlit on localhost port 8503, and leaves its console attached. Stop just this UI with **Ctrl+C** in that console. Existing paper/model caches, credentials and reviewed data are already present locally; `.env` stays out of Git. No dependency or model upgrade is needed. Final `uv sync --locked --offline` passes on this machine. For a fresh machine, follow the main setup prerequisites; this checkout alone does not contain ignored PDFs/models/data.

The working Neo4j container and Ollama must be running. Check without resetting data:

```powershell
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'
ollama list
```

If the **existing working** database is stopped, start only that retained container:

```powershell
docker start dbu-research-assistant-neo4j-1
```

Ollama should serve the installed `qwen3.8:latest` model on localhost 11434. Do not start a second server if it is already running. Never delete volumes, re-ingest papers, rebuild indexes or start either used evaluation target for a demonstration. Port8502 is the retained experimental research UI; **8503 is the product demo**.

## First live answer

1. Open port 8503. Choose **Twenty-paper research corpus**, **Standard**, **Ask**, and **Hybrid**.
2. Enter: `What do LightRAG low-level and high-level retrieval strategies retrieve?`
3. Check **Generate an answer with the configured model**, then click **Run research query** once.
4. Wait for the answer. In the observed browser run it took about 42 seconds; the service checks took 35-76 seconds per answer. Initial Python/encoder/model loading can add time. The request timeout is 180 seconds; a failure is shown and saved, with no automatic retry/provider switch.
5. Read the answer, then open the cited **E5/E6** source cards. Both point to PDF p.4 and contain the exact low/high-level descriptions. Future ranking can vary, so use the citation labels actually displayed rather than assume E5/E6 permanently.
6. Download the checked evidence CSV or full run JSON. Expanding cards, rerunning the page and downloading revalidate saved evidence without generating a second answer. A full browser refresh/new session may lose the displayed session result; files remain in `runs/ui/`.

Leaving synthesis unchecked retrieves evidence only. That is not an abstention. To request an answer afterward, enable it and submit once; that is a new local request. Normal manual UI submissions remain usable after this readiness pass; its recorded engineering-call limit is not a new research-run allowance or a paid budget.

## Five-minute presentation script

| What to show | Collection / workflow / mode | Public prompt and expected behavior |
|---|---|---|
| Live grounded answer | Twenty-paper / Ask / Hybrid | LightRAG question above. Explain the answer, citation cards, exact excerpts and PDF page links. |
| Discover papers | Five-paper / Discovery / Graph RAG | `Which methods were evaluated on MuSiQue? Cite at least two reporting papers and qualify benchmark comparability.` The observed result lists original HippoRAG and HippoRAG2 reports. |
| Qualify comparisons | Either / Comparison / Hybrid + Approved Facts; synthesis may stay off | Use the supplied HippoRAG comparison prompt. Show reported metrics/splits alongside **unknown** fields and the no-controlled-ranking notice. Shared benchmark names are not sufficient comparability evidence. |
| Inspect limitations | Twenty-paper / Limitations / Graph RAG | Use the supplied NER/OpenIE/scaling prompt. Show approved findings and their quotations. The observed generated answer cited two sources. |
| Handle missing evidence | Twenty-paper / Ask / Hybrid | `What exact carbon emissions in kilograms of CO2e are reported for Graph RAG Behind the Tech evaluation?` The observed answer explicitly abstained, with no invented measurement/citations. |

For a short presentation, show the live LightRAG answer, one evidence-only comparison and the explicit Graph fallback. More generation calls extend the presentation; do not submit repeatedly while a call is running.

## Explain the evidence honestly

- **Generated answer:** model-written synthesis. Checked citation IDs do not prove every sentence correct. In one discovery probe, a final qualification was overattributed to a paper; check such qualifications against the actual quotation. Source and approval checks do not eliminate model mistakes.
- **Source evidence:** exact retrieved text. A raw excerpt is not a human-approved claim. An approved claim is a reviewed source-bound summary, followed by its quotations and known/unknown conditions.
- **Graph connections used:** routes through reviewed relationships that actually entered the result. If none was selected, the UI says so. A Graph request can legitimately fall back to the exact Hybrid + Approved Facts assembly; do not present fallback as traversal success or fabricate a graph picture.
- **Requested/effective mode:** the requested algorithm and what was actually returned. The completed studies did not establish a held-out traversal benefit. Product usability is separate from that scientific finding.
- **Profiles:** this demo offers only profiles configured for its own review/target binding. The copied V2 scope belongs to the retained research checkout and is not offered here. Its synthesis remains disabled; no authority or scope was repointed.

Changing collection, profile, selector or workflow clears the previous result, preventing an old answer from being presented as belonging to new controls. Form edits take effect on submission; the result repeats the exact submitted question/mode. A stale approval/source/service error blocks display/export until a valid new query succeeds.

## Reproducible evidence and limits

[Read the M6 verification report](M6_REPORT.md). Local artifacts are under `runs/m6/`: test XML, source-preservation checks, actual public query runs/exports, durable attempt accounting, browser verification and screenshots. `scripts/m6_demo_checks.py` is the once-attempted engineering harness; its existing journal prevents silently repeating probes or resetting limits. It is not the launcher and should not be rerun to start the app.

The readiness work used 7 of 8 bounded local model attempts (two smoke probes, four service answers and one browser answer), $0 paid, no automatic retry, no private test input and no research rerun. The historical three foreign-scope refusals and corrected display/setup issues remain recorded. Frozen study code/data/results and both working graphs are preserved. Screenshot examples: [live answer](../runs/m6/demo-answer.jpg), [cited excerpts](../runs/m6/demo-sources.jpg).
