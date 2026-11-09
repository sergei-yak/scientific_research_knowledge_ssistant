"""Cache one bounded primary-source discovery result; never infer claims or approve them."""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.pipeline import write_immutable


def main() -> None:
    """Run the pre-recorded arXiv query once, preserving failures instead of retrying."""
    query = '(all:GraphRAG OR all:"graph retrieval" OR (all:"knowledge graph" AND all:"retrieval augmented")) AND submittedDate:[202401010000 TO 202512312359]'
    url = 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode({
        'search_query': query, 'start': 0, 'max_results': 150,
        'sortBy': 'submittedDate', 'sortOrder': 'ascending'})
    record = {'query': query, 'url': url, 'checked_at': datetime.now(timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'DBU-Research-Assistant/0.1 bounded academic corpus selection'})
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read(8_000_000)
            record['status'] = response.status
        write_immutable(Path('data/metadata/expansion-v1/discovery.xml'), body.decode('utf-8'))
    except (urllib.error.URLError, TimeoutError) as exc:
        record.update(status=getattr(exc, 'code', None), error=type(exc).__name__)
    write_immutable(Path('data/metadata/expansion-v1/discovery-attempt.json'), json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
