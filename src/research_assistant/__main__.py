"""Thin command-line entry point for setup and the M1 vector baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from research_assistant.settings import Settings, configure_caches


def main(argv: list[str] | None = None) -> int:
    """Run explicitly selected setup checks and write a sanitized JSON report."""
    parser = argparse.ArgumentParser(description="Scientific research assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke = subparsers.add_parser("smoke", help="Run selected environment/service probes")
    smoke.add_argument("--checks", nargs="+", choices=["imports", "resources", "model-artifacts", "embeddings", "neo4j", "ollama", "openai"], default=["imports", "resources"])
    smoke.add_argument("--allow-model-download", action="store_true", help="Permit encoder/estimator setup downloads")
    smoke.add_argument("--resident-encoder", action="store_true", help="Hold cached CPU MiniLM during local Ollama probes")
    smoke.add_argument("--output", type=Path, help="New report file; existing reports are never overwritten")
    ingest = subparsers.add_parser("ingest", help="Parse/embed/index a declared local paper")
    ingest.add_argument("--manifest", type=Path, required=True)
    ingest.add_argument("--output", type=Path)
    ask = subparsers.add_parser("ask", help="Answer from a ready vector corpus using local Qwen")
    ask.add_argument("--corpus", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--output", type=Path, required=True)
    ask.add_argument("--context-tokens", type=int, default=4096, help="M1 answer context; default 4096, separate from M0 smoke limits")
    ask.add_argument("--max-output-tokens", type=int, default=512, help="M1 output limit; default 512")
    ask.add_argument("--minimum-similarity", type=float, default=0.30)
    args = parser.parse_args(argv)
    configure_caches()
    try:
        settings = Settings.from_env()
    except ValidationError as exc:
        print(json.dumps({"error": "invalid_settings", "fields": [list(item["loc"]) for item in exc.errors(include_input=False)]}))
        return 2
    if args.output and args.output.exists():
        parser.error("Report already exists; choose a new output path")
    if args.command != "smoke":
        from research_assistant.contracts import QueryRequest
        from research_assistant.pipeline import ask_question, ingest_paper, write_immutable
        try:
            if args.command == "ingest":
                result = ingest_paper(args.manifest, settings)
            else:
                request = QueryRequest(question=args.question, corpus_id=args.corpus)
                result = ask_question(request, settings, args.context_tokens,
                                      args.max_output_tokens, args.minimum_similarity).model_dump(mode="json")
            if args.output:
                write_immutable(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            summary = result if args.command == "ingest" else {
                "output": str(args.output), "answer": result["result"],
                "evidence_units": len(result["retrieval"]["evidence"]),
                "estimated_evidence_tokens": result["retrieval"]["estimated_tokens"],
            }
            print(json.dumps(summary, ensure_ascii=True, indent=2))
            return 0
        except Exception as exc:
            failure = {"status": "failed", "created_at": datetime.now(timezone.utc).isoformat(),
                       "command": args.command, "error": type(exc).__name__,
                       "message": settings.redact(str(exc))}
            if args.output and not args.output.exists():
                try:
                    write_immutable(args.output, json.dumps(failure, indent=2) + "\n")
                except OSError:
                    failure["report_error"] = "Could not write the requested failure artifact"
            print(json.dumps(failure))
            return 1
    from research_assistant.smoke import check_embeddings, check_imports, check_model_artifacts, check_neo4j, check_ollama, check_openai, check_resources, new_report, run_check

    operations = {
        "imports": check_imports, "resources": check_resources,
        "model-artifacts": lambda: check_model_artifacts(args.allow_model_download),
        "embeddings": lambda: check_embeddings(args.allow_model_download),
        "neo4j": lambda: check_neo4j(settings),
        "ollama": lambda: check_ollama(settings, args.resident_encoder),
        "openai": lambda: check_openai(settings),
    }
    results = [run_check(name, operations[name], settings) for name in args.checks]
    report = json.dumps(new_report(results), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(report)
    return 1 if any(item.status == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
