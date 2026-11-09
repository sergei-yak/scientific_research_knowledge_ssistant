"""Materialize the declared M4 screening decisions from cached primary sources only."""

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from research_assistant.contracts import PaperManifestEntry, text_sha
from research_assistant.ingestion.corpus import ExpansionManifest
from research_assistant.pipeline import write_immutable

# Ordinals refer to the immutable ascending arXiv discovery result, not performance.
SELECTED = {6: 9, 11: 6, 13: 4, 17: 13, 21: 17, 23: 9, 31: 9, 40: 6,
            42: 8, 43: 8, 44: 10, 45: 7, 51: 9, 57: 8, 58: 7}
REASONS = {
    0: 'External-KG-only reasoning; no document collection retrieval.',
    1: 'Node-importance estimation rather than document RAG/QA.',
    2: 'Graph alignment/fine-tuning rather than document retrieval.',
    3: 'Multimodal EHR prediction using external PrimeKG.',
    4: 'General graph QA; no document-collection retrieval demonstrated in screened scope.',
    5: 'Temporal QA benchmark; no eligible document graph retrieval method.',
    7: 'Molecular graph modality, not document retrieval.',
    8: 'Pinned PDF describes KG construction; RAG answers competency questions before graph construction, not graph-guided document retrieval.',
    9: 'GUI automation graph, not document QA.',
    10: 'KG construction/schema retrieval, not graph-guided document QA.',
    12: 'Pilot base ID retained at its already pinned v1.',
    14: 'RAG extracts policy alignments into a KG, followed by rule-based compliance verification rather than graph-guided QA/synthesis.',
    15: 'Driving behavior/sensor modality, not document QA.',
    16: 'External-KG medical answer refinement, not a document graph.',
    18: 'KG link prediction rather than document QA.',
    19: 'Pinned method uses KG-enhanced contrastive training samples for a dense retriever; no graph traversal/evidence organization at retrieval.',
    20: 'Pilot base ID retained at its already pinned v1.',
    22: 'Pinned evaluation uses WebQSP/ExplaGraphs graph QA; no document-collection retrieval demonstrated in screened scope.',
    24: 'Multimodal EHR prediction with external PrimeKG.',
    25: 'External-KG-only QA (WebQSP/CWQ).',
    26: 'Software dependency graph, not a text/document collection.',
    27: 'Energy digital-twin measurements, not document retrieval.',
    28: 'External OwnThink KG-only QA.',
    29: 'Benchmark without an eligible document graph retrieval method.',
    30: 'Web passage retrieval plus external KG triples; no document graph retrieval.',
    32: 'Distractor generation/pretraining, not document graph QA.',
    33: 'KG-derived planning supervision, not a document graph retrieval method.',
    34: 'Relation extraction rather than graph-guided document QA.',
    35: 'Structured FMEA/tabular graph, not a document collection.',
    36: 'KG error checking benchmark, not document graph QA/synthesis.',
    37: 'Multimodal medical image/data workflow outside the text scope.',
    38: 'Interactive game-world memory, not document-collection QA.',
    39: 'Geospatial trajectory modality.',
    41: 'External-KG answer reasoning/error study, not a document graph.',
    46: 'Pinned KG module queries an external mock API; web passages are retrieved separately, without a document graph.',
    47: 'Validation requirements/perspective, not a retrieval method.',
    48: 'Pinned framework combines independent external KG and web retrieval, not a document graph.',
    49: 'Survey; additions require original retrieval methods.',
    50: 'Hardware design/task graph and waveform tracing, outside document QA.',
    52: 'Startup/time-series prediction, not document QA.',
    53: 'Temporal KG forecasting, not document QA.',
    54: 'Pinned method targets game trust reasoning, not document-collection QA.',
    55: 'Code synthesis from papers; retrospective retrieval is vector-based, not eligible document graph QA.',
    56: 'Drug-target prediction/evidence integration, outside the document graph QA method scope.',
}


