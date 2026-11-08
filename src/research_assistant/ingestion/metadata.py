"""Bounded OpenAlex lookups; reference metadata is version-agnostic discovery data."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import PaperManifestEntry, fingerprint
from research_assistant.pipeline import write_immutable
from research_assistant.settings import Settings


def normalized_title(value: str) -> str:
    """Ignore title punctuation/spacing only; never accept a fuzzy first hit."""
    return re.sub(r"[\W_]+", "", value.casefold())


def select_match(paper: PaperManifestEntry, payload: dict) -> dict | None:
    """Require an exact DOI or punctuation-normalized title, and an unambiguous match."""
    doi = "https://doi.org/10.48550/arxiv." + re.sub(r"v\d+$", "", paper.arxiv_id or "")
    rows = payload.get("results", [payload])
    matches = [row for row in rows if row.get("id") and (
        str(row.get("doi", "")).lower() == doi
        or normalized_title(row.get("title") or "") == normalized_title(paper.title))]
    return matches[0] if len(matches) == 1 else None


def fetch_metadata(papers: list[PaperManifestEntry], settings: Settings, directory: Path) -> dict:
    """At most two GETs per paper, no paid plan/top-up, no crawling or automatic retries."""
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for paper in papers:
        cache = directory / (paper.paper_id.replace(":", "-") + ".json")
        if cache.exists():
            row = json.loads(cache.read_text(encoding="utf-8"))
            if row["source_sha256"] != paper.source_sha256:
                raise ValueError("Metadata cache belongs to a different source")
            result.append(row)
            continue
        identity = re.sub(r"v\d+$", "", paper.arxiv_id or "")
        doi = "https://doi.org/10.48550/arXiv." + identity
        row = {"paper_id": paper.paper_id, "source_sha256": paper.source_sha256,
               "arxiv_id": paper.arxiv_id, "arxiv_doi": doi,
               "checked_at": datetime.now(timezone.utc).isoformat(), "openalex_id": None,
               "references_status": "unknown", "referenced_works": [], "attempts": []}
        urls = ["https://api.openalex.org/works/" + urllib.parse.quote(doi, safe=""),
                "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": paper.title, "per_page": 5})]
        for url in urls:
            headers = {"User-Agent": "DBU-Research-Pilot/0.1 (bounded academic metadata lookup)"}
            if key := settings.openalex_api_key.get_secret_value():
                headers["Authorization"] = "Bearer " + key
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                    payload = json.loads(response.read(4_000_000))
                    row["attempts"].append({"url": url, "status": response.status,
                                            "reported_cost": response.headers.get("X-RateLimit-Credits-Used")})
                match = select_match(paper, payload)
                if match:
                    row.update(openalex_id=match["id"], title=match.get("title"),
                               doi=match.get("doi"), year=match.get("publication_year"),
                               references_status="available" if "referenced_works" in match else "unknown",
                               referenced_works=match.get("referenced_works", []),
                               matched_record=match, response_sha256=fingerprint(payload))
                    break
                row["attempts"][-1]["match"] = "missing_or_ambiguous"
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
                row["attempts"].append({"url": url, "status": getattr(exc, "code", None),
                                        "error": type(exc).__name__})
                if getattr(exc, "code", None) in {401, 403, 409, 429}:
                    break  # Credentials/quota problems are pending, not reasons for more requests.
            time.sleep(0.2)
        write_immutable(cache, json.dumps(row, ensure_ascii=False, indent=2) + "\n")
        result.append(row)
    edges = [{"citing": source["paper_id"], "cited": target["paper_id"], "source": "openalex",
              "version_scope": "work_level_not_pdf_version"}
             for source in result for target in result
             if target["openalex_id"] and target["openalex_id"] in source["referenced_works"]]
    return {"papers": result, "citation_edges": edges,
            "caveat": "References are work-level metadata, not verification of citations in the pinned PDF; missing edges are unknown."}
