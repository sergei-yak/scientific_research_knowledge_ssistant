"""Research-paper workspace UI; collection/import/QA rules live in shared Python services."""

import json
import logging
from urllib.parse import urlsplit

import streamlit as st
from pydantic import ValidationError

from research_assistant.collections.contracts import LIMITS
from research_assistant.collections.store import CollectionRegistry
from research_assistant.collections.workspace import (
    USER_MODES, checked_output, import_collection, query_collection, verify_collection,
)
from research_assistant.contracts import RunArtifact, fingerprint
from research_assistant.settings import Settings, configure_caches
from research_assistant.ui.app import cached_encoder, render_run

logger = logging.getLogger(__name__)


def message(exc: Exception, settings: Settings) -> str:
    """Keep user-facing validation errors concise and avoid echoing secret input fields."""
    text = exc.errors(include_input=False, include_url=False)[0]['msg'] if isinstance(exc, ValidationError) else str(exc)
    return settings.redact(text)


def show_result(registry: CollectionRegistry, collection, saved: dict, settings: Settings) -> None:
    """Revalidate saved output and source files before rendering any answer/download."""
    run = RunArtifact.model_validate(saved)
    view, csv_text, ready = checked_output(registry, collection.collection_id, run, settings, collection.sha256)
    def source_card(excerpt, *, key):
        source = ready.sources[excerpt.paper_id]
        st.caption(f'{source.reference} · PDF page {excerpt.page}')
        if source.web_url:
            st.link_button(f'Open original paper · p. {excerpt.page}', source.web_url + f'#page={excerpt.page}')
        st.download_button(f'Download source PDF · p. {excerpt.page}', source.data,
            file_name=source.filename, mime='application/pdf', key=key)
    labels = {key: (urlsplit(source.web_url).path.rsplit('/', 1)[-1]
                   if source.web_url else source.filename)[:100]
              for key, source in ready.sources.items()}
    render_run(run, view, csv_text, source_card=source_card, show_reviewed_features=False,
               paper_labels=labels)


