"""Optional source-bound review UI; eligibility, mutation and provider rules live in services."""

import json

import streamlit as st

from research_assistant.collections.proposals import extract_proposals, extraction_budget
from research_assistant.collections.reviews import (
    UIResponse, present_claim, propose_claim, publish_review, record_decision, review_status,
)
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.review.store import state


def review_panel(registry, ready, settings, encoder_factory, error_message) -> dict:
    """Every mutation requires an explicit submit; opening/rerunning the panel does no inference."""
    status = review_status(registry,ready,settings)
    collection = ready.collection
    selection = (collection.collection_id,collection.sha256,status['review_head'])
    if st.session_state.get('user_review_selection') != selection:
        if st.session_state.get('user_review_selection') is not None:
            st.session_state.pop('user_run',None)
        st.session_state.pop('review_presentation',None)
        st.session_state['user_review_selection'] = selection
    with st.expander('Review claims and connections (optional)'):
        st.write('Check small proposed claims against their PDF quotations. Approving means the paper reports the claim; it does not prove the science is correct.')
        st.caption(f"{status['claims']} proposals · {status['approved']} eligible approvals. " +
                   ('Reviewed index is current.' if status['ready'] else status['reason']))
        notice = st.session_state.get('review_notice')
        if notice and notice[0] == collection.collection_id:
            st.info(notice[1])
        st.markdown('**1. Create or correct proposals**')
        chunks = load_corpus_chunks(collection.corpus_id)
        paper_ids = [d.paper_id for d in collection.documents]
        paper = st.selectbox('Proposal source paper',paper_ids,
            format_func=lambda key: ready.sources[key].reference, key='review_paper_'+collection.collection_id)
        pages = sorted({c.page for c in chunks.values() if c.paper_id==paper})
        page = st.selectbox('Proposal PDF page',pages,key='review_page_'+paper)
        choices = [c for c in chunks.values() if c.paper_id==paper and c.page==page]
        chunk_id = st.selectbox('Source passage',[c.chunk_id for c in choices],
            format_func=lambda key: chunks[key].text[:100],key='review_chunk_'+paper+'_'+str(page))
        chunk = chunks[chunk_id]
        source = ready.sources[paper]
        st.caption(f'{source.reference} · PDF page {chunk.page} · normalized page offsets {chunk.page_start}–{chunk.page_end}')
        st.text(chunk.text)
        if source.web_url:
            st.link_button('Open proposal source page',source.web_url+f'#page={page}')
        st.download_button('Download proposal source PDF',source.data,file_name=source.filename,
                           mime='application/pdf',key='review_source_pdf')
        budget = extraction_budget(registry,chunk.source_sha256)
        st.caption(f"Local draft allowance left for these PDF bytes: {budget['requests_remaining']} requests / {budget['candidates_remaining']} candidates. Prior curated-source attempts count. Failed/unknown calls retain reservations.")
        if st.button('Propose claims with local model',disabled=not budget['requests_remaining'] or not budget['candidates_remaining']):
            st.session_state.pop('user_run',None)
            try:
                with st.spinner('Preparing unapproved draft claims…'):
                    result = extract_proposals(registry,collection.collection_id,collection.sha256,chunk_id,settings)
                detail = (f"Prepared {len(result['claims'])} unapproved drafts. " + (result.get('no_claim_reason') or '')
                          if result['status']=='completed' else 'Draft request failed: '+result['message'])
                st.session_state['review_notice'] = (collection.collection_id,detail)
                st.rerun()
            except Exception as exc: st.error(error_message(exc,settings))
        if st.checkbox('Enter or correct a proposal manually',key='show_editor_'+collection.collection_id):
            editor(registry,ready,status,chunk_id,settings,error_message)
        if status['claims']:
            st.markdown('**2. Review a saved proposal**')
            review_claim(registry,ready,status,settings,error_message)
            st.markdown('**3. Update the reviewed index**')
            st.write('After decisions or corrections, update the reviewed index. Until it matches the journal, fact/Graph queries are blocked. Rejected and pending claims never enter it.')
            if st.button('Update reviewed index'):
                st.session_state.pop('user_run',None)
                try:
                    with st.spinner('Updating approved evidence and connections…'):
                        result = publish_review(registry,collection.collection_id,collection.sha256,
                            status['review_head'],settings,encoder_factory=encoder_factory)
                    st.session_state['review_notice'] = (collection.collection_id,
                        f"Reviewed index updated: {result['verified_active_facts']} active approved claims.")
                    st.rerun()
                except Exception as exc: st.error(error_message(exc,settings))
    return status


