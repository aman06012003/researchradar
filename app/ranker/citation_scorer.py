"""
ResearchRadar — Citation velocity scorer.

Normalises raw citation counts into a [0.0, 1.0] score and applies a
recency bonus for very fresh papers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from app.core.config import CITATION_NORM, RECENCY_BONUS
from app.core.models import Paper


def score(paper: Paper) -> float:
    """
    Return a citation score in [0.0, 1.0].

    - ``citation_score = min(citation_count / CITATION_NORM, 1.0)``
    - Papers published < 3 days ago get a recency bonus.
    """
    citation_score = min(paper.citation_count / max(CITATION_NORM, 1), 1.0)

    days_old = (date.today() - paper.published_date).days
    if days_old < 3:
        citation_score = min(citation_score + RECENCY_BONUS, 1.0)

    return citation_score


def score_many(papers: List[Paper]) -> List[Paper]:
    """Set ``citation_score`` on each paper and return the list (in-place)."""
    for p in papers:
        # Store on the Paper via the composite score pipeline; we use
        # a transient attribute.  The composite ranker reads this.
        p._citation_score = score(p)  # type: ignore[attr-defined]
    return papers


def recency_score(paper: Paper) -> float:
    """
    Return a recency score in [0.0, 1.0].

    1.0 = published today, 0.0 = published ≥ 7 days ago.
    """
    days_old = max((date.today() - paper.published_date).days, 0)
    return max(1.0 - days_old / 7.0, 0.0)
