"""Opt-in real pinned CPU model contracts; no graph mutation, gold or generation."""
import json
import os
from pathlib import Path

import pytest

from research_assistant.contracts import fingerprint
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.reranker import RerankerError,pinned_scorer,verified_manifest,model_identity


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_RERANKER_SMOKE')!='1',reason='Set RUN_RERANKER_SMOKE=1 for cached pinned CPU inference')
def test_real_scalar_scores_native_limit_repeatability_and_fail_closed(monkeypatch):
    manifest=verified_manifest();scorer=pinned_scorer()
    pairs=[('Which planet is red?','Mars is called the Red Planet.'),('Which planet is red?','Venus has a thick atmosphere.')]
    values,lengths=scorer.score_pairs(pairs)
    reverse,_=scorer.score_pairs(list(reversed(pairs)))
    assert values==list(reversed(reverse))
    assert all(1<=n<=512 for n in lengths)
    calls=[];forward=scorer.model.forward
    def counted(*args,**kwargs):calls.append(1);return forward(*args,**kwargs)
    monkeypatch.setattr(scorer.model,'forward',counted)
    with pytest.raises(RerankerError,match='512-token') as error:
        scorer.score_pairs([pairs[0],('q','word '*509)])
    assert not calls and error.value.selection_diagnostics['new_pairs_inferred']==0
    _,boundary=scorer.score_pairs([('q','word '*508)])
    assert boundary==[512]
    if os.getenv('RERANKER_REPORT'):
        write_immutable(Path(os.environ['RERANKER_REPORT']),json.dumps({'task_id':'M5.3','model_identity':model_identity(manifest),
            'manifest_sha256':fingerprint(manifest.model_dump()),'synthetic_pairs':pairs,'raw_logits':values,
            'native_pair_lengths':lengths,'exact_pool_order_repeatability':True,'512_token_boundary_passed':True,
            'overlength_rejected_before_any_inference':True,'generation_calls':0,'private_access':False},indent=2)+'\n')