def editor(registry,ready,status,chunk_id,settings,error_message) -> None:
    """The exact selected quotation plus explicit entity identities define a new unapproved revision."""
    current = state(registry.review_directory(ready.collection))
    selected_paper = load_corpus_chunks(ready.collection.corpus_id)[chunk_id].paper_id
    old = st.selectbox('Correct an existing claim',[None]+[r.claim_id for r in current['current'].values()
        if r.paper.paper_id==selected_paper],format_func=lambda key: 'New proposal' if key is None else current['current'][key].draft.statement[:90])
    prior = current['current'][old] if old else None
    draft = prior.draft if prior else None
    with st.form('proposal_editor_'+(prior.sha256 if prior else chunk_id)):
        kind = st.selectbox('Claim type',['finding','evaluation'],index=1 if draft and draft.kind=='evaluation' else 0)
        statement = st.text_area('Proposed claim',value=draft.statement if draft else '',max_chars=600)
        quotes = st.text_area('Exact quotation(s), separate with a line containing ---',
                             value='\n---\n'.join(draft.quotes) if draft else '',max_chars=1100)
        fields,bindings = {},{}
        for entity_kind in ('method','dataset'):
            fields[entity_kind] = st.text_input(entity_kind.title()+' name (blank means unknown)',value=getattr(draft,entity_kind) or '' if draft else '')
            fields[entity_kind+'_aliases'] = st.text_input(entity_kind.title()+' aliases (one per semicolon)',value=';'.join(getattr(draft,entity_kind+'_aliases')) if draft else '')
            values = [e for e in current['entities'].values() if e.kind==entity_kind]
            bindings[entity_kind] = st.selectbox('Use existing '+entity_kind+' identity',[None]+[e.id for e in values],
                format_func=lambda key: 'Paper-scoped identity' if key is None else next(e.name+' · '+e.id for e in values if e.id==key))
        conditions = st.text_area('Reported conditions as JSON (unknown values are null)',value=json.dumps(draft.conditions if draft else {
            'dataset_version':None,'split':None,'metric':None,'protocol':None}))
        st.caption('Sharing an existing identity is an explicit proposal, never a name-based merge. Copy its exact name/aliases; the reviewer sees the binding. Evaluation means this paper’s own method/dataset experiment; findings may describe a design or limitation.')
        submit = st.form_submit_button('Save unapproved proposal')
    if submit:
        st.session_state.pop('user_run',None)
        try:
            candidate = ProposedClaim(kind=kind,statement=statement,quotes=quotes.split('\n---\n'),conditions=json.loads(conditions),
                **{key:(value.strip() or None) if key in {'method','dataset'} else [v.strip() for v in value.split(';') if v.strip()]
                   for key,value in fields.items()})
            propose_claim(registry,ready.collection.collection_id,ready.collection.sha256,candidate,chunk_id,settings,
                entity_ids={k:v for k,v in bindings.items() if v},supersedes=old,
                expected_revision=prior.sha256 if prior else None)
            st.session_state['review_notice'] = (ready.collection.collection_id,'Proposal saved. It needs its own human review; earlier approval is not inherited.')
            st.rerun()
        except Exception as exc: st.error(error_message(exc,settings))


