"""Thin entry points for setup, review, controlled retrieval and grounded answers."""

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
    ask = subparsers.add_parser("ask", help="Answer with an explicitly selected retrieval mode and configured provider")
    ask.add_argument("--corpus", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--output", type=Path, required=True)
    ask.add_argument("--context-tokens", type=int, default=4096, help="M1 answer context; default 4096, separate from M0 smoke limits")
    ask.add_argument("--max-output-tokens", type=int, default=512, help="M1 output limit; default 512")
    ask.add_argument("--minimum-similarity", type=float, default=0.30)
    ask.add_argument('--mode',choices=['vector','hybrid','hybrid_facts','graph'],default='vector')
    ask.add_argument('--review-dir',type=Path,default=Path('data/reviews/pilot'))
    retrieve = subparsers.add_parser('retrieve',help='Retrieve evidence without generation or gold inputs')
    retrieve.add_argument('--corpus',required=True)
    retrieve.add_argument('--question',required=True)
    retrieve.add_argument('--mode',choices=['vector','hybrid','hybrid_facts','graph'],default='vector')
    retrieve.add_argument('--review-dir',type=Path,default=Path('data/reviews/pilot'))
    retrieve.add_argument('--minimum-similarity',type=float,default=0.30,help='Vector-only threshold; hybrid channels use fixed top-12 rankings')
    retrieve.add_argument('--output',type=Path,required=True)
    for query_parser in (ask,retrieve):
        query_parser.add_argument('--profile',choices=['baseline','retrieval-v2'],default='baseline')
        query_parser.add_argument('--scope-file',help='Explicit local data/scopes declaration required for retrieval-v2')
    export = subparsers.add_parser('export-evidence', help='Validate a saved run and export its exact evidence as CSV')
    export.add_argument('--run', type=Path, required=True)
    export.add_argument('--review-dir', type=Path, default=Path('data/reviews/pilot'))
    export.add_argument('--output', type=Path, required=True)
    setup = subparsers.add_parser('search-setup',help='Explicitly create missing chunk/alias search indexes without resetting data')
    setup.add_argument('--corpus',required=True)
    setup.add_argument('--output',type=Path,required=True)
    embedding_setup = subparsers.add_parser('embedding-setup', help='Add the separate MPNet 768-D index without changing baseline vectors')
    embedding_setup.add_argument('--corpus', required=True)
    embedding_setup.add_argument('--output', type=Path, required=True)
    embedding_query = subparsers.add_parser('retrieve-embedding', help='Vector-only encoder experiment; no generation or gold inputs')
    embedding_query.add_argument('--corpus', required=True)
    embedding_query.add_argument('--question', required=True)
    embedding_query.add_argument('--encoder', choices=['minilm', 'mpnet'], required=True)
    embedding_query.add_argument('--output', type=Path, required=True)
    freeze_prepare = subparsers.add_parser('freeze-prepare', help='Prepare a public freeze proposal after isolated recovery; grants no execution')
    freeze_prepare.add_argument('--snapshot-dir', type=Path, required=True)
    freeze_prepare.add_argument('--recovery-report', type=Path, required=True)
    freeze_prepare.add_argument('--private-root', required=True, help='Evaluator root path metadata only; never read during preparation')
    freeze_prepare.add_argument('--freeze-output', type=Path, required=True)
    freeze_prepare.add_argument('--output', type=Path, required=True)
    freeze_verify = subparsers.add_parser('freeze-verify', help='Verify public code/model/snapshot commitments without private evaluation access')
    freeze_verify.add_argument('--freeze', type=Path, required=True)
    freeze_verify.add_argument('--output', type=Path, required=True)
    providers = subparsers.add_parser('provider-check', help='Explicit live adapters/resource checks; paid access requires approved limits')
    providers.add_argument('--providers', nargs='+', choices=['ollama', 'openai'], default=['ollama', 'openai'])
    providers.add_argument('--output', type=Path, required=True)
    providers.add_argument('--approval', type=Path, help='Explicit recorded M3.3 budget approval; applies only to these probes')
    backup = subparsers.add_parser('snapshot-export', help='Export a new checksummed logical graph/source/review snapshot')
    backup.add_argument('--snapshot-dir', type=Path, required=True)
    backup.add_argument('--review-dir', type=Path, default=Path('data/reviews/pilot'))
    backup.add_argument('--freeze-corpus', action='store_true', help='Freeze the exported target corpus only; preserve working graph flags')
    backup.add_argument('--output', type=Path, required=True)
    restore = subparsers.add_parser('snapshot-restore', help='Restore only into an attested empty disposable Compose target')
    restore.add_argument('--snapshot-dir', type=Path, required=True)
    restore.add_argument('--target-uri', required=True)
    restore.add_argument('--target-project', required=True)
    restore.add_argument('--output', type=Path, required=True)
    metadata = subparsers.add_parser("pilot-metadata", help="Bounded OpenAlex lookups for the declared five papers")
    metadata.add_argument("--manifest", type=Path, required=True)
    metadata.add_argument("--cache-dir", type=Path, required=True)
    metadata.add_argument("--output", type=Path, required=True)
    pilot = subparsers.add_parser("pilot-ingest", help="Build a separate five-paper corpus, preserving member snapshots")
    pilot.add_argument("--manifest", type=Path, required=True)
    pilot.add_argument("--metadata", type=Path, required=True)
    pilot.add_argument("--output", type=Path, required=True)
    expanded_metadata = subparsers.add_parser("corpus-metadata", help="Bounded metadata for a declared 20–30-paper expansion")
    expanded_metadata.add_argument("--manifest", type=Path, required=True)
    expanded_metadata.add_argument("--cache-dir", type=Path, required=True)
    expanded_metadata.add_argument("--output", type=Path, required=True)
    expanded = subparsers.add_parser("corpus-ingest", help="Ingest a separate 20–30-paper corpus, preserving previous data")
    expanded.add_argument("--manifest", type=Path, required=True)
    expanded.add_argument("--metadata", type=Path, required=True)
    expanded.add_argument("--output", type=Path, required=True)
    extract = subparsers.add_parser("extract", help="Prepare bounded local-Qwen claim-review bundles; no approvals")
    extract.add_argument("--corpus", required=True)
    extract.add_argument("--plan", type=Path, required=True)
    extract.add_argument("--bundle-dir", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--selected-papers", action="store_true", help="Explicitly extract only the plan's nonempty subset; cumulative per-PDF caps remain enforced")
    review_check = subparsers.add_parser("review-check", help="Replay packet source/identity/cap checks with no model calls")
    review_check.add_argument("--bundle-dir", type=Path, required=True)
    review_check.add_argument("--output", type=Path, required=True)
    prepare = subparsers.add_parser("review-prepare", help="Register audited candidates without decisions")
    prepare.add_argument("--bundle-dir", type=Path, required=True)
    prepare.add_argument("--review-dir", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    extend = subparsers.add_parser("review-extend", help="Copy unchanged review history into a separate superset corpus scope")
    extend.add_argument("--source-dir", type=Path, required=True)
    extend.add_argument("--review-dir", type=Path, required=True)
    extend.add_argument("--corpus", required=True)
    extend.add_argument("--output", type=Path, required=True)
    review_import = subparsers.add_parser("review-import", help="Import explicit human CSV rows into review history")
    review_import.add_argument("--review-dir", type=Path, required=True)
    review_import.add_argument("--decisions", type=Path, required=True)
    review_import.add_argument("--output", type=Path, required=True)
    revise = subparsers.add_parser("review-revise", help="Register a proposed correction and invalidate old eligibility")
    revise.add_argument("--review-dir", type=Path, required=True)
    revise.add_argument("--revision", type=Path, required=True)
    revise.add_argument("--output", type=Path, required=True)
    review_status = subparsers.add_parser("review-status", help="Replay review eligibility without model/graph calls")
    review_status.add_argument("--review-dir", type=Path, required=True)
    review_status.add_argument("--output", type=Path, required=True)
    sync = subparsers.add_parser("review-sync", help="Synchronize current human-approved facts to Neo4j")
    sync.add_argument("--review-dir", type=Path, required=True)
    sync.add_argument("--output", type=Path, required=True)
    dev = subparsers.add_parser("dev-check", help="Verify development annotations and explicit human validation; no LLM/graph calls")
    dev.add_argument("--dataset-dir", type=Path, required=True)
    dev.add_argument("--output", type=Path, required=True)
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
            if args.command == 'export-evidence':
                from research_assistant.contracts import RunArtifact
                from research_assistant.product import prepare_output
                run = RunArtifact.model_validate_json(args.run.read_text(encoding='utf-8'))
                view, csv_text = prepare_output(run, settings, args.review_dir)
                write_immutable(args.output, csv_text)
                print(json.dumps({'output': str(args.output), 'run_id': run.run_id,
                                  'evidence_units': len(run.retrieval.evidence),
                                  'workflow': view.workflow, 'status': view.status, 'papers': view.paper_count}))
                return 0
            if args.command == 'provider-check':
                from research_assistant.integrations import provider_checks, readiness_settings
                selected_settings = readiness_settings(settings, args.approval) if args.approval else settings
                result = provider_checks(selected_settings, args.providers)
            elif args.command == 'snapshot-export':
                from research_assistant.graph.recovery import export_snapshot
                result = export_snapshot(settings, args.snapshot_dir, args.review_dir, freeze_corpus=args.freeze_corpus)
            elif args.command == 'snapshot-restore':
                from research_assistant.graph.recovery import restore_snapshot
                result = restore_snapshot(args.snapshot_dir,
                    Settings.model_validate({**settings.model_dump(), 'neo4j_uri': args.target_uri}), args.target_project)
            elif args.command == "ingest":
                result = ingest_paper(args.manifest, settings)
            elif args.command in {"pilot-metadata", "corpus-metadata"}:
                from research_assistant.ingestion.corpus import ExpansionManifest, PilotManifest
                from research_assistant.ingestion.metadata import fetch_metadata
                manifest_type = PilotManifest if args.command == "pilot-metadata" else ExpansionManifest
                manifest = manifest_type.model_validate_json(args.manifest.read_text(encoding="utf-8"))
                result = fetch_metadata(manifest.papers, settings, args.cache_dir)
            elif args.command == "pilot-ingest":
                from research_assistant.ingestion.corpus import ingest_pilot
                result = ingest_pilot(args.manifest, args.metadata, settings)
            elif args.command == "corpus-ingest":
                from research_assistant.ingestion.corpus import ingest_expansion
                result = ingest_expansion(args.manifest, args.metadata, settings)
            elif args.command == "extract":
                from research_assistant.extraction.pilot import extract_pilot
                result = extract_pilot(args.corpus, args.plan, args.bundle_dir, settings, selected_only=args.selected_papers)
            elif args.command == "review-check":
                from research_assistant.review.audit import audit_packets
                result = audit_packets(args.bundle_dir)
            elif args.command == "review-prepare":
                from research_assistant.review.store import prepare_review
                result = prepare_review(args.bundle_dir, args.review_dir)
            elif args.command == "review-extend":
                from research_assistant.review.scope import extend_scope
                result = extend_scope(args.source_dir, args.review_dir, args.corpus)
            elif args.command == "review-import":
                from research_assistant.review.store import import_csv
                result = import_csv(args.review_dir, args.decisions)
            elif args.command == "review-revise":
                from research_assistant.review.contracts import ReviewRevision
                from research_assistant.review.store import load_chunks, propose_revision
                revision = ReviewRevision.model_validate_json(args.revision.read_text(encoding="utf-8"))
                result = propose_revision(args.review_dir, revision, load_chunks(args.review_dir))
            elif args.command == "review-status":
                from research_assistant.review.facts import projection
                from research_assistant.review.store import load_chunks
                result = projection(args.review_dir, load_chunks(args.review_dir))
            elif args.command == "review-sync":
                from research_assistant.graph.reviews import synchronize_review
                result = synchronize_review(args.review_dir, settings)
            elif args.command == "dev-check":
                from research_assistant.evaluation.development import check_dataset
                result = check_dataset(args.dataset_dir)
            elif args.command == 'freeze-prepare':
                from research_assistant.evaluation.freeze import prepare_freeze
                result = prepare_freeze(args.snapshot_dir, args.recovery_report, settings, args.private_root, args.freeze_output)
            elif args.command == 'freeze-verify':
                from research_assistant.evaluation.freeze import load_freeze
                frozen = load_freeze(args.freeze)
                result = {'task_id': 'M4.2.4', 'status': 'public_freeze_commitments_verified',
                          'files': len(frozen.files), 'private_evaluation_inputs_read': 0, 'final_evaluation_authorized': False}
            elif args.command == 'embedding-setup':
                from research_assistant.retrieval.embedding_experiment import setup_mpnet
                result = setup_mpnet(args.corpus, settings)
            elif args.command == 'retrieve-embedding':
                from research_assistant.retrieval.embedding_experiment import retrieve_embedding
                result = retrieve_embedding(args.corpus, args.question, args.encoder, settings)
            elif args.command == 'search-setup':
                from research_assistant.graph.search import SearchRepository
                repository = SearchRepository(settings)
                try:
                    result = repository.prepare_indexes(args.corpus)
                finally:
                    repository.close()
            elif args.command == 'retrieve':
                from research_assistant.pipeline import run_query
                request = QueryRequest(question=args.question,corpus_id=args.corpus,mode=args.mode,
                    profile_id=args.profile,scope_file=args.scope_file)
                run = run_query(request, settings, minimum_similarity=args.minimum_similarity,
                                review_directory=args.review_dir, generate=False)
                retrieval = run.retrieval
                result = run.model_dump(mode='json')
            else:
                request = QueryRequest(question=args.question, corpus_id=args.corpus, mode=args.mode,
                    profile_id=args.profile,scope_file=args.scope_file)
                result = ask_question(request, settings, args.context_tokens,
                                      args.max_output_tokens, args.minimum_similarity,args.review_dir).model_dump(mode="json")
            if args.output:
                write_immutable(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            summary = result if args.command != "ask" else {
                "output": str(args.output), "answer": result["result"],
                "evidence_units": len(result["retrieval"]["evidence"]),
                "estimated_evidence_tokens": result["retrieval"]["estimated_tokens"],
            }
            if args.command == "pilot-metadata":
                summary = {"output": str(args.output), "matched": sum(bool(p["openalex_id"]) for p in result["papers"]),
                           "papers": len(result["papers"]), "citation_edges": len(result["citation_edges"])}
            if args.command == 'retrieve':
                summary = {'output':str(args.output),'requested_mode':retrieval.requested_mode,
                           'effective_mode':retrieval.effective_mode,'fallback_reason':retrieval.fallback_reason,
                           'evidence_units':len(retrieval.evidence),'estimated_tokens':retrieval.estimated_tokens,'new_llm_calls':0}
            if args.command == 'retrieve-embedding':
                summary = {'output': str(args.output), 'encoder': result['embedding_experiment']['encoder'],
                           'evidence_units': len(result['retrieval']['evidence']), 'new_llm_calls': 0}
            print(json.dumps(summary, ensure_ascii=True, indent=2))
            if args.command == 'provider-check' and any(row['status'] == 'failed' for row in result['checks']):
                return 1
            return 0
        except Exception as exc:
            from research_assistant.pipeline import QueryExecutionError
            failure = {"status": "failed", "created_at": datetime.now(timezone.utc).isoformat(),
                       "command": args.command, "error": type(exc).__name__,
                       "message": settings.redact(str(exc))}
            if isinstance(exc, QueryExecutionError):
                failure['failed_run'] = exc.artifact.model_dump(mode='json')
            if args.command != 'export-evidence' and args.output and not args.output.exists():
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
