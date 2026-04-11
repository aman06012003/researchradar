"""
ResearchRadar — Composite ranker.

Combines relevance, citation, and recency scores with user-configurable
weights to produce a final ``composite_score`` for each paper.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.core.config import (
    TOP_N_PER_CATEGORY,
    WEIGHT_CITATION,
    WEIGHT_RECENCY,
    WEIGHT_RELEVANCE,
)
from app.core.models import Paper, UserProfile
from app.ranker import citation_scorer
from app.ranker.tfidf_ranker import TfidfRanker

logger = logging.getLogger(__name__)


def rank_all(
    papers_by_category: Dict[str, List[Paper]],
    profile: UserProfile,
    cache_dir: str = '',
) -> Dict[str, List[Paper]]:
    """
    Score and sort papers per category.

    Returns a dict ``{category: [Paper, ...]}`` with each list sorted by
    ``composite_score`` descending and sliced to ``top_n``.
    """
    w_rel = profile.weight_relevance
    w_cit = profile.weight_citation
    w_rec = profile.weight_recency
    top_n = profile.top_n_per_category

    # Validate weights
    total = w_rel + w_cit + w_rec
    if abs(total - 1.0) > 0.01:
        logger.warning(
            'Ranking weights sum to %.2f (expected 1.0) — normalising', total
        )
        w_rel /= total
        w_cit /= total
        w_rec /= total

    # Build TF-IDF ranker
    ranker = TfidfRanker(cache_dir=cache_dir)
    if not ranker.load_cache():
        ranker.fit_profile(profile.interests)

    ranked: Dict[str, List[Paper]] = {}

    for category, papers in papers_by_category.items():
        if not papers:
            ranked[category] = []
            continue

        # Relevance scores
        ranker.score_many(papers)

        # Citation + recency scores
        for paper in papers:
            cit_score = citation_scorer.score(paper)
            rec_score = citation_scorer.recency_score(paper)

            paper.composite_score = (
                w_rel * paper.relevance_score
                + w_cit * cit_score
                + w_rec * rec_score
            )

        # Sort and slice
        papers.sort(key=lambda p: p.composite_score, reverse=True)
        ranked[category] = papers[:top_n]

        logger.info(
            'Ranked [%s]: %d → top %d (best=%.3f)',
            category, len(papers), min(top_n, len(papers)),
            papers[0].composite_score if papers else 0.0,
        )

    return ranked
