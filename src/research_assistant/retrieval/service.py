"""Controlled retrieval conditions; graph expansion never changes review or gold data."""

import json
import time
from pathlib import Path

from research_assistant.contracts import CandidateTrace, Chunk, EvidenceItem, QueryRequest, RetrievalResult, text_sha
from research_assistant.embeddings import Encoder
from research_assistant.graph.repository import GraphRepository
from research_assistant.graph.search import SearchRepository
from research_assistant.graph.templates import traversal_templates
from research_assistant.ingestion.sources import load_corpus_chunks, verified_chunk
from research_assistant.retrieval.catalog import ReviewCatalog, alias_matches, chunk_evidence, cosine, evidence_text, load_catalog
from research_assistant.retrieval.evidence import assemble_evidence
from research_assistant.retrieval.evidence import estimate_tokens, render_context
from research_assistant.retrieval.anchors import graph_anchors
from research_assistant.retrieval.profiles import reference_profile, validate_scope
from research_assistant.retrieval.ranking import reciprocal_rank_fusion
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings

RULES_VERSION = 'controlled-retrieval-v1'


def packed(mode: str, items: list[EvidenceItem], started: float, audit: dict,
           effective: str | None = None, reason: str | None = None) -> RetrievalResult:
    """Use the single shared renderer/packer for all added retrieval conditions."""
    selected, context, aliases, tokens, decisions = assemble_evidence(items)
    return RetrievalResult(requested_mode=mode, effective_mode=effective or mode, fallback_reason=reason,
        evidence=selected, context=context, context_sha256=text_sha(context), estimated_tokens=tokens,
        aliases=aliases,candidates=decisions,retrieval_ms=(time.perf_counter()-started)*1000,audit=audit)