def main() -> None:
    """Write selection ledger and source manifest before extraction, without contacting services."""
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    root = Path('data/metadata/expansion-v1')
    entries = ET.fromstring((root / 'discovery.xml').read_text(encoding='utf-8')).findall('a:entry', ns)
    papers = json.loads(Path('manifests/pilot-five-papers.json').read_text(encoding='utf-8'))['papers']
    ledger = []
    for index, entry in enumerate(entries):
        base = entry.findtext('a:id', namespaces=ns).split('/')[-1].split('v')[0]
        record = {'discovery_index': index, 'base_id': base,
                  'first_submitted': entry.findtext('a:published', namespaces=ns),
                  'discovery_title': ' '.join(entry.findtext('a:title', namespaces=ns).split()),
                  'url': 'https://arxiv.org/abs/' + base}
        if index not in SELECTED:
            record.update(status='not_reached' if index > max(SELECTED) else 'excluded',
                          reason='Fifteen eligible additions already selected in chronological order.' if index > max(SELECTED) else REASONS[index])
        else:
            identity = base + 'v1'
            landing = (root / (identity + '.html')).read_text(encoding='utf-8')
            title = html.unescape(re.search(r'<meta name="citation_title" content="(.*?)"', landing, re.S).group(1))
            rights = re.search(r'https?://(?:arxiv.org/licenses|creativecommons.org/licenses)/[^"<> ]+', landing).group(0).replace('http:', 'https:')
            path = Path('data/raw') / ('arxiv-' + identity + '.pdf')
            note = 'Pinned v1 main text; references/appendices beyond coverage omitted. Mixed boundary pages may contain references, figures or tables; these are not independently verified.'
            if index in {11, 31, 40, 42, 51}:
                note += ' Last included page mixes final prose/limitations with the start of references.'
            if index == 23:
                note += ' Separate limitations after the reference pages are omitted and must not be treated as searched.'
            paper = PaperManifestEntry(paper_id='arxiv:' + identity, arxiv_id=identity, title=title,
                source_url='https://arxiv.org/pdf/' + identity, source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                local_path=path.as_posix(), document_type='primary_study', rights_url=rights,
                rights='License displayed by pinned arXiv landing page: ' + rights + '; local academic analysis, no redistribution.',
                selected_pages=list(range(1, SELECTED[index] + 1)), selection_reason=note + ' See manifests/CORPUS_SELECTION.md.')
            papers.append(paper.model_dump())
            record.update(status='selected', reason='Graph-guided retrieval/organization over text or document collections; eligible in recorded date order.',
                          pinned_title=title, pinned_arxiv_id=identity, pages=paper.selected_pages, source_sha256=paper.source_sha256,
                          screening_basis='Cached pinned v1 PDF and arXiv landing page; no retrieval/generation scores.')
        ledger.append(record)
    manifest = ExpansionManifest(selection_record='manifests/CORPUS_SELECTION.md',
        selection_sha256=text_sha(Path('manifests/CORPUS_SELECTION.md').read_text(encoding='utf-8')), papers=papers)
    write_immutable(Path('manifests/expansion-selection.json'), json.dumps({'protocol': manifest.selection_record,
        'selection_sha256': manifest.selection_sha256, 'discovery_sha256': hashlib.sha256((root / 'discovery.xml').read_bytes()).hexdigest(),
        'candidates': ledger, 'retained_pilot_papers': 5, 'selected_additions': 15,
        'caveat': 'Bounded date-ordered purposive sample; latest API abstracts used for triage, pinned v1 source is authoritative.'}, ensure_ascii=False, indent=2) + '\n')
    write_immutable(Path('manifests/expanded-twenty-papers.json'), manifest.model_dump_json(indent=2) + '\n')
    print('Recorded 20 sources, 15 additions; no model calls or claim approvals.')


if __name__ == '__main__':
    main()
