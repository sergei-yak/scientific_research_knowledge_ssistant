"""In-process single-use generation permits issued only by the authorized matched runner."""

from dataclasses import dataclass
from weakref import WeakKeyDictionary

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.matched_freeze import MatchedAuthorization, MatchedFreeze
from research_assistant.evaluation.scheduling import ProposedSlot


class StudyGrant:
    """Opaque registry key; constructing/copying it does not confer authority."""


class SlotPermit:
    """Opaque one-slot key, never a serializable UI/CLI option."""


@dataclass
class _Grant:
    freeze: MatchedFreeze
    freeze_sha256: str
    used_slots: set


_STUDIES = WeakKeyDictionary()
_SLOTS = WeakKeyDictionary()


def _register_study(freeze: MatchedFreeze, freeze_sha256: str, authorization: MatchedAuthorization) -> StudyGrant:
    """Runner calls this after public authorization, physical verification and durable start claim."""
    freeze = MatchedFreeze.model_validate(freeze.model_dump(mode='json'))
    authorization = MatchedAuthorization.model_validate(authorization.model_dump(mode='json'))
    if authorization.freeze_file_sha256 != freeze_sha256:
        raise ValueError('Study grant requires an exact matched final authorization')
    key = StudyGrant()
    _STUDIES[key] = _Grant(freeze, freeze_sha256, set())
    return key


def _issue_slot(grant: StudyGrant, slot: ProposedSlot, request, *, reservation_persisted: bool) -> SlotPermit:
    """Reserve each validated logical pair once; callers fsync its ledger entry first."""
    if grant not in _STUDIES or reservation_persisted is not True:
        raise ValueError('No authorized durable study reservation')
    proof = _STUDIES[grant]
    slot = ProposedSlot.model_validate(slot.model_dump(mode='json'))
    plan = proof.freeze.plan
    if (slot.proposal_sha256 != fingerprint(plan.model_dump(mode='json'))
            or slot.condition not in plan.conditions or slot.slot_index in proof.used_slots
            or len(proof.used_slots) >= plan.generation_request_limit
            or slot.slot_identity != fingerprint([slot.proposal_sha256, slot.slot_index,
                                                  slot.question.model_dump(), slot.condition.model_dump()])
            or request.corpus_id != proof.freeze.scope.corpus_id
            or (request.mode, request.profile_id, request.selector_id) !=
               (slot.condition.mode, slot.condition.profile_id, slot.condition.selector_id)):
        raise ValueError('Slot/policy differs from the authorized durable study')
    proof.used_slots.add(slot.slot_index)
    key = SlotPermit()
    _SLOTS[key] = (proof.freeze, fingerprint(request.model_dump(mode='json')), False)
    return key


def validate_slot(permit: SlotPermit, request, settings, context_tokens: int, output_tokens: int,
                  minimum_similarity: float, *, consume: bool = False) -> MatchedFreeze:
    """Recheck request/runtime identity; copied, reused and arbitrary objects fail closed."""
    if permit not in _SLOTS:
        raise ValueError('Matched generation requires an issued one-slot permit')
    freeze, request_sha, used = _SLOTS[permit]
    if (used or request_sha != fingerprint(request.model_dump(mode='json'))
            or settings.neo4j_uri != freeze.scope.target_uri
            or settings.generation_provider != freeze.generator_provider
            or settings.generation_model != freeze.generator_model
            or settings.ollama_base_url != freeze.ollama_base_url
            or settings.max_retries != 0 or settings.max_concurrency != 1
            or settings.request_timeout_seconds != freeze.request_timeout_seconds
            or settings.graph_query_timeout_seconds != freeze.graph_query_timeout_seconds
            or (context_tokens, output_tokens, minimum_similarity) !=
               (freeze.plan.context_tokens, freeze.plan.output_tokens, freeze.minimum_similarity)):
        raise ValueError('Matched slot is consumed or request/runtime controls changed')
    if consume:
        _SLOTS[permit] = (freeze, request_sha, True)
    return freeze