def retrieve_modes(request: QueryRequest, repo: SearchRepository, encoder, chunks: dict[str, Chunk],
                   catalog: ReviewCatalog | None, encoder_revision: str, timeout: float = 30,
                   *, profile_id: str = 'baseline', scope_id: str | None = None) -> RetrievalResult:
    """Fuse fixed channel rankings, then optionally traverse and select under identical context limits."""
    if request.mode not in {'hybrid','hybrid_facts','graph'}:
        raise ValueError('Use the preserved M1 service for vector mode')
    if profile_id not in {'baseline','retrieval-v2'} or (profile_id=='retrieval-v2' and not scope_id):
        raise ValueError('Unknown or unscoped retrieval profile')
    if request.mode != 'hybrid' and (catalog is None or catalog.corpus_id != request.corpus_id):
        raise ValueError('Fact modes require a matching current review catalog')
    started = time.perf_counter()
    query = encoder.encode([request.question])[0]
    cosine(query,query)
    head = catalog.head if catalog else None
    audit = {'rules_version':RULES_VERSION,'review_head':head,'rrf_k':60,'channel_rankings':{},
             'query_timeout_seconds':timeout,'ann_pool':24,'channel_limit':12,
             'evidence_unit_limit':6,'estimated_token_limit':1800,'lexical_term_limit':128}
    items, vectors, rankings = {}, {}, []
    with repo.reading(request.corpus_id,head,timeout):
        repo.check_indexes(request.corpus_id,catalog is not None)
        fact_vectors = (repo.fact_vectors(catalog,chunks,encoder_revision,strict_roles=True)
                        if catalog and profile_id=='retrieval-v2' else repo.fact_vectors(catalog,chunks,encoder_revision) if catalog else {})
        for kind in (['chunk','fact'] if catalog else ['chunk']):
            for channel in ('vector','text'):
                rows = repo.ranked(request.corpus_id,kind,channel,query,request.question,encoder_revision,list(fact_vectors))
                ranking = []
                for row in rows:
                    identity = row['id']
                    if kind=='chunk':
                        source = verified_chunk(row['source'],chunks)
                        if source.chunk_id != identity:
                            raise ValueError('Retrieved chunk differs from the immutable source cache')
                        item = chunk_evidence(source)
                    else:
                        if identity not in catalog.facts:
                            raise ValueError('Search returned a fact outside current human approval')
                        item = EvidenceItem.model_validate(catalog.facts[identity]['evidence'])
                    item.similarity = row['similarity']
                    items[identity],vectors[identity] = item,row['vector']
                    ranking.append(identity)
                rankings.append(ranking)
                audit['channel_rankings'][kind+'_'+channel] = [
                    {'id':r['id'],'native_score':r['score'],'cosine':r['similarity']} for r in rows]
        fusion = reciprocal_rank_fusion(rankings,k=60)
        baseline = []
        for rank,(identity,score) in enumerate(fusion,1):
            item = items[identity].model_copy(deep=True,update={'rank':rank})
            baseline.append(item)
        audit['fusion'] = [{'id':identity,'rrf_score':score} for identity,score in fusion]
        baseline_result = packed(request.mode,baseline,started,audit)
        if request.mode != 'graph':
            return baseline_result
        pool = {item.id:item for item in baseline}
        question_entities = alias_matches(request.question,catalog.entities)
        seeds = baseline_result.evidence[:4]
        audit['baseline_context_sha256'] = baseline_result.context_sha256
        audit['seed_ids'] = [item.id for item in seeds]
        seed_entities = set().union(*(alias_matches(evidence_text(item),catalog.entities) for item in seeds))
        # Resolve fallback separately for methods and datasets: a method mention must not
        # suppress a reviewed dataset shown in the seed (or vice versa).
        expansion_by_kind = {}
        for kind in ('method','dataset'):
            explicit = {key for key in question_entities if catalog.entities[key].kind==kind}
            shown = {key for key in seed_entities if catalog.entities[key].kind==kind}
            expansion_by_kind[kind] = sorted(explicit or shown)
        if profile_id=='retrieval-v2':
            from research_assistant.graph.templates_v2 import traversal_templates_v2
            anchors,question_entities,seed_entities,expansion_by_kind=graph_anchors(request.question,baseline_result.evidence,catalog)
            templates=traversal_templates_v2(request.corpus_id)
            audit['anchors']=anchors
            audit['seed_ids']=[a['id'] for a in anchors if a['type']=='evidence']
        else:
            anchors=[{'id':s.id,'type':'evidence','paper_id':s.paper_ids[0],'chunk_ids':s.source_chunk_ids} for s in seeds]
            templates=traversal_templates(request.corpus_id)
        expansion_entities = set().union(*map(set,expansion_by_kind.values()))
        graph, calls = {}, []
        row_outcomes=[]
        for anchor in anchors:
            params = {'project':repo.project,'corpus':request.corpus_id,'head':head,
                      'seed_paper':anchor.get('paper_id',''),'seed_chunks':anchor.get('chunk_ids',[]),
                      'entity_ids':sorted(expansion_entities),'fact_ids':sorted(catalog.facts)}
            if profile_id=='retrieval-v2':
                params.update(scope_id=scope_id,anchor_type=anchor['type'],anchor_entity_id=anchor.get('entity_id',''),
                              anchor_entity_node=anchor.get('entity_node',''))
            for template in templates:
                if anchor['type']=='entity' and template!='shared_'+anchor['kind']:
                    continue
                rows,_ = (repo.traverse(request.corpus_id,template,params,profile_id=profile_id)
                          if profile_id=='retrieval-v2' else repo.traverse(request.corpus_id,template,params))
                if len(rows)>5:raise ValueError('Graph template exceeded its union-wide row bound')
                calls.append({'seed_id':anchor['id'],'template':template,'parameters':params,'rows':rows})
                for row in rows:
                    identity = row['fact_id']
                    fact = catalog.facts.get(identity)
                    if (fact is None or row['reporting_paper'] != fact['paper_id']
                            or row['claim_id'] != fact['claim_id'] or row['revision'] != fact['claim_revision']
                            or row['support_chunk'] not in fact['evidence']['source_chunk_ids']):
                        raise ValueError('Graph target failed current approval/source ownership checks')
                    path = {'template':template,'node_ids':row['node_ids'],'entity_ids':row['entity_ids'],
                            'direction':row['direction'],'length':len(row['node_ids'])-1,
                            'reporting_paper_id':row['reporting_paper']}
                    if not 1 <= path['length'] <= 5:
                        raise ValueError('Graph route exceeded the fixed path bound')
                    previous = graph.get(identity)
                    row_outcomes.append({'id':identity,'anchor':anchor['id'],'template':template,
                                         'duplicate':previous is not None,'baseline_member':identity in pool})
                    if previous is None or (path['length'],json.dumps(path,sort_keys=True)) < (
                            previous['length'],json.dumps(previous,sort_keys=True)):
                        graph[identity] = path
        audit.update(question_entity_ids=sorted(question_entities),seed_entity_ids=sorted(seed_entities),
                     expansion_entities_by_kind=expansion_by_kind,
                     expansion_entity_ids=sorted(expansion_entities),graph_calls=calls,
                     graph_rows=sum(len(c['rows']) for c in calls),graph_candidate_limit=40)
        if len(calls)>16 or audit['graph_rows']>80:
            raise ValueError('Graph expansion exceeded the frozen seed/template bound')
        for identity in graph:
            if identity not in pool:
                pool[identity] = EvidenceItem.model_validate(catalog.facts[identity]['evidence']).model_copy(
                    update={'retrieval_origin':'graph','graph_paths':[graph[identity]]})
                vectors[identity] = fact_vectors[identity]

        def rank_key(identity):
            item = pool[identity]
            overlap = len(question_entities & alias_matches(evidence_text(item),catalog.entities))
            similarity = cosine(query,vectors[identity])
            length = item.graph_paths[0]['length'] if item.graph_paths else 0
            return (-overlap,-similarity,length,item.rank if item.rank else float('inf'),identity)

        keys = {identity:rank_key(identity) for identity in pool}
        graph_ids = sorted(graph,key=keys.__getitem__)[:40]
        baseline_ids = {item.id for item in baseline}
        new_ids = set(graph_ids)-baseline_ids
        audit['graph_candidates_retained'] = graph_ids
        merged = sorted(baseline_ids | set(graph_ids),key=keys.__getitem__)
        audit['merged_ranking'] = [{'id':identity,'question_entity_overlap':-keys[identity][0],
                                    'cosine':-keys[identity][1],'path_length':keys[identity][2],
                                    'baseline_rank':pool[identity].rank} for identity in merged]
        result = packed('graph',[pool[identity] for identity in merged],started,audit)
        if profile_id=='retrieval-v2':
            decisions={d['id']:d for d in result.candidates}
            ranks={identity:rank for rank,identity in enumerate(merged,1)}
            audit['graph_row_outcomes']=row_outcomes
            audit['pre_fallback_candidate_trace']=[CandidateTrace(
                candidate_id=identity,origins=(['baseline'] if identity in baseline_ids else [])+(['graph'] if identity in graph else []),
                baseline_member=identity in baseline_ids,approval_source_checks={'source':True,**({'current_approval':True} if identity in catalog.facts else {})},
                route=[graph[identity]] if identity in graph else [],score=-keys[identity][1],rank_before=pool[identity].rank,
                rank_after=ranks.get(identity),selected=decisions.get(identity,{}).get('selected',False),
                exclusion_reason=decisions.get(identity,{}).get('reason','graph_candidate_limit'),
                units=int(decisions.get(identity,{}).get('selected',False)),
                estimated_tokens=estimate_tokens(render_context([pool[identity]])[0])).model_dump()
                for identity in sorted(pool)]
            audit['pre_fallback_selected_ids']=[item.id for item in result.evidence]
            audit['pre_fallback_context_sha256']=result.context_sha256
            audit['trace_token_accounting']='Standalone rendered candidate tokens; not additive context costs'
            audit['generated_rows']=audit['graph_rows']
            audit['unique_graph_candidates']=len(graph)
            audit['new_graph_candidates']=sorted(new_ids)
            audit['selected_graph_additions']=sorted(new_ids & {i.id for i in result.evidence})
            result=result.model_copy(update={'audit':audit})
        if new_ids & {item.id for item in result.evidence}:
            return result
        reason = 'no_new_eligible_graph_candidates' if not new_ids else 'graph_candidates_not_selected_within_budget'
        # Preserve every baseline evidence/context/alias/budget field exactly; audit may explain the attempt.
        return baseline_result.model_copy(update={'effective_mode':'hybrid_facts','fallback_reason':reason,
            'audit':audit,'retrieval_ms':(time.perf_counter()-started)*1000})


