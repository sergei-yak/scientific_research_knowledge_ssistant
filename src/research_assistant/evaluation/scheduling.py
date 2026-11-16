"""Pure deterministic matched-study scheduling; no prompts, gold, I/O or execution authority."""

from __future__ import annotations

from collections import Counter
import random
from typing import Literal

from pydantic import Field

from research_assistant.contracts import Contract, fingerprint
from research_assistant.evaluation.proposals import CATEGORIES, MatchedStudyProposal, ProposedCondition


class QuestionKey(Contract):
    """Only identifiers/strata enter scheduling; prompt/answer fields are forbidden."""

    question_id: str = Field(min_length=1, max_length=128)
    split: Literal['development', 'held_out']
    category: Literal['direct', 'cross_paper', 'multi_hop', 'unanswerable']


class ProposedSlot(Contract):
    """A logical matrix slot, not a durable reservation or permission to execute it."""

    slot_index: int = Field(ge=1, le=288)
    question: QuestionKey
    condition: ProposedCondition
    proposal_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    slot_identity: str = Field(pattern=r'^[a-f0-9]{64}$')
    execution_authorized: Literal[False] = False


def build_proposed_schedule(keys: list[QuestionKey], proposal: MatchedStudyProposal) -> list[ProposedSlot]:
    """Shuffle canonical IDs, rotate complete conditions and retain one slot per pair.

    The authorized future runner may reuse this pure ordering rule after validation.
    A schedule built from real held-out identifiers belongs in evaluator storage,
    never a public development artifact. No filesystem access happens here.
    """
    # Pydantic model_copy/attribute updates can bypass validators. Validate fresh
    # values at the boundary rather than trusting a previously constructed object.
    proposal = MatchedStudyProposal.model_validate(proposal.model_dump(mode='json'))
    keys = [QuestionKey.model_validate(key.model_dump(mode='json')) for key in keys]
    if len(keys)!=proposal.question_count or len({key.question_id for key in keys})!=len(keys):
        raise ValueError('Schedule requires 24 unique question identities')
    if any(not key.question_id.strip() or key.question_id!=key.question_id.strip() for key in keys):
        raise ValueError('Question identifiers must be nonblank and canonical')
    for split, per_category in (('development', 2), ('held_out', 4)):
        actual = Counter(key.category for key in keys if key.split==split)
        if actual!={category:per_category for category in CATEGORIES}:
            raise ValueError('Schedule split/category counts differ from the proposal')
    ordered = sorted(keys, key=lambda key:key.question_id)
    random.Random(proposal.order_seed).shuffle(ordered)
    plan_sha = fingerprint(proposal.model_dump(mode='json'))
    slots = []
    for position, question in enumerate(ordered):
        offset = position % len(proposal.conditions)
        conditions = proposal.conditions[offset:]+proposal.conditions[:offset]
        for condition in conditions:
            slot_index = len(slots)+1
            identity = fingerprint([plan_sha, slot_index, question.model_dump(), condition.model_dump()])
            slots.append(ProposedSlot(slot_index=slot_index, question=question, condition=condition,
                         proposal_sha256=plan_sha, slot_identity=identity))
    if len(slots)!=proposal.generation_request_limit or len({slot.slot_identity for slot in slots})!=len(slots):
        raise ValueError('Matched schedule exceeds/misses a proposed logical slot')
    return slots
