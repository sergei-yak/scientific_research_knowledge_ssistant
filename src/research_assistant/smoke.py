"""Opt-in setup probes; these do not ingest papers or approve scientific claims."""

from __future__ import annotations

import ctypes
import gc
import hashlib
import importlib
import importlib.metadata
import json
import platform
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from research_assistant.settings import Settings


class CheckResult(BaseModel):
    """A check outcome with explicit separation of failure and unperformed work."""

    name: str
    status: Literal["passed", "failed", "pending"]
    details: dict[str, Any]
    elapsed_seconds: float = 0


class ProbeAnswer(BaseModel):
    """Small structured-output probe with no scientific or gold evaluation data."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    value: Literal[2]


def _require(condition: bool, message: str) -> None:
    """Keep probe validation active even when Python runs in optimized mode."""
    if not condition:
        raise ValueError(message)


def check_imports() -> dict[str, Any]:
    """Import every required SDK/library without accessing providers or models."""
    modules = {
        "torch": "torch", "sentence-transformers": "sentence_transformers",
        "transformers": "transformers", "openai": "openai", "ollama": "ollama",
        "neo4j": "neo4j", "PyMuPDF": "pymupdf", "streamlit": "streamlit",
        "pandas": "pandas", "pydantic": "pydantic", "python-dotenv": "dotenv",
        "tiktoken": "tiktoken",
    }
    versions = {}
    for package, module in modules.items():
        importlib.import_module(module)
        versions[package] = importlib.metadata.version(package)
    return {"python": platform.python_version(), "packages": versions}


def check_resources() -> dict[str, Any]:
    """Capture local host/GPU resource usage without modifying services."""
    details: dict[str, Any] = {"platform": platform.platform()}
    if platform.system() == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")
            ]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError("Cannot inspect host memory")
        details.update(total_ram_bytes=memory.total, available_ram_bytes=memory.available)
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    details["gpu"] = gpu.stdout.strip() if gpu.returncode == 0 else "unavailable"
    return details


def check_model_artifacts(allow_download: bool) -> dict[str, Any]:
    """Prepare encoder/tokenizer artifacts independently of the CUDA installation."""
    from huggingface_hub import HfApi, snapshot_download
    import tiktoken

    models = []
    for model_id in ("all-MiniLM-L6-v2", "all-mpnet-base-v2"):
        if allow_download:
            revision = HfApi().model_info(f"sentence-transformers/{model_id}").sha
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise ValueError("Unexpected model revision identity")
            directory = Path(".cache/models") / model_id / revision
            snapshot_download(
                f"sentence-transformers/{model_id}", revision=revision, local_dir=directory,
                allow_patterns=["*.json", "*.txt", "model.safetensors", "1_Pooling/config.json", "README.md"],
            )
            _require((directory / "model.safetensors").is_file(), "Encoder weights were not downloaded")
            (directory.parent / "manifest.json").write_text(json.dumps({"revision": revision}), encoding="utf-8")
        directory, revision = encoder_artifact(model_id)
        models.append({"id": model_id, "revision": revision})
    if not allow_download:
        import os
        cache_key = hashlib.sha1(b"https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken").hexdigest()
        if not (Path(os.environ["TIKTOKEN_CACHE_DIR"]) / cache_key).is_file():
            raise FileNotFoundError("Estimator cache missing; explicitly allow setup downloads")
    estimator = tiktoken.get_encoding("o200k_base")
    _require(estimator.decode(estimator.encode("M0 tokenizer probe")) == "M0 tokenizer probe", "Estimator round-trip failed")
    return {"models": models, "estimator": estimator.name, "inference_verified": False}


def encoder_artifact(model_id: str) -> tuple[Path, str]:
    """Resolve a completed, revision-addressed local model without network access."""
    if model_id not in {"all-MiniLM-L6-v2", "all-mpnet-base-v2"}:
        raise ValueError("Unknown setup encoder")
    root = Path(".cache/models") / model_id
    revision = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid local model revision")
    directory = root / revision
    if not (directory / "model.safetensors").is_file():
        raise FileNotFoundError("Model download incomplete; run the explicit artifact check")
    return directory, revision


def check_embeddings(allow_download: bool) -> dict[str, Any]:
    """Verify both fixed encoders, finite vectors, tokenizer limits and CUDA math."""
    import numpy as np
    import tiktoken
    import torch
    from sentence_transformers import SentenceTransformer

    details: dict[str, Any] = {"models": [], "cuda_available": torch.cuda.is_available()}
    if allow_download:
        check_model_artifacts(True)
    if torch.cuda.is_available():
        result = (torch.ones((8, 8), device="cuda") @ torch.ones((8, 8), device="cuda")).cpu()
        _require(float(result[0, 0]) == 8, "CUDA matrix result was incorrect")
        details["cuda_runtime"] = torch.version.cuda
        details["gpu_name"] = torch.cuda.get_device_name(0)
    texts = ["A research method is evaluated on a benchmark.", "The paper reports a limitation."]
    for model_id, dimension in (("all-MiniLM-L6-v2", 384), ("all-mpnet-base-v2", 768)):
        directory, revision = encoder_artifact(model_id)
        model = SentenceTransformer(
            str(directory), device="cpu", local_files_only=True,
        )
        vectors = model.encode(texts, normalize_embeddings=True)
        _require(vectors.shape == (2, dimension) and np.isfinite(vectors).all(), f"Invalid {model_id} vector shape/values")
        _require(np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5), f"Invalid {model_id} normalization")
        lengths = [len(model.tokenizer.encode(text, add_special_tokens=True)) for text in texts]
        _require(max(lengths) <= model.max_seq_length, f"{model_id} probe would be truncated")
        details["models"].append({
            "id": model_id, "revision": revision,
            "dimension": dimension, "max_seq_length": model.max_seq_length, "probe_lengths": lengths,
        })
        del model, vectors
        gc.collect()
    if not allow_download:
        import os
        cache_key = hashlib.sha1(b"https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken").hexdigest()
        if not (Path(os.environ["TIKTOKEN_CACHE_DIR"]) / cache_key).is_file():
            raise FileNotFoundError("Estimator cache missing; explicitly allow setup downloads")
    estimator = tiktoken.get_encoding("o200k_base")
    encoded = estimator.encode(texts[0])
    _require(bool(encoded) and estimator.decode(encoded) == texts[0], "Estimator round-trip failed")
    details["token_estimator"] = {"name": estimator.name, "probe_tokens": len(encoded)}
    return details


def check_neo4j(settings: Settings) -> dict[str, Any]:
    """Test isolated sentinel nodes/indexes and remove only this run's own fixtures."""
    from neo4j import GraphDatabase, Query

    if not settings.neo4j_password.get_secret_value():
        return {"pending": "NEO4J_PASSWORD is not configured"}
    run_id = uuid.uuid4().hex
    label, vector_index, text_index = f"M0Smoke_{run_id}", f"m0_vec_{run_id}", f"m0_text_{run_id}"
    created_indexes = []
    with GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        connection_timeout=10, max_transaction_retry_time=0,
    ) as driver, driver.session(database=settings.neo4j_database) as session:
        driver.verify_connectivity()
        version = session.run("CALL dbms.components() YIELD versions, edition RETURN versions, edition").single().data()
        try:
            node_query = f"MERGE (n:`{label}` {{run_id:$run, id:$id}}) SET n.text=$text, n.embedding=$vector"
            for _ in range(2):
                session.run(Query(node_query, timeout=15), run=run_id, id="a", text="research smoke checkpoint", vector=[1.0] + [0.0] * 383).consume()
            count = session.run(f"MATCH (n:`{label}` {{run_id:$run}}) RETURN count(n) AS count", run=run_id).single()["count"]
            _require(count == 1, "Neo4j sentinel MERGE was not idempotent")
            for name, statement in (
                (vector_index, f"CREATE VECTOR INDEX `{vector_index}` FOR (n:`{label}`) ON (n.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`:384, `vector.similarity_function`:'cosine'}}}}"),
                (text_index, f"CREATE FULLTEXT INDEX `{text_index}` FOR (n:`{label}`) ON EACH [n.text]"),
            ):
                session.run(Query(statement, timeout=20)).consume()
                created_indexes.append(name)
                session.run("CALL db.awaitIndex($name, 60)", name=name).consume()
            states = session.run("SHOW INDEXES YIELD name,state WHERE name IN $names RETURN name,state", names=created_indexes).data()
            _require(len(states) == 2 and all(item["state"] == "ONLINE" for item in states), "Smoke indexes are not ONLINE")
            vector = session.run("CALL db.index.vector.queryNodes($index, 1, $vector) YIELD node,score RETURN node.id AS id,score", index=vector_index, vector=[1.0] + [0.0] * 383).single()
            lexical = session.run("CALL db.index.fulltext.queryNodes($index, $term) YIELD node,score RETURN node.id AS id,score", index=text_index, term="checkpoint").single()
            _require(vector is not None and lexical is not None and vector["id"] == lexical["id"] == "a", "Vector/full-text lookup missed sentinel")
        finally:
            for name in created_indexes:
                session.run(f"DROP INDEX `{name}` IF EXISTS").consume()
            session.run(f"MATCH (n:`{label}` {{run_id:$run}}) DELETE n", run=run_id).consume()
        remaining = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS count").single()["count"]
        _require(remaining == 0, "Smoke sentinel cleanup was incomplete")
        return {"server": version, "idempotent_sentinel": True, "indexes": states, "vector_and_fulltext": True, "cleanup": "only this run's nodes/indexes removed"}