def main() -> None:
    """User submits are the only triggers for import, retrieval or optional synthesis."""
    st.set_page_config(page_title='Research Paper Workspace', page_icon='📚', layout='wide')
    configure_caches()
    st.title('Research Paper Workspace')
    st.write('Add research papers to a collection, ask a question, and check the answer against the source pages.')
    try:
        settings = Settings.from_env()
        registry = CollectionRegistry()
    except Exception:
        st.error('The paper workspace is not configured. Use the M8 launcher and its setup guide.')
        return
    with st.sidebar:
        st.header('Your collections')
        with st.form('create_collection'):
            name = st.text_input('Collection name', max_chars=80)
            create = st.form_submit_button('Create collection')
        if create:
            try:
                created = registry.create(name.strip())
                st.session_state['user_collection'] = created.collection_id
                st.session_state.pop('user_run', None)
            except Exception as exc:
                st.error(message(exc, settings))
        try:
            collections = sorted(registry.list(), key=lambda row: (row.binding is None, row.name.casefold(), row.collection_id))
        except Exception as exc:
            st.session_state.pop('user_run', None)
            st.error('Collection registry is unavailable: ' + message(exc, settings))
            return
        if not collections:
            st.info('Create a collection to add your first papers.')
            return
        by_id = {row.collection_id: row for row in collections}
        if st.session_state.get('user_collection') not in by_id:
            st.session_state['user_collection'] = collections[0].collection_id
        selector_key = 'collection_selector_' + fingerprint(list(by_id))[:16]
        if selector_key not in st.session_state:
            st.session_state[selector_key] = st.session_state['user_collection']
        selected = st.selectbox('Paper collection', list(by_id), index=None,
            format_func=lambda key: by_id[key].name, key=selector_key)
        st.session_state['user_collection'] = selected
        st.caption('Each collection keeps its own papers, revisions and source references.')
    collection = by_id[selected]
    selection = (collection.collection_id, collection.revision, collection.sha256)
    if st.session_state.get('user_selection') != selection:
        st.session_state.pop('user_run', None)
        st.session_state['user_selection'] = selection
    st.subheader(collection.name)
    st.caption(f'{len(collection.documents)} documents · revision {collection.revision}')
    previous = st.session_state.get('last_import')
    if previous and previous.get('collection_id') == selected:
        if previous['status'] == 'ready':
            st.success('Papers imported and indexed. You can now ask a question.')
        elif previous['status'] == 'duplicate':
            st.info('Those PDF bytes are already in this collection. No new revision was created.')
        else:
            st.error('Import failed: ' + previous.get('reason', previous['status']))
    with st.expander('Add papers', expanded=not collection.documents):
        st.caption('Text-based PDFs only. Up to 10 papers per collection; 25 MiB and 100 pages per PDF. Scanned or password-protected files are unsupported.')
        epoch = st.session_state.get('upload_epoch', 0)
        with st.form('import_documents'):
            uploaded = st.file_uploader('Upload PDFs', type=['pdf'], accept_multiple_files=True, key=f'uploads_{epoch}')
            links = st.text_area('PDF or arXiv links (one per line)', max_chars=LIMITS.max_url_length * LIMITS.max_documents,
                                 key=f'links_{epoch}')
            importing = st.form_submit_button('Import documents')
        if importing:
            st.session_state.pop('user_run', None)
            try:
                status = st.empty()
                with st.spinner('Importing documents…'):
                    def progress(job):
                        labels = {'resolving': 'Reading files and downloading links…',
                                  'parsing': 'Checking PDF pages and readable text…',
                                  'indexing': 'Building searchable passages…',
                                  'ready': 'Import complete', 'duplicate': 'Existing papers recognized'}
                        status.info(labels.get(job.state, job.state))
                    outcome = import_collection(registry, selected, collection.sha256,
                        [(file.name, file) for file in uploaded], links.splitlines(), settings,
                        encoder_factory=cached_encoder, on_progress=progress)
                    if outcome['status'] in {'ready', 'duplicate'}:
                        status.success('Import complete')
                    else:
                        status.error('Import failed')
                st.session_state['last_import'] = outcome
                if outcome['status'] in {'ready', 'duplicate'}:
                    st.session_state['upload_epoch'] = epoch + 1
                st.rerun()
            except Exception as exc:
                st.error('Import could not start: ' + message(exc, settings))
    if collection.documents:
        with st.expander('Papers and indexed coverage'):
            st.table([{'Source': d.source.value, 'PDF pages': d.pdf_pages,
                       'Indexed pages': len(d.indexed_pages)} for d in collection.documents])
    usable = False
    try:
        ready = verify_collection(registry, selected, settings, collection.sha256)
        usable = True
        st.caption(f'Ready to search · {ready.collection.binding.chunk_count} passages')
    except Exception as exc:
        st.info('Collection is not ready for questions: ' + message(exc, settings))
    with st.form('user_query'):
        question = st.text_area('Research question', max_chars=2000,
            placeholder='For example: What problem does this method solve, and what limitations do the authors report?')
        mode = st.selectbox('Retrieval mode', list(USER_MODES), index=1, format_func=USER_MODES.get,
            help='Vector finds similar passages. Hybrid combines meaning and keyword search.')
        generate = st.checkbox('Generate an answer', value=False)
        st.caption(f'Configured generator: {settings.generation_provider} / {settings.generation_model}. Generation is optional; local answers can take a minute or more.')
        submitted = st.form_submit_button('Ask question', type='primary', disabled=not usable)
    if submitted:
        st.session_state.pop('user_run', None)
        try:
            with st.spinner('Finding source passages' + (' and writing an answer…' if generate else '…')):
                run = query_collection(registry, selected, collection.sha256, question, mode, settings,
                                       generate=generate, encoder=cached_encoder())
                st.session_state['user_run'] = run.model_dump(mode='json')
        except Exception as exc:
            logger.error('Collection query failed: %s', message(exc, settings))
            st.error('Question failed: ' + message(exc, settings))
    if 'user_run' in st.session_state:
        try:
            show_result(registry, collection, st.session_state['user_run'], settings)
        except Exception as exc:
            st.session_state.pop('user_run', None)
            st.error('Saved output is no longer valid for this collection. Submit the question again; downloads are disabled.')
            logger.warning('Saved collection output rejected: %s', message(exc, settings))
    with st.expander('Import history'):
        jobs = [job for job in registry.jobs() if job.collection_id == selected]
        st.table([{'Job': job.job_id, 'Status': job.state, 'Details': job.reason or ''} for job in jobs])


if __name__ == '__main__':
    main()