def retrieve_request(request: QueryRequest, settings: Settings, review_directory: Path = Path('data/reviews/pilot'),
                     minimum_similarity: float = 0.30, encoder: Encoder | None = None) -> tuple[dict, RetrievalResult]:
    """Entry-point service; no gold loading or generator calls, and no automatic index setup."""
    reference_profile(request.profile_id)
    if request.selector_id!='reference':raise ValueError('Unsupported selector; the model gate has not been completed')
    if request.profile_id=='retrieval-v2':
        return retrieve_scoped(request,settings,review_directory,minimum_similarity,encoder)
    if request.scope_file:
        raise ValueError('Baseline requests must not carry a V2 scope')
    if request.mode=='vector':
        from research_assistant.pipeline import retrieve_vector
        repo = GraphRepository(settings)
        try:
            snapshot = repo.snapshot(request.corpus_id)
            encoder = encoder if encoder is not None else Encoder()
            if snapshot['encoder_revision'] != encoder.revision:
                raise ValueError('Query encoder revision differs from the indexed snapshot')
            return snapshot,retrieve_vector(request,repo,encoder,minimum_similarity)
        finally:
            repo.close()
    repo = SearchRepository(settings)
    try:
        snapshot = repo.snapshot(request.corpus_id)
        chunks = load_corpus_chunks(request.corpus_id)
        encoder = encoder if encoder is not None else Encoder()
        if snapshot['encoder_revision'] != encoder.revision:
            raise ValueError('Query encoder revision differs from the indexed snapshot')
        if request.mode=='hybrid':
            return snapshot,retrieve_modes(request,repo,encoder,chunks,None,encoder.revision,settings.graph_query_timeout_seconds)
        with review_lock(review_directory):
            catalog = load_catalog(review_directory,request.corpus_id,chunks)
            return snapshot,retrieve_modes(request,repo,encoder,chunks,catalog,encoder.revision,settings.graph_query_timeout_seconds)
    finally:
        repo.close()