def check_ollama(settings: Settings, resident_encoder: bool = False) -> dict[str, Any]:
    """Run two bounded local probes against an already installed, explicitly chosen model."""
    import ollama

    client = ollama.Client(host=settings.ollama_base_url, timeout=settings.request_timeout_seconds)
    installed = client.list().models
    model_name = settings.generation_model
    model = next((item for item in installed if item.model == model_name), None)
    if model is None:
        return {"pending": f"Configured model {model_name} is not installed; no automatic pull/substitution"}
    encoder = None
    if resident_encoder:
        from sentence_transformers import SentenceTransformer
        directory, _ = encoder_artifact("all-MiniLM-L6-v2")
        encoder = SentenceTransformer(str(directory), device="cpu", local_files_only=True)
    before = check_resources()
    options = {"num_ctx": settings.ollama_context_tokens, "num_predict": settings.max_output_tokens, "temperature": 0, "num_batch": 64}
    outputs = []
    for schema, prompt in ((None, "Reply with the single word READY."), (ProbeAnswer.model_json_schema(), "Return JSON only: status is ok and value is 2. Use this schema: " + json.dumps(ProbeAnswer.model_json_schema()))):
        if encoder is not None and schema is not None:
            vectors = encoder.encode(["M0 resource coexistence probe"])
            _require(vectors.shape == (1, 384), "Resident encoder inference failed")
        start = time.perf_counter()
        response = client.chat(model=model_name, messages=[{"role": "user", "content": prompt}], format=schema, options=options, think=False, keep_alive="2m")
        content = response.message.content
        if schema:
            ProbeAnswer.model_validate_json(content)
        else:
            _require(content.strip().upper() == "READY", "Local text probe did not return READY")
        outputs.append({"kind": "structured" if schema else "text", "prompt": prompt, "output": content, "seconds": round(time.perf_counter() - start, 3), "prompt_tokens": response.prompt_eval_count, "output_tokens": response.eval_count})
    running = client.ps().models
    return {"provider": "ollama", "sdk_version": importlib.metadata.version("ollama"), "prompt_version": "m0-readiness-v1", "timeout_seconds": settings.request_timeout_seconds, "retries": 0, "concurrency": 1, "model": model_name, "digest": model.digest, "size_bytes": model.size, "quantization": model.details.quantization_level, "options": options, "probes": outputs, "resident_encoder_cpu": encoder is not None, "resources_before": before, "resources_loaded": check_resources(), "loaded_models": [item.model_dump(mode="json") for item in running]}


def check_openai(settings: Settings) -> dict[str, Any]:
    """Inspect SDK/configuration only; paid inference awaits budgeted adapter work."""
    import openai

    return {"pending": settings.paid_probe_blockers() or ["Paid live probes require the budget-accounted provider adapter in M1; no request made"], "sdk_version": openai.__version__, "model": settings.openai_model, "requests_made": 0}


def run_check(name: str, operation: Callable[[], dict[str, Any]], settings: Settings) -> CheckResult:
    """Capture a bounded probe's actual result and sanitize exceptions."""
    start = time.perf_counter()
    try:
        details = operation()
        status = "pending" if "pending" in details else "passed"
    except Exception as exc:
        status, details = "failed", {"error_type": type(exc).__name__, "message": settings.redact(str(exc))}
    return CheckResult(name=name, status=status, details=details, elapsed_seconds=round(time.perf_counter() - start, 3))


def new_report(results: list[CheckResult]) -> dict[str, Any]:
    """Build a timestamped report without conflating pending work with success."""
    return {"milestone": "M0", "created_at": datetime.now(timezone.utc).isoformat(), "checks": [item.model_dump(mode="json") for item in results]}
