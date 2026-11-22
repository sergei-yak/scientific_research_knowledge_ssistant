"""Public HTTPS PDF downloader with pinned DNS, TLS verification and explicit redirect bounds."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urljoin, urlsplit

from research_assistant.collections.contracts import LIMITS, supported_url


class ImportFailure(ValueError):
    """A stable user-facing failure code, with no response body or credential interpolation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def remaining(deadline: float) -> float:
    """Apply one total deadline across DNS, redirects, headers and streaming reads."""
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ImportFailure('download_timeout', 'PDF download deadline exceeded')
    return seconds


def resolve_public(host: str, deadline: float) -> list[str]:
    """Kill a stalled resolver process; reject mixed public/private DNS answers in full."""
    try:
        result = subprocess.run([sys.executable, '-m', 'research_assistant.ingestion.resolve_dns', host],
            capture_output=True, text=True, timeout=remaining(deadline), check=True)
        addresses = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ImportFailure('dns_failed', 'Public PDF host could not be resolved within the deadline') from exc
    return checked_addresses(addresses)


def checked_addresses(addresses: list[str]) -> list[str]:
    """Accept only ordinary globally routable IPv4/IPv6 addresses, never local/mapped escape routes."""
    if not addresses:
        raise ImportFailure('unsafe_host', 'PDF host has no public addresses')
    parsed = []
    for value in addresses:
        address = ipaddress.ip_address(value)
        mapped = getattr(address, 'ipv4_mapped', None)
        if ('%' in value or not address.is_global or address.is_multicast
                or mapped is not None or getattr(address, 'sixtofour', None) is not None
                or getattr(address, 'teredo', None) is not None
                or (address.version == 6 and any(address in ipaddress.ip_network(prefix)
                    for prefix in ('64:ff9b::/96', '64:ff9b:1::/48')))):
            raise ImportFailure('unsafe_host', 'PDF host resolved to a non-public address')
        parsed.append(address)
    return [str(a) for a in sorted(set(parsed), key=lambda a: (a.version, int(a)))]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Keep hostname-based TLS/Host while connecting directly to one previously checked IP."""

    def __init__(self, host: str, address: str, timeout: float):
        self.deadline = time.monotonic() + timeout
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        """Avoid a second DNS lookup or proxy environment; never retry another address implicitly."""
        family = socket.AF_INET6 if ipaddress.ip_address(self.address).version == 6 else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        self._connecting_socket = raw
        try:
            raw.settimeout(remaining(self.deadline))
            raw.connect((self.address, 443))
            if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(self.address):
                raise ImportFailure('unsafe_peer', 'Connected PDF peer differs from its checked address')
            raw.settimeout(remaining(self.deadline))
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            self.sock.do_handshake()
            self._connecting_socket = None
        except BaseException:
            raw.close()
            raise


def expire_connection(connection) -> None:
    """Interrupt stalled/dribbling headers or TLS reads even when individual reads make progress."""
    transport = (getattr(connection, '_deadline_socket', None) or connection.sock
                 or getattr(connection, '_connecting_socket', None))
    if transport is not None:
        try:
            transport.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    connection.close()


def download_pdf(url: str, destination: Path, *, reserve, resolver=resolve_public,
                 connection_factory=PinnedHTTPSConnection) -> dict:
    """Reserve each attempt before DNS, stream once and retain a failed partial file for inspection."""
    current = supported_url(url)
    deadline = time.monotonic() + LIMITS.request_timeout_seconds
    attempts = []
    for number in range(LIMITS.max_redirects + 1):
        remaining(deadline)
        reserve({'url': current, 'attempt_in_chain': number + 1})
        parsed = urlsplit(current)
        addresses = checked_addresses(resolver(parsed.hostname, deadline))
        connection = connection_factory(parsed.hostname, addresses[0], remaining(deadline))
        connection.deadline = deadline
        expired = threading.Event()
        def enforce_deadline() -> None:
            expired.set()
            expire_connection(connection)
        watchdog = threading.Timer(remaining(deadline), enforce_deadline)
        watchdog.daemon = True
        watchdog.start()
        response = None
        try:
            connection.connect()
            transport = connection.sock
            connection._deadline_socket = transport
            transport.settimeout(remaining(deadline))
            path = parsed.path + ('?' + parsed.query if parsed.query else '')
            connection.request('GET', path, headers={
                'User-Agent': 'DBU-Research-Assistant/0.1 (local academic PDF import)',
                'Accept': 'application/pdf, application/octet-stream;q=0.8', 'Accept-Encoding': 'identity'})
            transport.settimeout(remaining(deadline))
            response = connection.getresponse()
            attempts.append({'url': current, 'addresses': addresses, 'connected_address': addresses[0],
                             'http_status': response.status})
            if response.status in {301, 302, 303, 307, 308}:
                if number >= LIMITS.max_redirects:
                    raise ImportFailure('redirect_limit', 'PDF link exceeded three redirects')
                location = response.getheader('Location')
                if not location:
                    raise ImportFailure('bad_redirect', 'PDF redirect has no destination')
                current = supported_url(urljoin(current, location))
                continue
            if response.status != 200:
                raise ImportFailure('http_error', f'PDF server returned HTTP {response.status}; no retry performed')
            content_type = (response.getheader('Content-Type') or '').split(';')[0].strip().lower()
            if content_type not in {'application/pdf', 'application/octet-stream', 'binary/octet-stream', ''}:
                raise ImportFailure('not_pdf', 'Link did not return a PDF content type')
            if (response.getheader('Content-Encoding') or 'identity').lower() != 'identity':
                raise ImportFailure('encoded_response', 'Compressed HTTP content is unsupported')
            declared = response.getheader('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared) > LIMITS.max_pdf_bytes):
                raise ImportFailure('file_too_large', 'PDF download exceeds the 25 MiB file limit')
            total, digest = 0, hashlib.sha256()
            with destination.open('xb') as handle:
                while True:
                    timeout = remaining(deadline)
                    transport.settimeout(timeout)
                    block = response.read1(min(65536, LIMITS.max_pdf_bytes - total + 1))
                    if not block:
                        break
                    total += len(block)
                    if total > LIMITS.max_pdf_bytes:
                        raise ImportFailure('file_too_large', 'PDF download exceeds the 25 MiB file limit')
                    handle.write(block)
                    digest.update(block)
            if expired.is_set():
                raise ImportFailure('download_timeout', 'PDF download deadline exceeded')
            if declared is not None and total != int(declared):
                raise ImportFailure('incomplete_download', 'PDF response length differs from the received bytes')
            return {'final_url': current, 'requests': attempts, 'byte_count': total,
                    'source_sha256': digest.hexdigest()}
        finally:
            watchdog.cancel()
            if response is not None:
                response.close()
            connection.close()
    raise ImportFailure('redirect_limit', 'PDF redirect limit exceeded')
