"""Shared cross-mode candidate features, deterministic score cache, ties and trace accounting."""
from __future__ import annotations

import math
import time

from research_assistant.contracts import CandidateTrace,Chunk,EvidenceItem,fingerprint
from research_assistant.retrieval.catalog import ReviewCatalog,checked_fact,chunk_evidence
from research_assistant.retrieval.evidence import estimate_tokens,render_context
from research_assistant.retrieval.reranker import FEATURE_SHA256,PairScorer,RerankerError


def canonical_text(item: EvidenceItem,chunks: dict[str,Chunk],catalog: ReviewCatalog | None) -> str:
    """Use exact shared source/fact representations; never packed clipping or graph metadata."""
    if item.kind=='approved_fact':return checked_fact(item,catalog)['embedding_text']
    chunk=chunks.get(item.id)
    if chunk is None or item.excerpts!=chunk_evidence(chunk).excerpts:
        raise RerankerError('Reranker raw feature differs from the exact full source chunk')
    return chunk.text


class SelectorSession:
    """One question's cache counts seed and graph scoring against one 88-candidate bound."""
    def __init__(self,question: str,chunks: dict[str,Chunk],catalog: ReviewCatalog | None,scorer: PairScorer):
        self.question=question;self.chunks=chunks;self.catalog=catalog;self.scorer=scorer
        self.features: dict[str,str]={};self.cache: dict[str,tuple[float,int]]={}
        self.scores: dict[str,float]={};self.stages: dict[str,dict]={}
        self.pairs_inferred=0

    def order(self,items: list[EvidenceItem],baseline_ranks: dict[str,int],stage: str) -> list[EvidenceItem]:
        """Score exact features once, then sort relevance/rank/ID without origin preferences."""
        start=time.perf_counter()
        ids=[i.id for i in items]
        if len(set(ids))!=len(ids):raise RerankerError('Duplicate candidate identities passed to selector')
        if len(set(ids)|set(self.features))>88:raise RerankerError('88 unique candidate identities per question exceeded')
        keys={};pending={}
        for item in items:
            text=canonical_text(item,self.chunks,self.catalog)
            key=fingerprint([self.question,text])
            if item.id in self.features and self.features[item.id]!=key:
                raise RerankerError('Candidate canonical feature changed within a request')
            keys[item.id]=key
            if key not in self.cache:pending.setdefault(key,(self.question,text))
        try:
            values,lengths=self.scorer.score_pairs(list(pending.values())) if pending else ([],[])
            if (len(values)!=len(pending) or len(lengths)!=len(pending)
                    or any(not math.isfinite(v) for v in values) or any(not 1<=n<=512 for n in lengths)):
                raise RerankerError('Reranker score/length result violates the shared contract')
        except Exception as exc:
            details=getattr(exc,'selection_diagnostics',{'status':'failed','stage':'inference'})
            raise RerankerError(str(exc),{**details,'selection_stage':stage,'previous_pairs_inferred':self.pairs_inferred,
                'requested_new_pairs':len(pending),'candidate_ids':ids,'feature_policy_sha256':FEATURE_SHA256}) from exc
        self.cache.update({key:(value,length) for key,value,length in zip(pending,values,lengths)})
        self.pairs_inferred+=len(pending)
        self.features.update(keys)
        self.scores.update({identity:self.cache[key][0] for identity,key in keys.items()})
        ordered=sorted(items,key=lambda i:(-self.scores[i.id],baseline_ranks.get(i.id,float('inf')),i.id))
        self.stages[stage]={'rows':[{'id':item.id,'feature_sha256':keys[item.id],
            'score':self.scores[item.id],'native_pair_tokens':self.cache[keys[item.id]][1],
            'baseline_rank':baseline_ranks.get(item.id),'rank_after':rank}
            for rank,item in enumerate(ordered,1)],'new_pairs_inferred':len(pending),
            'cache_hits':len(items)-len(pending),'elapsed_ms':(time.perf_counter()-start)*1000}
        return ordered

    def audit(self,items: list[EvidenceItem],baseline_ranks: dict[str,int],stage: str,decisions: list[dict]) -> dict:
        """Bind real shared-packer exclusions to the exact scoring stage, including empty pools."""
        decision_by_id={d['id']:d for d in decisions}
        rows={r['id']:r for r in self.stages[stage]['rows']}
        trace=[]
        for item in items:
            row=rows[item.id];decision=decision_by_id[item.id]
            trace.append(CandidateTrace(candidate_id=item.id,origins=[item.retrieval_origin],
                baseline_member=item.id in baseline_ranks,approval_source_checks={'source':True,
                    **({'current_approval':True} if item.kind=='approved_fact' else {})},route=item.graph_paths,
                score=row['score'],rank_before=baseline_ranks.get(item.id),rank_after=row['rank_after'],
                selected=decision['selected'],exclusion_reason=decision['reason'],units=int(decision['selected']),
                estimated_tokens=estimate_tokens(render_context([item])[0])).model_dump())
        self.stages[stage]['candidate_trace']=trace
        return self.snapshot()

    def snapshot(self) -> dict:
        """Return score provenance separately from unchanged generator-context serialization."""
        return {'selector_id':'cross_encoder','feature_policy_sha256':FEATURE_SHA256,'score_policy':'raw-logit-fp32-v1',
                'unique_candidates':len(self.features),'pairs_inferred':self.pairs_inferred,'pair_limit':88,
                'stages':self.stages}
