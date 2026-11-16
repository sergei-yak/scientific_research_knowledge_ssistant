"""Synthetic-only scope/authorization tests; never touch an external private path."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.freeze import FinalRunAuthorization, RunPlan
from research_assistant.evaluation.proposals import (
    EvaluatorAuthoringAuthorization, EvaluatorAuthoringScope, MatchedStudyProposal,
    check_authoring_authorization,
)


def scope(**updates):
    """All paths are inert synthetic strings, never files or real project/private inputs."""
    return EvaluatorAuthoringScope(**{**dict(developer_root='C:/fixture/worktree', baseline_root='C:/fixture/baseline',
        output_root='C:/fixture/private/fresh', retired_questions_file='C:/fixture/private/retired/questions.jsonl',
        public_bundle_manifest='C:/fixture/worktree/public/manifest.json', public_bundle_manifest_sha256='a'*64,
        task_file='C:/fixture/worktree/docs/task.md', task_sha256='b'*64), **updates})


def receipt(value, **updates):
    """Synthetic receipts are confined to this unit test and never production authorization."""
    return EvaluatorAuthoringAuthorization(**{**dict(origin='human_chat', scope_sha256=fingerprint(value.model_dump(mode='json')),
        reviewer='Synthetic test reviewer', received_at=datetime(2026,1,1,tzinfo=timezone.utc),
        verbatim_response='Synthetic fixture approval only', approved=True), **updates})


def test_complete_proposal_never_counts_as_old_run_or_authorization():
    value = MatchedStudyProposal()
    assert len(value.conditions)==12 and len({c.condition_id for c in value.conditions})==12
    assert value.question_count*len(value.conditions)==288 and not value.final_execution_authorized
    with pytest.raises(ValidationError):
        RunPlan.model_validate(value.model_dump())
    with pytest.raises(ValidationError):
        FinalRunAuthorization.model_validate(value.model_dump())


def test_condition_policy_substitution_cannot_hide_behind_mode_name():
    value = MatchedStudyProposal().model_dump()
    value['conditions'][8]['selector_id']='reference'
    with pytest.raises(ValidationError,match='exact A0/A1/A2'):
        MatchedStudyProposal.model_validate(value)
    value = MatchedStudyProposal().model_dump(); value['conditions']=value['conditions'][:4]
    with pytest.raises(ValidationError,match='exact A0/A1/A2'):
        MatchedStudyProposal.model_validate(value)


@pytest.mark.parametrize('field,value', [('generation_request_limit',96),('retrieval_request_limit',144),
    ('paid_budget_usd',1),('concurrency',2),('retries',1),('final_execution_authorized',True)])
def test_proposal_bounds_cannot_be_silently_changed(field,value):
    with pytest.raises(ValidationError):
        MatchedStudyProposal(**{field:value})


@pytest.mark.parametrize('updates', [dict(output_root='C:/fixture/worktree/private'),
    dict(output_root='C:/fixture/baseline/private'), dict(output_root='C:/fixture/private/retired/new'),
    dict(output_root='C:/fixture/private'),dict(output_root='C:/fixture/private/../fresh'), dict(retired_questions_file='C:/fixture/private/retired/annotations.jsonl'),
    dict(retired_questions_file='C:/fixture/worktree/questions.jsonl'),dict(task_file='C:/fixture/other/task.md'),
    dict(public_bundle_manifest_sha256='0'*64), dict(output_root='relative/private')])
def test_authoring_path_boundary_is_fail_closed_without_private_io(updates):
    with pytest.raises(ValidationError):
        scope(**updates)


def test_exact_authoring_receipt_cannot_be_reused_after_scope_change():
    original = scope(); approval = receipt(original)
    assert check_authoring_authorization(original,approval)['final_execution_authorized'] is False
    changed = scope(output_root='C:/fixture/private/different')
    with pytest.raises(ValueError,match='different exact scope'):
        check_authoring_authorization(changed,approval)
    with pytest.raises(ValidationError):
        FinalRunAuthorization.model_validate(approval.model_dump())


@pytest.mark.parametrize('updates', [dict(approved=False),dict(received_at=datetime(2026,1,1)),
    dict(reviewer='  '),dict(verbatim_response='  '),dict(final_execution_authorized=True)])
def test_missing_or_inferred_human_provenance_is_rejected(updates):
    with pytest.raises(ValidationError):
        receipt(scope(),**updates)
