"""Bounded, sequential pinned-source screening cache; no recursive discovery or inference."""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from research_assistant.pipeline import write_immutable


def main() -> None:
    """Cache only explicitly named discovery indices, respecting arXiv request pacing."""
    parser = argparse.ArgumentParser()
    parser.add_argument('indices', type=int, nargs='+')
    args = parser.parse_args()
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    root = Path('data/metadata/expansion-v1')
    entries = ET.fromstring((root / 'discovery.xml').read_text(encoding='utf-8')).findall('a:entry', ns)
    for index in args.indices:
        entry = entries[index]
        base = entry.findtext('a:id', namespaces=ns).split('/')[-1].split('v')[0]
        identity = base + 'v1'
        for suffix, url, limit in [('html', 'https://arxiv.org/abs/' + identity, 2_000_000),
                                   ('pdf', 'https://arxiv.org/pdf/' + identity, 30_000_000)]:
            target = root / (identity + '.html') if suffix == 'html' else Path('data/raw') / ('arxiv-' + identity + '.pdf')
            if target.exists():
                continue
            time.sleep(3.1)
            record = {'discovery_index': index, 'source_url': url}
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'DBU-Research-Assistant/0.1 bounded academic source cache'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read(limit + 1)
                if len(body) > limit or (suffix == 'pdf' and not body.startswith(b'%PDF')):
                    raise ValueError('Invalid/oversized source response')
                if suffix == 'html':
                    write_immutable(target, body.decode('utf-8'))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as stream:
                        stream.write(body)
                record.update(status='cached', bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                record.update(status='unavailable', error=type(exc).__name__, code=getattr(exc, 'code', None))
            write_immutable(root / (identity + '.' + suffix + '.attempt.json'), json.dumps(record, indent=2) + '\n')
            print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
