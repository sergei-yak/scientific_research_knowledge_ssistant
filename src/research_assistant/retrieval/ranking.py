"""Frozen rank-only fusion contract for later retrievers; no hybrid search in M1."""

from __future__ import annotations


def reciprocal_rank_fusion(lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Fuse equal-contribution unique rankings, with stable-ID ties."""
    if k <= 0:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for ranking in lists:
        for rank, identity in enumerate(dict.fromkeys(ranking), 1):
            scores[identity] = scores.get(identity, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
