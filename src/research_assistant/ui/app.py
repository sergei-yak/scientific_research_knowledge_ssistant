"""Local research workflows using the same services as the CLI."""

import logging
import uuid
from pathlib import Path

import streamlit as st

from research_assistant.contracts import QueryRequest, RunArtifact
from research_assistant.embeddings import Encoder
from research_assistant.pipeline import QueryExecutionError, run_query, write_immutable
from research_assistant.product import WORKFLOWS, known, prepare_output
from research_assistant.product_catalog import CORPORA, MODE_LABELS, WORKFLOW_HELP, FALLBACK_HELP, configured_profiles, product_target
from research_assistant.settings import Settings, configure_caches

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


@st.cache_resource(show_spinner='Loading the cached CPU encoder…')
def cached_encoder() -> Encoder:
    """Share the read-only encoder, never database transactions or query results."""
    return Encoder()


def display_run(run: RunArtifact, settings: Settings,review_directory: Path = Path('data/reviews/pilot')) -> None:
    """Render checked saved request identity, structured views, excerpts and optional synthesis."""
    view, csv_text = prepare_output(run, settings, review_directory=review_directory)
    st.caption(f'Retrieval profile: {run.request.profile_id} · selector: {run.request.selector_id}')
    retrieval = run.retrieval
    st.subheader('Submitted question')
    st.write(run.request.question)
    st.caption(f'Workflow: {run.workflow} · Requested: {retrieval.requested_mode} · Effective: {retrieval.effective_mode}')
    if retrieval.fallback_reason:
        st.info(FALLBACK_HELP[retrieval.fallback_reason])
    st.caption(f'{len(retrieval.evidence)} evidence units · {retrieval.estimated_tokens}/1800 estimated tokens · {retrieval.retrieval_ms:.0f} ms retrieval')
    if view.status == 'partial evidence':
        st.warning('Partial evidence for this workflow. Check the excerpts; do not infer missing information.')
    if view.rows:
        st.subheader('Approved paper claims')
        columns = ['paper', 'method', 'dataset']
        if run.workflow == 'comparison':
            columns.extend(['dataset_version', 'split', 'metric', 'protocol'])
        st.table([{column: row[column] for column in columns} for row in view.rows])
        seen = set()
        for row in view.rows:
            citation = row['citations'].split('; ')[0]
            if (row['paper'], citation) not in seen:
                st.link_button(f'{row["method"]} · {row["paper"]} · reporting source', citation)
                seen.add((row['paper'], citation))
    else:
        st.info('No approved claims selected for this workflow. Raw excerpts may still help answer the question.')
    for notice in view.notices:
        st.caption(notice)
    st.subheader('Generated answer')
    if run.result is None:
        st.info('This profile currently returns evidence only.' if run.request.profile_id=='retrieval-v2'
                else 'Answer not generated. Enable synthesis and submit to request an answer.')
    else:
        if run.result.insufficient_evidence:
            st.warning('The generator reported insufficient evidence.')
        st.text(run.result.answer)
        if run.result.citations:
            st.caption('Cited source cards: ' + ', '.join(citation['evidence_id'] for citation in run.result.citations))
        st.caption('Generated synthesis is separate from approved claims; a valid citation is not a correctness score.')
        if run.generation:
            st.caption(f'{run.generation.provider} · {run.generation.model} · {run.generation.elapsed_ms:.0f} ms · run {run.run_id}')
    st.subheader('Source evidence')
    st.write('Each card contains exact text from a paper. An approved claim is a source-checked summary; the excerpt underneath lets you verify it.')
    st.caption('PDF page numbers are authoritative. Parsed section labels are unverified; figures and numeric tables are not validated.')
    for index, item in enumerate(retrieval.evidence, 1):
        with st.expander(f'E{index} · {"Approved paper claim" if item.kind == "approved_fact" else "Raw excerpt"} · {", ".join(item.paper_ids)}'):
            if item.claim_text:
                st.text(item.claim_text)
                st.caption(f'Claim {item.approved_claim_ids[0]} · revision {item.claim_revision}')
                st.table([{'Reported condition': field.replace('_', ' ').title(), 'Value': known(item.conditions.get(field))} for field in ['method', 'dataset', 'dataset_version', 'split', 'metric', 'protocol']])
            for number, excerpt in enumerate(item.excerpts, 1):
                st.link_button(f'{excerpt.paper_id} · PDF p. {excerpt.page} · source {number}',
                               excerpt.source_url.split('#')[0] + f'#page={excerpt.page}')
                st.text(excerpt.text)
            if item.graph_paths:
                st.write('Graph connection used: this evidence was reached by following reviewed relationships between papers, methods or datasets.')
                for path in item.graph_paths:
                    st.caption(f"Route: {path['template'].replace('_', ' ')}. Reporting paper: {path['reporting_paper_id']}.")
                st.json(item.graph_paths)
    st.subheader('Graph connections used')
    if any(item.graph_paths for item in retrieval.evidence):
        st.write('Connection routes are shown in the source cards above. They explain how evidence was found; they are not extra scientific proof.')
    else:
        st.info('No graph connection was added to this result.' + (' The graph search fell back to Hybrid + Approved Facts.' if retrieval.fallback_reason else ' Other retrieval modes can return source evidence directly.'))
    with st.expander('Run provenance and exact model context'):
        st.caption(f'Corpus {run.request.corpus_id} · context SHA-256 {retrieval.context_sha256}')
        st.json({'requested_mode': retrieval.requested_mode, 'effective_mode': retrieval.effective_mode,
                 'fallback_reason': retrieval.fallback_reason, 'review_head': retrieval.audit.get('review_head'),
                 'code_revision': run.code_revision, 'code_dirty': run.code_dirty})
        st.code(retrieval.context, language='json')
    st.caption('Approval/source checks ran for this display/export. Saved downloads remain historical snapshots. CSV has one row per shown excerpt; escaped_fields identifies reversible spreadsheet protection.')
    st.download_button('Download evidence CSV', csv_text.encode('utf-8-sig'),
                       file_name=f'evidence-{run.run_id}.csv', mime='text/csv', key='csv_download')
    st.download_button('Download run JSON', run.model_dump_json(indent=2).encode('utf-8'),
                       file_name=f'run-{run.run_id}.json', mime='application/json', key='json_download')


