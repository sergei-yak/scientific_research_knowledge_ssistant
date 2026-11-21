"""PDF imports and downloader failures on synthetic sources; no live network/models/DB."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pymupdf
import pytest

from research_assistant.collections.contracts import CorpusBinding, InputReference, LIMITS
from research_assistant.collections.store import CollectionRegistry
from research_assistant.ingestion import user_download as download
from research_assistant.ingestion import user_import as importing
from research_assistant.ingestion.user_pdf import inspect_pdf
from research_assistant.settings import Settings
from test_user_collections import declared_scope


@pytest.fixture
def registry(tmp_path, monkeypatch):
    declared_scope(tmp_path)
    monkeypatch.chdir(tmp_path)
    registry = CollectionRegistry(tmp_path)
    registry.initialize()
    return registry


def pdf_bytes(text='A synthetic scientific paper about attention and research evidence.', blank=False):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(30, 30, 560, 810), text, fontsize=8)
    if blank:
        doc.new_page()
    result = doc.tobytes()
    doc.close()
    return result


def inline_inspector(path, output):
    record = {'status': 'passed', **inspect_pdf(path)}
    output.write_text(json.dumps(record), encoding='utf-8')
    return record


class FixtureIndexer:
    """Synthetic typed binding only; native end-to-end proof uses the actual shared indexer."""

    def __init__(self):
        self.calls = []

    def __call__(self, candidate, prepared, encoder):
        self.calls.append((candidate, prepared))
        return CorpusBinding(corpus_id=candidate.corpus_id, snapshot_sha256='1' * 64,
            chunks_sha256='2' * 64, chunk_count=len(prepared), encoder_revision='synthetic')


def upload(content, name='paper.pdf'):
    return importing.ImportInput(InputReference(kind='upload', value=name), io.BytesIO(content))


def execute(registry, row, entries, **kwargs):
    job = registry.queue(row.collection_id, row.sha256, tuple(e.reference for e in entries))
    result = importing.run_import(registry, job.job_id, entries, Settings(),
        encoder_factory=lambda: object(), inspector=inline_inspector,
        indexer=kwargs.pop('indexer', FixtureIndexer()), write_guard=lambda settings: None, **kwargs)
    return result, registry.get_job(job.job_id)


def test_upload_commit_and_exact_duplicate_preserve_prior_revision(registry):
    first = registry.create('Attention')
    data = pdf_bytes(blank=True)
    indexer = FixtureIndexer()
    result, job = execute(registry, first, [upload(data)], indexer=indexer)
    assert result['status'] == job.state == 'ready' and len(indexer.calls) == 1
    indexed = registry.get(first.collection_id)
    assert indexed.revision == 2 and registry.committed_import(indexed) == job
    assert indexed.documents[0].pdf_pages == 2 and indexed.documents[0].indexed_pages == (1,)
    assert result['items'][0]['omitted_pages'] == [2]
    assert registry.describe(indexed)['available_modes'] == []
    earlier = (registry.root / 'collections' / first.collection_id / 'history/000001.json').read_bytes()
    result, job = execute(registry, indexed, [upload(data, 'renamed.pdf')], indexer=indexer)
    assert result['status'] == 'duplicate' and len(indexer.calls) == 1
    assert registry.get(first.collection_id) == indexed and job.output_corpus_id is None
    assert (registry.root / 'collections' / first.collection_id / 'history/000001.json').read_bytes() == earlier


def test_batch_deduplicates_identical_bytes_before_membership_and_indexing(registry):
    row = registry.create('Batch')
    data = pdf_bytes()
    indexer = FixtureIndexer()
    result, job = execute(registry, row, [upload(data, 'one.pdf'), upload(data, 'two.pdf')], indexer=indexer)
    assert result['status'] == 'ready' and result['new_documents'] == 1
    assert [item['duplicate'] for item in result['items']] == [False, True]
    assert len(indexer.calls[0][1]) == 1


@pytest.mark.parametrize('data', [b'', b'<html>not a PDF</html>', b'%PDF-1.7\ncorrupted bytes'])
def test_bad_input_retains_failure_and_does_not_publish(registry, data):
    row = registry.create('Bad input')
    result, job = execute(registry, row, [upload(data)])
    assert result['status'] == job.state == 'failed'
    assert registry.get(row.collection_id) == row
    assert (registry.root / 'jobs' / job.job_id / 'outcome.json').exists()
    with pytest.raises(ValueError, match='automatic resume'):
        importing.run_import(registry, job.job_id, [upload(data)], Settings())


def test_late_parse_failure_keeps_entire_prior_collection_intact(registry):
    row = registry.create('Atomic batch')
    indexer = FixtureIndexer()
    result, _ = execute(registry, row, [upload(pdf_bytes()), upload(b'%PDF-1.2 bad', 'bad.pdf')], indexer=indexer)
    assert result['status'] == 'failed' and indexer.calls == []
    assert registry.get(row.collection_id) == row
    assert (registry.root / 'sources').exists()  # retained source evidence, not an approved/indexed collection


def test_index_failure_has_no_commit_and_is_not_retried(registry):
    row = registry.create('Index failure')
    calls = []
    def fail(*args):
        calls.append(True)
        raise RuntimeError('Synthetic missing index service')
    result, job = execute(registry, row, [upload(pdf_bytes())], indexer=fail)
    assert result['status'] == job.state == 'failed' and len(calls) == 1
    assert registry.get(row.collection_id) == row
    assert not (registry.root / 'jobs' / job.job_id / 'commit.json').exists()


def test_download_reservation_is_durable_even_when_link_fails(registry):
    row = registry.create('Link')
    entry = importing.ImportInput(InputReference(kind='url', value='https://example.org/paper.pdf'))
    def unavailable(url, path, reserve):
        reserve({'url': url, 'attempt_in_chain': 1})
        raise download.ImportFailure('http_error', 'Synthetic HTTP 404; not retried')
    result, job = execute(registry, row, [entry], downloader=unavailable)
    assert result['status'] == 'failed' and result['request_attempts'] == 1
    saved = json.loads((registry.root / 'jobs' / job.job_id / 'requests/000001.json').read_bytes())
    assert saved['automatic_retries'] == 0


def test_supported_link_records_original_and_final_source(registry):
    row = registry.create('Link')
    data = pdf_bytes()
    def resolved(url, path, reserve):
        reserve({'url': url, 'attempt_in_chain': 1})
        path.write_bytes(data)
        import hashlib
        return {'source_sha256': hashlib.sha256(data).hexdigest(), 'byte_count': len(data),
                'final_url': 'https://example.org/paper.pdf', 'requests': []}
    entry = importing.ImportInput(InputReference(kind='url', value='https://arxiv.org/abs/1706.03762v7'))
    result, _ = execute(registry, row, [entry], downloader=resolved)
    assert result['status'] == 'ready' and result['request_attempts'] == 1
    assert registry.get(row.collection_id).documents[0].source == entry.reference


def test_worker_cannot_be_replaced_or_interrupted_while_running(registry):
    row = registry.create('Busy')
    entry = upload(pdf_bytes())
    job = registry.queue(row.collection_id, row.sha256, (entry.reference,))
    with registry.worker(job.job_id):
        with pytest.raises(FileExistsError):
            with registry.worker(job.job_id):
                pytest.fail('No concurrent worker')
        with pytest.raises(ValueError, match='worker is active'):
            registry.interrupt(job.job_id, job.sha256, 'Race')


def test_illegal_transitions_and_incomplete_publications_fail_closed(registry):
    row = registry.create('Commit')
    entry = upload(pdf_bytes())
    job = registry.queue(row.collection_id, row.sha256, (entry.reference,))
    with registry.worker(job.job_id) as token:
        with pytest.raises(ValueError, match='transition'):
            registry.advance(job.job_id, job.sha256, token, 'indexing')
        with pytest.raises(ValueError, match='ready requires'):
            registry.advance(job.job_id, job.sha256, token, 'ready')
    registry.interrupt(job.job_id, job.sha256, 'Unexecuted test')
    result, _ = execute(registry, row, [upload(pdf_bytes())])
    current = registry.get(row.collection_id)
    commit = registry.root / 'jobs' / result['job_id'] / 'commit.json'
    commit.unlink()  # synthetic corruption fixture, never real product data
    with pytest.raises(ValueError, match='incomplete'):
        registry.committed_import(current)
    with pytest.raises(ValueError, match='incomplete'):
        registry.queue(current.collection_id, current.sha256, (entry.reference,))


def test_plain_image_pdf_and_too_many_pages_are_rejected(tmp_path):
    blank = tmp_path / 'blank.pdf'
    doc = pymupdf.open()
    doc.new_page()
    doc.save(blank)
    doc.close()
    with pytest.raises(ValueError, match='no readable text'):
        inspect_pdf(blank)
    many = tmp_path / 'many.pdf'
    doc = pymupdf.open()
    for _ in range(101): doc.new_page()
    doc.save(many)
    doc.close()
    with pytest.raises(ValueError, match='100 pages'):
        inspect_pdf(many)


def test_upload_stream_actual_size_and_parser_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(importing, 'LIMITS', SimpleNamespace(max_pdf_bytes=1024))
    with pytest.raises(download.ImportFailure, match='25 MiB'):
        importing.copy_upload(io.BytesIO(b'x' * 1025), tmp_path / 'oversize.pdf')
    import subprocess
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('parser', 60)
    monkeypatch.setattr(importing.subprocess, 'run', timeout)
    with pytest.raises(download.ImportFailure) as error:
        importing.inspect_isolated(tmp_path / 'pdf', tmp_path / 'result.json')
    assert error.value.code == 'pdf_parse_timeout'


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.0.1',
    '::1', 'fc00::1', 'fe80::1', '224.0.0.1', '::ffff:127.0.0.1', '64:ff9b::7f00:1', '2002:7f00:1::'])
def test_dns_rejects_every_private_or_transitional_answer(address):
    with pytest.raises(download.ImportFailure):
        download.checked_addresses(['8.8.8.8', address])


class Response:
    def __init__(self, status=200, body=b'%PDF-fixture', headers=None):
        self.status, self.body, self.headers = status, io.BytesIO(body), headers or {}
        self.closed = False
    def getheader(self, name): return self.headers.get(name)
    def read1(self, size): return self.body.read(size)
    def close(self): self.closed = True


def transport(responses, connected):
    class Connection:
        def __init__(self, host, address, timeout):
            self.sock = SimpleNamespace(settimeout=lambda timeout: None)
            connected.append((host, address))
            self.response = responses.pop(0)
        def connect(self): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return self.response
        def close(self): pass
    return Connection


def fetch(tmp_path, responses, resolver=lambda host, deadline: ['8.8.8.8']):
    connected, reserved = [], []
    result = download.download_pdf('https://example.org/paper.pdf', tmp_path / 'download.pdf',
        reserve=reserved.append, resolver=resolver, connection_factory=transport(responses, connected))
    return result, connected, reserved


def test_download_stream_and_relative_redirect_preserve_checked_host(tmp_path):
    responses = [Response(302, headers={'Location': '/next.pdf'}), Response(headers={'Content-Type': 'application/pdf'})]
    result, connected, reserved = fetch(tmp_path, responses)
    assert len(connected) == len(reserved) == 2 and result['final_url'].endswith('/next.pdf')
    assert (tmp_path / 'download.pdf').read_bytes() == b'%PDF-fixture'


def test_redirect_to_private_host_stops_before_connecting(tmp_path):
    connected, reserved = [], []
    responses = [Response(302, headers={'Location': 'https://private.example.org/other.pdf'})]
    def dns(host, deadline): return ['8.8.8.8'] if host == 'example.org' else ['127.0.0.1']
    with pytest.raises(download.ImportFailure):
        download.download_pdf('https://example.org/paper.pdf', tmp_path / 'download.pdf', reserve=reserved.append,
            resolver=dns, connection_factory=transport(responses, connected))
    assert len(connected) == 1 and len(reserved) == 2


@pytest.mark.parametrize('response,code', [
    (Response(404), 'http_error'),
    (Response(headers={'Content-Type': 'text/html'}), 'not_pdf'),
    (Response(headers={'Content-Encoding': 'gzip'}), 'encoded_response'),
    (Response(headers={'Content-Length': str(LIMITS.max_pdf_bytes + 1)}), 'file_too_large'),
    (Response(headers={'Content-Length': '99'}), 'incomplete_download'),
])
def test_download_failure_has_no_retry(tmp_path, response, code):
    connected, reserved = [], []
    with pytest.raises(download.ImportFailure) as failure:
        download.download_pdf('https://example.org/paper.pdf', tmp_path / 'download.pdf', reserve=reserved.append,
            resolver=lambda *a: ['8.8.8.8'], connection_factory=transport([response], connected))
    assert failure.value.code == code and len(reserved) == len(connected) == 1
    assert response.closed


def test_redirect_limit_is_four_total_attempts(tmp_path):
    connected, reserved = [], []
    with pytest.raises(download.ImportFailure) as failure:
        download.download_pdf('https://example.org/paper.pdf', tmp_path / 'download.pdf', reserve=reserved.append,
            resolver=lambda *a: ['8.8.8.8'],
            connection_factory=transport([Response(302, headers={'Location': '/loop.pdf'}) for _ in range(4)], connected))
    assert failure.value.code == 'redirect_limit' and len(reserved) == len(connected) == 4


def test_single_total_download_deadline(tmp_path, monkeypatch):
    clock = [0]
    monkeypatch.setattr(download.time, 'monotonic', lambda: clock[0])
    def late_dns(*args):
        clock[0] = 31
        return ['8.8.8.8']
    with pytest.raises(download.ImportFailure) as failure:
        fetch(tmp_path, [], resolver=late_dns)
    assert failure.value.code == 'download_timeout'


def test_chunked_download_cannot_exceed_actual_byte_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(download, 'LIMITS', SimpleNamespace(request_timeout_seconds=30,
        max_redirects=3, max_pdf_bytes=8))
    with pytest.raises(download.ImportFailure) as failure:
        fetch(tmp_path, [Response(body=b'%PDF-' + b'x' * 40)])
    assert failure.value.code == 'file_too_large'
    assert (tmp_path / 'download.pdf').stat().st_size <= 8


def test_tls_connect_uses_checked_ip_without_second_dns(monkeypatch):
    import ssl
    import socket
    calls, closed = [], []
    raw = SimpleNamespace(settimeout=lambda t: calls.append(('timeout', t)),
        connect=lambda addr: calls.append(('connect', addr)), getpeername=lambda: ('8.8.8.8', 443),
        close=lambda: closed.append(True), do_handshake=lambda: calls.append(('handshake', True)))
    monkeypatch.setattr(download.socket, 'socket', lambda *args: raw)
    monkeypatch.setattr(download.socket, 'getaddrinfo', lambda *a, **k: pytest.fail('No second DNS lookup'))
    conn = object.__new__(download.PinnedHTTPSConnection)
    conn.address, conn.host, conn.timeout = '8.8.8.8', 'public.example.org', 2
    conn.deadline = time.monotonic() + 2
    conn._context = SimpleNamespace(wrap_socket=lambda sock, server_hostname, **options:
        calls.append(('tls-host', server_hostname)) or sock)
    conn.connect()
    assert ('connect', ('8.8.8.8', 443)) in calls and ('tls-host', 'public.example.org') in calls
    assert not closed


def test_tls_certificate_verification_remains_enabled():
    import ssl
    conn = download.PinnedHTTPSConnection('public.example.org', '8.8.8.8', 1)
    assert conn._context.check_hostname and conn._context.verify_mode == ssl.CERT_REQUIRED
    conn.close()


def test_full_collection_still_accepts_duplicate_without_new_revision(registry):
    row = registry.create('Ten papers')
    data = [pdf_bytes('Distinct synthetic paper ' + str(i)) for i in range(10)]
    result, _ = execute(registry, row, [upload(d, f'paper-{i}.pdf') for i, d in enumerate(data)])
    assert result['status'] == 'ready'
    full = registry.get(row.collection_id)
    assert len(full.documents) == 10
    duplicate, _ = execute(registry, full, [upload(data[0])])
    assert duplicate['status'] == 'duplicate' and registry.get(row.collection_id) == full
    exceeded, _ = execute(registry, full, [upload(pdf_bytes('An eleventh new paper'))])
    assert exceeded['status'] == 'failed' and exceeded['error_code'] == 'collection_limit'
    assert registry.get(row.collection_id) == full


def test_encrypted_pdf_and_text_budget_rejected(tmp_path, monkeypatch):
    encrypted = tmp_path / 'encrypted.pdf'
    doc = pymupdf.open()
    doc.new_page().insert_text((30, 40), 'Encrypted fixture only')
    doc.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
             owner_pw='fixture-owner', user_pw='fixture-reader')
    doc.close()
    with pytest.raises(ValueError, match='Encrypted'):
        inspect_pdf(encrypted)
    path = tmp_path / 'readable.pdf'
    path.write_bytes(pdf_bytes('Lengthy fixture text exceeds this deliberately tiny test cap'))
    from research_assistant.ingestion import user_pdf
    monkeypatch.setattr(user_pdf, 'MAX_PAGE_CHARACTERS', 5)
    with pytest.raises(ValueError, match='text limit'):
        user_pdf.inspect_pdf(path)


def test_chunk_cap_is_checked_before_embedding_or_graph_writes(registry, tmp_path, monkeypatch):
    from test_ingestion import FakeEncoder
    from research_assistant.collections.contracts import DocumentVersion, UserCollection
    from research_assistant.contracts import PaperManifestEntry
    path = tmp_path / 'large-text.pdf'
    path.write_bytes(pdf_bytes(' '.join('word' + str(i) for i in range(450))))
    inspected = inspect_pdf(path)
    manifest = PaperManifestEntry.model_validate(inspected['manifest'])
    document = DocumentVersion(paper_id=manifest.paper_id, source_sha256=manifest.source_sha256,
        source=InputReference(kind='upload', value='large-text.pdf'), byte_count=path.stat().st_size,
        pdf_pages=1, indexed_pages=(1,))
    row = registry.create('Chunk cap')
    candidate = UserCollection.model_validate({**row.model_dump(), 'revision': 2,
        'previous_sha256': row.sha256, 'documents': (document,)})
    monkeypatch.setattr(importing, 'LIMITS', SimpleNamespace(max_chunks=1))
    monkeypatch.setattr(importing, 'index_prepared_paper', lambda *a, **k: pytest.fail('No index/embedding write'))
    prepared = importing.PreparedPaper(document, manifest, inspected['pages'])
    with pytest.raises(ValueError, match='chunk limit'):
        importing.SharedCollectionIndexer(registry, Settings())(candidate, [prepared], FakeEncoder())


def test_cross_collection_source_metadata_is_canonical_but_corpora_are_separate(registry):
    data = pdf_bytes()
    indexer = FixtureIndexer()
    a, b = registry.create('A'), registry.create('B')
    first, _ = execute(registry, a, [upload(data, 'first-name.pdf')], indexer=indexer)
    second, _ = execute(registry, b, [upload(data, 'another-name.pdf')], indexer=indexer)
    assert first['status'] == second['status'] == 'ready'
    assert first['output_corpus_id'] != second['output_corpus_id']
    pa, pb = indexer.calls[0][1][0], indexer.calls[1][1][0]
    assert pa.manifest == pb.manifest and pa.pages == pb.pages
    assert pa.manifest.source_url.startswith('userpdf://')
    assert pa.document.source != pb.document.source


def test_total_deadline_interrupts_continuously_dripping_headers(tmp_path, monkeypatch):
    import socket
    import threading
    monkeypatch.setattr(download, 'LIMITS', SimpleNamespace(request_timeout_seconds=0.08,
        max_redirects=3, max_pdf_bytes=1024))
    threads = []
    class DrippingConnection:
        def __init__(self, *args):
            self.sock, self.peer = socket.socketpair()
        def connect(self): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self):
            def drip():
                try:
                    for _ in range(100):
                        self.peer.send(b'a')
                        time.sleep(0.01)
                except OSError:
                    pass
            thread = threading.Thread(target=drip, daemon=True)
            threads.append(thread)
            thread.start()
            while self.sock.recv(1):
                pass
            raise download.ImportFailure('download_timeout', 'Deadline interrupted headers')
        def close(self):
            self.sock.close()
            self.peer.close()
    started = time.monotonic()
    with pytest.raises((download.ImportFailure, OSError)):
        download.download_pdf('https://example.org/paper.pdf', tmp_path / 'drip.pdf',
            reserve=lambda record: None, resolver=lambda *args: ['8.8.8.8'],
            connection_factory=DrippingConnection)
    assert time.monotonic() - started < 0.7
    for thread in threads: thread.join(timeout=0.2)


def test_deadline_can_close_transport_after_http_connection_detaches_socket():
    closed = []
    transport = SimpleNamespace(shutdown=lambda how: closed.append('shutdown'))
    connection = SimpleNamespace(sock=None, _deadline_socket=transport, close=lambda: closed.append('close'))
    download.expire_connection(connection)
    assert closed == ['shutdown', 'close']


def test_timeout_induced_eof_is_not_accepted_as_a_completed_download(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(download, 'LIMITS', SimpleNamespace(request_timeout_seconds=0.05,
        max_redirects=3, max_pdf_bytes=1024))
    stopped = threading.Event()
    class IncompleteResponse(Response):
        def read1(self, size):
            block = self.body.read(size)
            if block: return block
            stopped.wait(0.5)
            return b''
    class Connection:
        def __init__(self, *args):
            self.sock = SimpleNamespace(settimeout=lambda t: None, shutdown=lambda how: stopped.set())
        def connect(self): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return IncompleteResponse(body=b'%PDF-incomplete')
        def close(self): stopped.set()
    with pytest.raises(download.ImportFailure) as failure:
        download.download_pdf('https://example.org/paper.pdf', tmp_path / 'partial.pdf',
            reserve=lambda r: None, resolver=lambda *args: ['8.8.8.8'], connection_factory=Connection)
    assert failure.value.code == 'download_timeout'
