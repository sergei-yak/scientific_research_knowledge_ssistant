"""M0 command-line entry point; later milestones add product operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from research_assistant.settings import Settings, configure_caches


def main(argv: list[str] | None = None) -> int:
    """Run explicitly selected setup checks and write a sanitized JSON report."""
    parser = argparse.ArgumentParser(description="Research assistant M0 setup checks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke = subparsers.add_parser("smoke", help="Run selected environment/service probes")
    smoke.add_argument("--checks", nargs="+", choices=["imports", "resources", "model-artifacts", "embeddings", "neo4j", "ollama", "openai"], default=["imports", "resources"])
    smoke.add_argument("--allow-model-download", action="store_true", help="Permit encoder/estimator setup downloads")
    smoke.add_argument("--resident-encoder", action="store_true", help="Hold cached CPU MiniLM during local Ollama probes")
    smoke.add_argument("--output", type=Path, help="New report file; existing reports are never overwritten")
    args = parser.parse_args(argv)
    configure_caches()
    try:
        settings = Settings.from_env()
    except ValidationError as exc:
        print(json.dumps({"error": "invalid_settings", "fields": [list(item["loc"]) for item in exc.errors(include_input=False)]}))
        return 2
    from research_assistant.smoke import check_embeddings, check_imports, check_model_artifacts, check_neo4j, check_ollama, check_openai, check_resources, new_report, run_check

    if args.output and args.output.exists():
        parser.error("Report already exists; choose a new output path")
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
