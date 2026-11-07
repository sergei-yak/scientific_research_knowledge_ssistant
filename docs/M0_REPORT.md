# M0 readiness report

Date: 2026-11-07 (America/Chicago). This records actual checks, not a claim that M1 is implemented.

**Outcome: M0 is ready for M1 using the explicitly chosen local provider.** OpenAI live inference remains pending credentials and a user-approved budget; this does not block the local path.

## Current gate status

| Task | Status | Evidence |
|---|---|---|
| M0.1 runtime/lock | Passed | Python 3.11.13, full locked installation/imports, CUDA math, both encoders/tokenizer limits, CLI and 17 offline tests verified in the main environment. |
| M0.2 database | Passed | Healthy isolated Neo4j 5.26.32; parameterized sentinel, idempotency, vector/full-text indexes and cleanup verified. |
| M0.3 provider/resources | Passed for selected local provider; OpenAI live pending | Qwen text/JSON passed with CPU MiniLM resident and exercised while Neo4j was running. Zero paid requests made. |

## Environment and identities

- Windows 11 Home, approximately 32 GiB RAM, RTX 4070 Ti with 12,282 MiB VRAM, driver 617.42.
- `uv` 0.10.10; managed CPython 3.11.13 was already installed. The shell's default Python 3.12 was not used for the locked environment.
- Docker Engine 29.4.3 / Compose 5.1.4; Docker Desktop and Ollama were started. Ollama runtime reports 0.40.13; its Python SDK is separately pinned to 0.6.3.
- Neo4j image: `neo4j:5.26.32-community`; resolved digest `sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f`.
- New Compose project: `dbu-research-assistant`; persistent project-specific data/log volumes. Ports 7474/7687 bind to 127.0.0.1. Existing unrelated volumes were preserved.
- Qwen: `qwen3.8:latest`, 27.3B, Q4_K_M; digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`.
- MiniLM revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; MPNet: `e8c3b32edf5434bc2275fc9bab85f82640a19130`. Both downloaded and passed actual inference.
- Actual neural/runtime versions: Torch `2.6.0+cu124`, Sentence Transformers `4.1.0`, Transformers `4.57.6`, Pandas `2.3.3`, Pydantic `2.14.3`, `tiktoken` `0.14.0`. Build backend pinned to the tested Hatchling `1.33.0`.
- Lockfile SHA-256: `8baf584693d8ab776870b666044fd9696883c023f66392e7adcf99f74d4db7c7`.

## Verification completed

All commands were run from the project root. Local service/network operations needed sandbox escalation; this is distinct from service failure.

| Command/check | Actual outcome |
|---|---|
| `uv lock`, `uv lock --check` | 95 packages resolved; lock consistency passed. |
| `uv sync --locked` | Passed: complete 79-package environment installed, including the 2.4 GiB CUDA wheel. Preparation took 37m17s; installation 7.53s. |
| `uv sync --locked --offline`, `uv pip check` | Passed: cached resynchronization and all installed package requirements compatible. |
| `UV_PROJECT_ENVIRONMENT=.venv-checks` with `uv sync --locked --no-install-package torch` | Temporary environment installed from the same lockfile; deliberately incomplete and not a substitute for the final environment. |
| Temporary environment offline tests | 17 passed; two service tests deselected. |
| Main environment: `uv run --locked --offline pytest -m "not integration"` | 17 passed, two deselected; no package-network access required. |
| CLI `--help`, Python compilation | Passed. |
| `docker compose config --quiet`, startup and health | Passed; new isolated volumes, no reset of existing data. |
| CLI Neo4j probe | Passed: both indexes ONLINE, both searches correct, MERGE sentinel idempotent, own fixture resources removed. |
| Enabled Neo4j pytest integration | One passed; Ollama pytest case intentionally skipped (local probes run separately). |
| CLI Ollama probe | Text `READY`; structured JSON validated as `{status:"ok",value:2}`. Cold first request 77.772 s; following structured request 2.806 s. |
| Model-artifact probe | Passed using revision-addressed local directories; actual inference verified separately below. |
| Final main-environment import/resource/encoder probe | Passed: every required import, CUDA 12.4 matrix result, finite normalized 384-D/768-D outputs; token limits 256/384. Shared estimator round-trip passed. |
| Final main-environment Neo4j/Ollama probe with `--resident-encoder` | Passed: Neo4j fixture/index cleanup; Qwen text and JSON, with cached CPU MiniLM loaded and exercised. First request 20.933 s, following JSON 2.853 s. |
| OpenAI config/import probe | SDK 3.46.0 imported. Live inference pending key and approved budget. |

Local ignored raw reports under `runs/m0/`: `preflight.json`, `services.json`, `neo4j-fixed.json`, `model-artifacts.json`, `model-artifacts-localdir.json`, **`final-environment.json`**, and **`final-services.json`**. Final commands:

```powershell
uv run --locked python -m research_assistant smoke --checks imports resources embeddings openai --output runs/m0/final-environment.json
uv run --locked python -m research_assistant smoke --checks neo4j ollama --resident-encoder --output runs/m0/final-services.json
```

Failed attempts are retained: the first Neo4j probe exposed a `Session.run` keyword collision, fixed and verified by rerun; the first artifact attempt hit Windows symlink privileges, resolved through supported local-directory downloads without changing OS settings. Initial sandbox-only DNS/service access failures were rerun with authorized escalation. Editing build metadata triggered a fresh backend resolution; the subsequent full-environment offline run passed. Existing report files are never overwritten.

## Resource limits and pending checks

The local probe used context 2,048, at most 128 output tokens, temperature zero, thinking disabled, no retries and one request at a time. The initial probe (without an encoder resident) left about 4.1 GB RAM and used 11,745 MiB GPU memory. In the final combined check, Neo4j, CPU MiniLM and Qwen coexisted; available RAM was **5,469,810,688 bytes** and total GPU use **11,643 MiB**. Ollama reported 9,672,767,568 bytes in VRAM and CPU/GPU offloading. These are individual snapshots, not controlled performance comparisons.

Skipped/pending: OpenAI live inference (no API key, approved budget or per-request paid ceiling); the duplicate Ollama pytest integration case was skipped because the explicit CLI probes covered live inference. Native snapshot/restore, paper ingestion and benchmark checks belong to later milestones. M1 must recheck capacity with a context large enough for instructions, question, 1,800 estimated evidence tokens and output. These small probes do not establish full production capacity; use CPU embeddings while the large local model occupies most VRAM.

OpenAI paid inference remains pending under the agreed policy; the local provider is the explicit M0 choice, not an automatic fallback. There is **no blocking prerequisite for starting the local M1 baseline**. Corpus ingestion, UI, review and final evaluation have not begun. The Git planning baseline is `d68606b`; the M0 implementation checkpoint records the verified setup and this report.
