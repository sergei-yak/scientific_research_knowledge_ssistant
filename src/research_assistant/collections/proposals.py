"""Explicit local draft extraction with cumulative PDF-wide reservations and no approval."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from research_assistant.collections.reviews import _register
from research_assistant.collections.workspace import verify_collection
from research_assistant.contracts import fingerprint
from research_assistant.extraction.contracts import ExtractionResponse
from research_assistant.extraction.pilot import PROMPT
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.llm import create_client
from research_assistant.pipeline import code_identity

PRIOR_FILE = Path(__file__).resolve().parents[3]/'manifests/user-review-prior-usage-v1.json'
POLICY = {'format':'user-claim-extraction-v1','max_requests':8,'max_candidates':12,'max_passages':8,
          'candidates_per_request':2,'context_tokens':4096,'output_tokens':1024,
          'concurrency':1,'automatic_retries':0,'paid_spend':0}


def prior_usage() -> dict:
    """Keep prior public-source reservations; missing inheritance metadata never means a reset."""
    value = json.loads(PRIOR_FILE.read_bytes())
    if value['format'] != 'user-review-prior-usage-v1':
        raise ValueError('Unsupported prior extraction accounting')
    return value


def extraction_budget(registry, source_sha256: str) -> dict:
    """Replay a PDF-wide hash chain across collection, metadata, prompt and export changes."""
    directory = registry._path('extraction',source_sha256)
    inherited = prior_usage()
    prior = inherited['sources'].get(source_sha256,{'requests':0,'candidates':0,'passages':0})
    config = {'policy':POLICY,'prior_manifest_sha256':fingerprint(inherited),'source_sha256':source_sha256}
    if (directory/'config.json').exists():
        if json.loads((directory/'config.json').read_bytes()) != config:
            raise ValueError('Extraction policy/history changed; preserve it for investigation')
    elif directory.exists() and any(directory.iterdir()):
        raise ValueError('Extraction configuration missing; accounting cannot reset')
    events,previous = [],'0'*64
    for number,path in enumerate(sorted((directory/'events').glob('*.json')),1):
        registry._path('extraction',source_sha256,'events',path.name)
        event = json.loads(path.read_bytes())
        digest = event.pop('sha256')
        if event['sequence'] != number or event['previous_sha256'] != previous or fingerprint(event) != digest:
            raise ValueError('Extraction journal chain changed')
        events.append({**event,'sha256':digest})
        previous = digest
    starts = {e['payload']['id']:e['payload'] for e in events if e['kind']=='reserved'}
    ends = {e['payload']['id']:e['payload'] for e in events if e['kind']=='completed'}
    if any(e['kind'] not in {'reserved','completed'} for e in events) or not set(ends)<=set(starts):
        raise ValueError('Invalid extraction journal event')
    used = prior['candidates'] + sum(ends[key]['generated'] if key in ends and ends[key]['status']=='completed'
                                   else row['allowance'] for key,row in starts.items())
    passages = {row['chunk_id'] for row in starts.values()}
    return {'requests_remaining':max(0,8-prior['requests']-len(starts)),
        'candidates_remaining':max(0,12-used),'passages_remaining':max(0,8-prior['passages']-len(passages)),
        'passages':sorted(passages),'unknown_attempts':len(set(starts)-set(ends)),
        'events':events,'config':config,'directory':directory,'attempts':list(ends.values())}


def _append(registry, source_sha256, kind, payload) -> None:
    """Caller holds the workspace operation lock; reservation is durable before inference."""
    budget = extraction_budget(registry,source_sha256)
    directory = budget['directory']
    if not (directory/'config.json').exists(): registry._write(directory/'config.json',budget['config'])
    events = budget['events']
    row = {'sequence':len(events)+1,'previous_sha256':events[-1]['sha256'] if events else '0'*64,
           'kind':kind,'payload':payload}
    row['sha256'] = fingerprint(row)
    registry._write(directory/'events'/f'{len(events)+1:06d}.json',row)


def extract_proposals(registry, collection_id, expected_head, chunk_id, settings, *, client_factory=None) -> dict:
    """One deliberate local request; retain empty, invalid, failed and interrupted reservations."""
    if settings.extraction_provider != 'ollama':
        raise ValueError('User-collection draft extraction currently requires the configured local provider; no paid allowance')
    with registry.query_lock():
        ready = verify_collection(registry,collection_id,settings,expected_head)
        chunks = load_corpus_chunks(ready.collection.corpus_id)
        chunk = chunks.get(chunk_id)
        if chunk is None: raise ValueError('Extraction passage is outside this collection')
        budget = extraction_budget(registry,chunk.source_sha256)
        if not budget['requests_remaining'] or not budget['candidates_remaining']:
            raise ValueError('Cumulative PDF extraction allowance exhausted, including prior curated-source attempts')
        if chunk_id not in budget['passages'] and not budget['passages_remaining']:
            raise ValueError('Cumulative PDF passage allowance exhausted')
        client = (client_factory or create_client)(settings,4096,1024,purpose='extraction')
        client.prompt_version = 'user-claim-extraction-v1'
        identifier = uuid4().hex
        allowance = min(2,budget['candidates_remaining'])
        paper = next(p for p in ready.snapshot['papers'] if p['paper_id']==chunk.paper_id)
        messages = [{'role':'system','content':PROMPT},{'role':'user','content':json.dumps({
            'paper_id':chunk.paper_id,'title':paper['title'],'document_type':paper['document_type'],
            'maximum_candidates':allowance,'passage':{'id':chunk.chunk_id,'page':chunk.page,'text':chunk.text}},ensure_ascii=False)}]
        _append(registry,chunk.source_sha256,'reserved',{'id':identifier,'chunk_id':chunk_id,'allowance':allowance,
            'recorded_at':datetime.now(timezone.utc).isoformat(),'collection_marker':ready.marker,
            'messages':messages,'model':client.model,'digest':client.digest,'code':code_identity()})
        try:
            draft,result = client.generate_structured(ExtractionResponse,messages)
            draft = ExtractionResponse.model_validate(draft.model_dump())
            if len(draft.candidates)>allowance: raise ValueError('Model exceeded candidate allowance')
            outcome = {'id':identifier,'status':'completed','generated':len(draft.candidates),
                'draft':draft.model_dump(),'generation':result.model_dump(mode='json')}
        except Exception as exc:
            result = getattr(client,'last_result',None)
            outcome = {'id':identifier,'status':'failed','generated':0,'error':type(exc).__name__,
                'message':settings.redact(str(exc)),'generation':result.model_dump(mode='json') if result else None}
        _append(registry,chunk.source_sha256,'completed',outcome)
        if outcome['status'] != 'completed':
            return {**{k:outcome[k] for k in ('id','status','message')},'claims':[]}
        revisions = [_register(registry,ready,candidate,chunk_id,{},None,None,
                     'Local model proposal from extraction '+identifier) for candidate in draft.candidates]
        return {'id':identifier,'status':'completed','claims':[r.claim_id for r in revisions],
                'no_claim_reason':draft.no_claim_reason,'approved':0}