def review_claim(registry,ready,status,settings,error_message) -> None:
    """Display the complete exact revision before the blank human decision form."""
    current = state(registry.review_directory(ready.collection))
    claim_id = st.selectbox('Claim to review',list(current['current']),
        format_func=lambda key: current['current'][key].draft.statement[:100])
    cached = st.session_state.get('review_presentation')
    if not cached or cached.revision.claim_id!=claim_id or cached.review_head!=status['review_head']:
        cached = present_claim(registry,ready.collection.collection_id,ready.collection.sha256,claim_id,settings)
        st.session_state['review_presentation'] = cached
    revision = cached.revision
    st.markdown('**Exact proposal for review**')
    st.text(revision.draft.statement)
    st.caption(f'Revision {revision.revision} · binding {revision.sha256} · reporting source {ready.sources[revision.paper.paper_id].reference}')
    st.caption('Claim type: '+revision.draft.kind+'. Check attribution and whether the statement overstates its evidence.')
    st.table([{'Reported condition':key.replace('_',' ').title(),'Value':value or 'unknown'}
              for key,value in revision.draft.conditions.items()])
    if revision.entities:
        st.table([{'Type':e.kind,'Name':e.name,'Aliases':'; '.join(e.aliases) or 'none',
            'Relationship':('OF_METHOD' if e.kind=='method' else 'ON_DATASET') if revision.draft.kind=='evaluation'
                            else ('ABOUT_METHOD' if e.kind=='method' else 'MENTIONS'),
            'Exact identity':e.id} for e in revision.entities])
    else:
        st.caption('No method/dataset identity is proposed. This claim does not connect papers through a named method or dataset.')
    for quote in revision.draft.quotes: st.text('Proposed exact quotation: '+quote)
    for excerpt in cached.excerpts:
        st.caption(f'PDF page {excerpt.page} · chunk offsets {excerpt.start}–{excerpt.end}')
        st.text(excerpt.text)
        source = ready.sources[excerpt.paper_id]
        if source.web_url: st.link_button('Open review source · p. '+str(excerpt.page),source.web_url+f'#page={excerpt.page}')
        st.download_button('Download review PDF · p. '+str(excerpt.page),source.data,file_name=source.filename,
            mime='application/pdf',key='review_pdf_'+excerpt.chunk_id+'_'+str(excerpt.start))
    if cached.errors: st.warning('Cannot approve until corrected: '+'; '.join(cached.errors))
    else: st.caption('Exact-source checks passed. Semantic support and attribution still need your review.')
    entry = current['decisions'].get((claim_id,revision.revision))
    st.caption('Current human decision: '+(entry[0].decision if entry else 'pending'))
    with st.form('human_decision_'+cached.sha256):
        reviewer = st.text_input('Reviewer name',max_chars=160)
        choice = st.selectbox('Your decision',['approved','rejected','needs_review'],index=None,
            format_func=lambda v:{'approved':'Approve','rejected':'Reject','needs_review':'Needs review'}[v])
        reason = st.text_area('Your reason',max_chars=2000)
        seconds = st.text_input('Review time in seconds (blank if not measured)')
        confirm = st.checkbox('I reviewed this exact claim, source quotations, conditions and entity/relationship bindings')
        st.caption('A timezone-aware submission timestamp is recorded automatically. Blank time remains unknown. This is your human decision; no automatic approval is supplied.')
        submit = st.form_submit_button('Save my decision')
    if submit:
        st.session_state.pop('user_run',None)
        try:
            response = UIResponse(presentation_sha256=cached.sha256,reviewer=reviewer,decision=choice,
                reason=reason,confirmed=confirm,review_seconds=float(seconds) if seconds.strip() else None)
            record_decision(registry,ready.collection.collection_id,ready.collection.sha256,cached,response,settings)
            st.session_state['review_notice'] = (ready.collection.collection_id,'Decision saved. Update the reviewed index before using facts or graph connections.')
            st.rerun()
        except Exception as exc: st.error(error_message(exc,settings))
