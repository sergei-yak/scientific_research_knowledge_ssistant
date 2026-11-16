"""Synthetic schedules verify pairing/rotation without private data or model execution."""

from collections import Counter

import pytest
from pydantic import ValidationError

from research_assistant.evaluation.proposals import CATEGORIES, MatchedStudyProposal
from research_assistant.evaluation.scheduling import QuestionKey, build_proposed_schedule


def questions():
    """Return synthetic metadata only; there are no actual questions or reference answers."""
    return [QuestionKey(question_id=f'fixture-{split}-{category}-{i}',split=split,category=category)
            for split, count in (('development',2),('held_out',4)) for category in CATEGORIES for i in range(count)]


def test_full_matrix_keeps_paired_conditions_and_balanced_rotation():
    plan = MatchedStudyProposal(); keys = questions(); slots = build_proposed_schedule(keys,plan)
    assert len(slots)==288 and [slot.slot_index for slot in slots]==list(range(1,289))
    assert len({slot.slot_identity for slot in slots})==288 and not any(slot.execution_authorized for slot in slots)
    for key in keys:
        group = [slot for slot in slots if slot.question==key]
        assert len(group)==12 and {slot.condition.condition_id for slot in group}=={c.condition_id for c in plan.conditions}
    # Across 24 questions each condition occupies each within-question position twice.
    for column in range(12):
        assert Counter(slot.condition.condition_id for slot in slots[column::12])=={c.condition_id:2 for c in plan.conditions}
    assert Counter(slot.question.split for slot in slots)=={'development':96,'held_out':192}


def test_input_permutation_does_not_change_paired_schedule():
    plan = MatchedStudyProposal()
    assert build_proposed_schedule(questions(),plan)==build_proposed_schedule(list(reversed(questions())),plan)


@pytest.mark.parametrize('mutation', ['duplicate','missing','wrong_split','wrong_category','blank','noncanonical'])
def test_bad_metadata_is_rejected_before_any_slot_is_returned(mutation):
    keys = questions()
    if mutation=='duplicate':keys[-1]=keys[0]
    elif mutation=='missing':keys.pop()
    elif mutation=='wrong_split':keys[0]=keys[0].model_copy(update={'split':'held_out'})
    elif mutation=='wrong_category':keys[0]=keys[0].model_copy(update={'category':'multi_hop'})
    elif mutation=='blank':keys[0]=keys[0].model_copy(update={'question_id':' '})
    else:keys[0]=keys[0].model_copy(update={'question_id':' fixture '})
    with pytest.raises(ValueError):build_proposed_schedule(keys,MatchedStudyProposal())


def test_prompt_and_gold_cannot_enter_scheduler_contract():
    with pytest.raises(ValidationError):
        QuestionKey(question_id='fixture',split='development',category='direct',reference_answer='forbidden')
    with pytest.raises(ValidationError):
        QuestionKey(question_id='fixture',split='development',category='direct',question='forbidden')


def test_post_validation_policy_mutation_cannot_change_the_schedule_silently():
    plan = MatchedStudyProposal()
    plan.conditions[8].selector_id='reference'
    with pytest.raises(ValidationError):
        build_proposed_schedule(questions(),plan)