def main() -> None:
    """Submit is the sole trigger for retrieval or local generation; reruns only validate/display."""
    st.set_page_config(page_title='Research Evidence Assistant', page_icon='📚', layout='wide')
    configure_caches()
    st.title('Research Evidence Assistant')
    st.write('Discover methods, compare reported studies and inspect limitations with source evidence.')
    try:
        settings = Settings.from_env()
    except Exception:
        logger.error('UI configuration failed; check environment field names/types locally')
        st.error('Configuration is invalid. Check local settings and the console log.')
        return
    corpus_key = st.selectbox('Paper collection', list(CORPORA), format_func=lambda key: CORPORA[key].label)
    profiles = configured_profiles(corpus_key)
    profile = st.selectbox('Retrieval profile', profiles,
        format_func=lambda value: 'Standard' if value == 'baseline' else 'Experimental V2 (evidence only)',
        help='Standard supports live local answers. V2 inspects the broader routes and optional reranker; its synthesis guard remains active.')
    selector = (st.selectbox('Evidence ordering', ['reference', 'cross_encoder'],
        format_func=lambda value: 'Shared reranker' if value == 'cross_encoder' else 'Reference ordering')
        if profile == 'retrieval-v2' else 'reference')
    if corpus_key == 'expanded' and 'retrieval-v2' not in profiles:
        st.caption('The experimental V2 scope remains in its separate research checkout. Standard supports live answers and all four retrieval modes here.')
    workflow = st.selectbox('Workflow', list(WORKFLOWS), format_func=lambda value: value.title())
    st.caption(WORKFLOW_HELP[workflow])
    try:
        collection, target_settings, scope_file = product_target(corpus_key, profile, settings)
    except Exception as exc:
        st.error('Collection is unavailable: ' + settings.redact(str(exc)))
        return
    review_directory = collection.review_directory
    selection = (corpus_key, profile, selector, workflow)
    if st.session_state.get('selection') != selection:
        st.session_state.pop('run', None)
        st.session_state['selection'] = selection
    st.caption(f'{collection.label} | {collection.papers} indexed papers | source-bound human approvals')
    with st.form('query'):
        question = st.text_area('Research question', value=WORKFLOWS[workflow], key=f'question_{workflow}', max_chars=2000)
        mode = st.selectbox('Retrieval mode', list(MODE_LABELS), index=3, format_func=MODE_LABELS.get,
            help='Vector: semantic excerpts. Hybrid: semantic and keyword search. Hybrid + Facts: also reviewed claims. Graph: also follows reviewed connections and explicitly falls back if none is selected.')
        generate = st.checkbox('Generate an answer with the configured model', value=False,
            disabled=profile == 'retrieval-v2', key=f'generate_{profile}')
        if profile == 'retrieval-v2':
            st.caption('Experimental V2 is evidence only. Select Standard for a live answer; no provider or profile is switched automatically.')
        st.caption(f'Configured generator: {settings.generation_provider} / {settings.generation_model}. Context 4096, output limit 512; one request, no automatic retry or provider switching.')
        with st.expander('Collection and technical details'):
            st.code(collection.corpus_id)
            st.caption(f'Review store: {review_directory}. Database: {target_settings.neo4j_uri}.')
            if scope_file:
                st.caption(f'Experimental scope: {scope_file}')
        submitted = st.form_submit_button('Run research query', type='primary')
    if submitted:
        st.session_state.pop('run', None)
        try:
            with st.spinner('Retrieving evidence' + (' and generating an answer…' if generate else '…')):
                request = QueryRequest(question=question.strip(), corpus_id=collection.corpus_id, mode=mode,profile_id=profile,scope_file=scope_file,selector_id=selector)
                run = run_query(request, target_settings, generate=generate, workflow=workflow, encoder=cached_encoder(),review_directory=review_directory)
                write_immutable(Path('runs/ui') / run.run_id / 'run.json', run.model_dump_json(indent=2) + '\n')
                prepare_output(run, target_settings, review_directory=review_directory)
                st.session_state['run'] = run.model_dump(mode='json')
        except Exception as exc:
            if isinstance(exc, QueryExecutionError):
                write_immutable(Path('runs/ui') / exc.artifact.run_id / 'failed-run.json', exc.artifact.model_dump_json(indent=2) + '\n')
            if hasattr(exc,'selection_diagnostics'):
                import json
                write_immutable(Path('runs/ui')/uuid.uuid4().hex/'failed-selection.json',
                    json.dumps({'status':'failed','message':settings.redact(str(exc)),
                                'selection_diagnostics':exc.selection_diagnostics},indent=2)+'\n')
            logger.error('UI query failed: %s', settings.redact(str(exc)))
            st.error('Query failed: ' + settings.redact(str(exc)))
            st.caption('Check service readiness. Submit with synthesis disabled to inspect evidence independently.')
    if 'run' in st.session_state:
        try:
            display_run(RunArtifact.model_validate(st.session_state['run']), target_settings, review_directory=review_directory)
        except Exception as exc:
            logger.error('Stored result validation failed: %s', settings.redact(str(exc)))
            st.error('Saved evidence cannot be validated against current sources/approvals. Rerun the query; export is disabled.')


if __name__ == '__main__':
    main()
