"""Interactive local HTML presentation of an already-validated logical collection map."""

import json
import logging
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from research_assistant.collections.graph_view import CollectionGraph, load_collection_graph

logger = logging.getLogger(__name__)


def graph_html(graph: CollectionGraph) -> str:
    """Embed data safely; labels and quotations are rendered with textContent in the iframe."""
    payload = json.dumps(graph.model_dump(mode='json'), ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = Path(__file__).with_name('collection_graph.html').read_text(encoding='utf-8')
    return template.replace('__COLLECTION_GRAPH_JSON__', payload)


def graph_panel(registry, collection, settings, error_message) -> None:
    """An explicit toggle opens a freshly checked map without changing question/results/reviews."""
    show = st.checkbox('Show collection graph', value=False,
        key='show_collection_graph_' + collection.collection_id,
        help='Explore this collection independently of a question. No AI/model call is made.')
    if not show:
        return
    st.subheader('Collection graph explorer')
    logger.info('Collection graph display requested: %s revision %s', collection.collection_id, collection.revision)
    try:
        graph, ready = load_collection_graph(registry, collection.collection_id, collection.sha256, settings)
    except Exception as exc:
        st.error('Graph view is unavailable: ' + error_message(exc, settings))
        return
    st.caption(graph.review_notice)
    st.caption('Overview hides passages/search records for readability. Turn on Full graph inside the viewer to see every current node and edge. This map excludes obsolete/unapproved records and database administration nodes.')
    components.html(graph_html(graph), height=790, scrolling=True)
    st.download_button('Download current graph JSON', graph.model_dump_json(indent=2).encode('utf-8'),
        file_name='collection-graph-' + graph.sha256[:12] + '.json', mime='application/json',
        key='graph_json_' + collection.collection_id)
    source_id = st.selectbox('Graph source PDF', list(ready.sources),
        format_func=lambda key: ready.sources[key].reference, key='graph_pdf_' + collection.collection_id)
    source = ready.sources[source_id]
    st.download_button('Download graph source PDF', source.data, file_name=source.filename,
        mime='application/pdf', key='graph_source_' + collection.collection_id)
