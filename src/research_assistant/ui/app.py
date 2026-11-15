"""Local research workflows using the same services as the CLI."""

import logging
from pathlib import Path

import streamlit as st

from research_assistant.contracts import QueryRequest, RunArtifact
from research_assistant.embeddings import Encoder
from research_assistant.pipeline import QueryExecutionError, run_query, write_immutable
from research_assistant.product import PILOT_CORPUS, WORKFLOWS, prepare_output
from research_assistant.settings import Settings, configure_caches

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


@st.cache_resource(show_spinner='Loading the cached CPU encoder…')
def cached_encoder() -> Encoder:
    """Share the read-only encoder, never database transactions or query results."""
    return Encoder()


def display_run(run: RunArtifact, settings: Settings,review_directory: Path = Path('data/reviews/pilot')) -> None:
    """Render checked saved request identity, structured views, excerpts and optional synthesis."""
    view, csv_text = (prepare_output(run, settings,review_directory=review_directory)
                      if run.request.profile_id=='retrieval-v2' else prepare_output(run, settings))
    st.caption(f'Retrieval profile: {run.request.profile_id} · selector: {run.request.selector_id}')
    retrieval = run.retrieval
    st.subheader('Query result')
    st.write(run.request.question)
    st.caption(f'Workflow: {run.workflow} · Requested: {retrieval.requested_mode} · Effective: {retrieval.effective_mode}')
    if retrieval.fallback_reason:
        st.info(f'Graph fallback: {retrieval.fallback_reason}. Showing the unchanged Hybrid + Facts evidence.')
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
    st.subheader('LLM synthesis')
    if run.result is None:
        st.info('This profile currently returns evidence only.' if run.request.profile_id=='retrieval-v2'
                else 'Answer not generated. Enable synthesis and submit to request an answer.')
    else:
        if run.result.insufficient_evidence:
            st.warning('The generator reported insufficient evidence.')
        st.text(run.result.answer)
        if run.result.citations:
            st.caption('Cited evidence: ' + ', '.join(citation['evidence_id'] for citation in run.result.citations))
        st.caption('Generated synthesis is separate from approved claims; a valid citation is not a correctness score.')
        if run.generation:
            st.caption(f'{run.generation.provider} · {run.generation.model} · {run.generation.elapsed_ms:.0f} ms · run {run.run_id}')
    st.subheader('Source excerpts and graph connections')
    st.caption('PDF page numbers are authoritative. Parsed section labels are unverified; figures and numeric tables are not validated.')
    for index, item in enumerate(retrieval.evidence, 1):
        with st.expander(f'E{index} · {"Approved paper claim" if item.kind == "approved_fact" else "Raw excerpt"} · {", ".join(item.paper_ids)}'):
            if item.claim_text:
                st.text(item.claim_text)
                st.caption(f'Claim {item.approved_claim_ids[0]} · revision {item.claim_revision}')
                st.json(item.conditions)
            for number, excerpt in enumerate(item.excerpts, 1):
                st.link_button(f'{excerpt.paper_id} · PDF p. {excerpt.page} · source {number}',
                               excerpt.source_url.split('#')[0] + f'#page={excerpt.page}')
                st.text(excerpt.text)
            if item.graph_paths:
                st.write('Graph-derived connections included in the model context')
                st.json(item.graph_paths)
            else:
                st.caption('No graph-derived connection selected for this evidence unit.')
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
    workflow = st.selectbox('Workflow', list(WORKFLOWS), format_func=lambda value: value.title())
    profile = st.selectbox('Retrieval profile', ['baseline','retrieval-v2'],
                           help='V2 requires the explicit isolated development scope; the pilot default stays baseline.')
    review_directory=Path('data/reviews/expansion-v1' if profile=='retrieval-v2' else 'data/reviews/pilot')
    with st.form('query'):
        question = st.text_area('Research question', value=WORKFLOWS[workflow], key=f'question_{workflow}', max_chars=2000)
        mode = st.selectbox('Retrieval mode', ['vector', 'hybrid', 'hybrid_facts', 'graph'], index=3)
        generate = st.checkbox('Generate an answer with the configured model', value=False,disabled=profile=='retrieval-v2')
        if profile=='retrieval-v2':st.caption('V2 reference selector · isolated scope required · retrieval only')
        st.caption(f'Configured generator: {settings.generation_provider} / {settings.generation_model}. Context 4096, output limit 512; one request, no automatic retry or provider switching.')
        with st.expander('Corpus snapshot'):
            corpus = st.text_input('Corpus ID', value=PILOT_CORPUS)
            scope_file=st.text_input('V2 scope file',value='data/scopes/retrieval-v2.json') if profile=='retrieval-v2' else None
        submitted = st.form_submit_button('Run research query', type='primary')
    if submitted:
        st.session_state.pop('run', None)
        try:
            with st.spinner('Retrieving evidence' + (' and generating an answer…' if generate else '…')):
                request = QueryRequest(question=question.strip(), corpus_id=corpus, mode=mode,profile_id=profile,scope_file=scope_file)
                run = run_query(request, settings, generate=generate, workflow=workflow, encoder=cached_encoder(),review_directory=review_directory)
                write_immutable(Path('runs/ui') / run.run_id / 'run.json', run.model_dump_json(indent=2) + '\n')
                if profile=='retrieval-v2':prepare_output(run, settings,review_directory=review_directory)
                else:prepare_output(run, settings)
                st.session_state['run'] = run.model_dump(mode='json')
        except Exception as exc:
            if isinstance(exc, QueryExecutionError):
                write_immutable(Path('runs/ui') / exc.artifact.run_id / 'failed-run.json', exc.artifact.model_dump_json(indent=2) + '\n')
            logger.error('UI query failed: %s', settings.redact(str(exc)))
            st.error('Query failed: ' + settings.redact(str(exc)))
            st.caption('Check service readiness. Submit with synthesis disabled to inspect evidence independently.')
    if 'run' in st.session_state:
        try:
            display_run(RunArtifact.model_validate(st.session_state['run']), settings,review_directory=review_directory)
        except Exception as exc:
            logger.error('Stored result validation failed: %s', settings.redact(str(exc)))
            st.error('Saved evidence cannot be validated against current sources/approvals. Rerun the query; export is disabled.')


if __name__ == '__main__':
    main()
