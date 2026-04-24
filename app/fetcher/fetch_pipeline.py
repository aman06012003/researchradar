"""
ResearchRadar — Fetch pipeline orchestration.

Contains the main Sunday job logic.  Coordinates all API clients,
handles fallback, deduplication, ranking, storage, and notification.

This function must **never raise** — all exceptions are caught and
logged into ``Digest.fetch_errors``.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Dict, List

from app.core.config import (
    ARXIV_CATEGORY_MAP,
    KEYWORD_MAP,
    PUBMED_MESH_MAP,
    TOP_N_PER_CATEGORY,
    AI_FILTERS,
)
from app.core.models import Digest, Paper, UserProfile
from app.core import database
from app.fetcher import arxiv_client, pubmed_client, semantic_scholar, youtube_client
from app.fetcher.http_session import FetchError, RetrySession
from app.ranker import composite_ranker
from app.summarizer.groq_client import GroqSummarizer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_weekly_fetch(
    db_path: str,
    profile: UserProfile | None = None,
) -> Digest:
    """
    Main weekly pipeline.  Called by the scheduler every Sunday.

    1. Fetch papers from arXiv (primary) with Semantic Scholar fallback.
    2. For neuro/BCI categories, additionally fetch from PubMed and merge.
    3. Enrich citation counts (best-effort).
    4. Rank papers via composite ranker.
    5. Save digest to DB and send notification.
    6. Return the Digest.
    """
    if profile is None:
        profile = UserProfile()

    digest = Digest.create_new()
    session = RetrySession()
    all_papers: Dict[str, List[Paper]] = {}

    for category, arxiv_cats in ARXIV_CATEGORY_MAP.items():
        papers = _fetch_category(category, arxiv_cats, session, digest)

        # PubMed supplement for neuroscience & BCI
        if category in PUBMED_MESH_MAP:
            pubmed_papers = _fetch_pubmed(category, session, digest)
            papers = _deduplicate(papers + pubmed_papers)

            # Enforce AI filter for neuro categories
            # "I want only those papers in neuroscience and BCI which has in someway AI or ML"
            papers = _ai_filter(papers)

        all_papers[category] = papers

    # Enrich citation counts (best-effort)
    flat = [p for cat_list in all_papers.values() for p in cat_list]
    try:
        semantic_scholar.enrich_citations(flat, session)
    except Exception as exc:
        logger.warning('Citation enrichment failed: %s', exc)
        digest.fetch_errors.append(f'Citation enrichment: {exc}')

    # Filter out papers that have already been sent in a previous digest
    flat_all = [p for cat_list in all_papers.values() for p in cat_list]
    existing_ids = database.get_existing_paper_ids(db_path, [p.paper_id for p in flat_all])
    
    if existing_ids:
        logger.info("Filtering out %d papers already in database", len(existing_ids))
        for cat in all_papers:
            all_papers[cat] = [p for p in all_papers[cat] if p.paper_id not in existing_ids]

    # Rank
    digest.total_fetched = sum(len(v) for v in all_papers.values())
    ranked = composite_ranker.rank_all(all_papers, profile)

    # After ranking, summarize the top papers for the digest
    # (Only summarizes top N results that appear in the final ranked lists)
    _summarize_top_papers(ranked)

    digest.papers = ranked
    digest.total_ranked = sum(len(v) for v in ranked.values())

    # Fetch YouTube videos for the "while eating" section
    try:
        digest.videos = youtube_client.fetch_latest_videos(limit_per_channel=1)
    except Exception as exc:
        logger.warning('YouTube fetch failed: %s', exc)
        digest.fetch_errors.append(f'YouTube error: {exc}')

    # Persist
    try:
        database.save_digest(db_path, digest)
    except Exception as exc:
        logger.error('Failed to save digest: %s', exc)
        digest.fetch_errors.append(f'DB save error: {exc}')

    # Notification (best-effort)
    try:
        from app.core.notifier import send_digest_notification
        send_digest_notification(digest)
    except Exception as exc:
        logger.warning('Notification failed: %s', exc)

    return digest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_category(
    category: str,
    arxiv_cats: list,
    session: RetrySession,
    digest: Digest,
) -> List[Paper]:
    """Fetch from arXiv, fall back to Semantic Scholar if empty / error."""
    papers: List[Paper] = []

    try:
        papers = arxiv_client.fetch_papers(category, arxiv_cats, session)
    except Exception as exc:
        msg = f'arXiv error [{category}]: {exc}'
        logger.warning(msg)
        digest.fetch_errors.append(msg)

    if not papers:
        logger.info('arXiv empty for [%s] — trying Semantic Scholar', category)
        try:
            keywords = KEYWORD_MAP.get(category, [category])
            papers = semantic_scholar.fetch_papers(category, keywords, session)
        except Exception as exc:
            msg = f'Semantic Scholar error [{category}]: {exc}'
            logger.warning(msg)
            digest.fetch_errors.append(msg)

    if not papers:
        logger.info('No papers found for [%s] from any source', category)

    return papers


def _fetch_pubmed(
    category: str,
    session: RetrySession,
    digest: Digest,
) -> List[Paper]:
    """Fetch supplemental papers from PubMed."""
    mesh = PUBMED_MESH_MAP.get(category, '')
    if not mesh:
        return []
    try:
        return pubmed_client.fetch_papers(category, mesh, session)
    except Exception as exc:
        msg = f'PubMed error [{category}]: {exc}'
        logger.warning(msg)
        digest.fetch_errors.append(msg)
        return []


def _summarize_top_papers(papers_by_cat: Dict[str, List[Paper]]):
    """Call Groq to summarize papers in the final digest list."""
    summarizer = GroqSummarizer()
    for cat, papers in papers_by_cat.items():
        if papers:
            logger.info("Summarizing %d papers for category [%s]...", len(papers), cat)
            summarizer.summarize_many(papers)


def _ai_filter(papers: List[Paper]) -> List[Paper]:
    """Filter to only include papers mentioning AI/ML keywords in title or abstract."""
    if not papers:
        return []

    result = []
    for p in papers:
        text = (p.title + " " + p.abstract).lower()
        if any(f in text for f in AI_FILTERS):
            result.append(p)
    return result


def _deduplicate(papers: List[Paper]) -> List[Paper]:
    """
    Remove duplicate papers.

    Two papers are considered duplicates if:
    - Their paper_id matches, OR
    - Their title similarity (SequenceMatcher ratio) > 0.92

    When merging, prefer arXiv > Semantic Scholar > PubMed.
    """
    SOURCE_PRIORITY = {'arxiv': 0, 'semantic_scholar': 1, 'pubmed': 2}
    seen_ids: set = set()
    seen_titles: List[str] = []
    result: List[Paper] = []

    # Sort by source priority so preferred sources come first
    papers.sort(key=lambda p: SOURCE_PRIORITY.get(p.source, 9))

    for paper in papers:
        if paper.paper_id in seen_ids:
            continue

        is_dup = False
        for existing_title in seen_titles:
            if SequenceMatcher(None, paper.title.lower(), existing_title).ratio() > 0.92:
                is_dup = True
                break

        if is_dup:
            continue

        seen_ids.add(paper.paper_id)
        seen_titles.append(paper.title.lower())
        result.append(paper)

    if len(papers) != len(result):
        logger.info(
            'Deduplication: %d → %d papers', len(papers), len(result),
        )

    return result
