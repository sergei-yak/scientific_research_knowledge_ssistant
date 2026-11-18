"""Public-only matched evaluation setup; no operation consumes private evaluation inputs."""

import argparse
import json
from pathlib import Path

from research_assistant.evaluation.matched_freeze import load_freeze, prepare_freeze
from research_assistant.evaluation.matched_scope import prepare_scope
from research_assistant.evaluation.readiness_v2 import load_source_attestation
from research_assistant.settings import Settings, configure_caches


def main(argv=None):
    """Source check/real scope/freezing require explicit named public files and never run answers."""
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    source=sub.add_parser('source-check')
    source.add_argument('--attestation',type=Path,required=True)
    source.add_argument('--sha256',required=True)
    scope=sub.add_parser('scope-prepare')
    scope.add_argument('--snapshot-directory',type=Path,required=True)
    scope.add_argument('--recovery-report',type=Path,required=True)
    scope.add_argument('--output',type=Path,required=True)
    freeze=sub.add_parser('freeze-prepare')
    freeze.add_argument('--scope-path',type=Path,required=True)
    freeze.add_argument('--source-attestation-path',type=Path,required=True)
    freeze.add_argument('--source-attestation-sha256',required=True)
    freeze.add_argument('--snapshot-directory',type=Path,required=True)
    freeze.add_argument('--recovery-report',type=Path,required=True)
    freeze.add_argument('--private-root',required=True)
    freeze.add_argument('--output',type=Path,required=True)
    verify=sub.add_parser('freeze-verify')
    verify.add_argument('--freeze',type=Path,required=True)
    args=parser.parse_args(argv)
    configure_caches()
    try:
        if args.operation=='source-check':
            evidence=load_source_attestation(args.attestation,args.sha256)
            result={'status':'source_human_annotation_ready','approved':evidence.counts.approved,
                    'runner_readiness':False,'execution_authorized':False}
        elif args.operation=='freeze-verify':
            load_freeze(args.freeze)
            result={'status':'public_matched_freeze_verified','execution_authorized':False}
        elif args.operation=='scope-prepare':
            result=prepare_scope(args.snapshot_directory,args.recovery_report,Settings.from_env(),args.output)
        else:
            result=prepare_freeze(scope_path=args.scope_path,source_attestation_path=args.source_attestation_path,
                source_attestation_sha256=args.source_attestation_sha256,snapshot_directory=args.snapshot_directory,
                recovery_report=args.recovery_report,private_root=args.private_root,settings=Settings.from_env(),output=args.output)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'declined_or_failed','error_type':type(exc).__name__,
                         'message':'No private inputs consumed; inspect public setup bindings.'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