def retrieve_scoped(request: QueryRequest, settings: Settings, review_directory: Path,
                    minimum_similarity: float, encoder: Encoder | None) -> tuple[dict,RetrievalResult]:
    """Validate physical/current scope before any V2 search, retaining shared retrieval services."""
    profile=reference_profile(request.profile_id)
    chunks=load_corpus_chunks(request.corpus_id)
    with review_lock(review_directory):
        catalog=load_catalog(review_directory,request.corpus_id,chunks)
        repo=SearchRepository(settings)
        try:
            scope=validate_scope(request,settings,review_directory,chunks,catalog,repo)
            snapshot=repo.snapshot(request.corpus_id)
            encoder=encoder if encoder is not None else Encoder()
            if snapshot['encoder_revision']!=encoder.revision:
                raise ValueError('Query encoder revision differs from the indexed snapshot')
            if request.mode=='vector':
                from research_assistant.pipeline import retrieve_vector
                with repo.reading(request.corpus_id,catalog.head,settings.graph_query_timeout_seconds):
                    result=retrieve_vector(request,repo,encoder,minimum_similarity)
            else:
                result=retrieve_modes(request,repo,encoder,chunks,None if request.mode=='hybrid' else catalog,
                    encoder.revision,settings.graph_query_timeout_seconds,profile_id='retrieval-v2',scope_id=scope.scope_id)
            validate_scope(request,settings,review_directory,chunks,catalog,repo)
            result.audit.update(profile=profile.model_dump(),experiment_scope=scope.model_dump(),
                                requested_profile=request.profile_id,effective_profile=request.profile_id,
                                final_selected_ids=[item.id for item in result.evidence])
            return snapshot,result
        finally:
            repo.close()
