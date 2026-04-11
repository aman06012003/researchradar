"""
ResearchRadar — Semantic Scholar REST client.

Used as a fallback fetch source and to enrich citation counts for arXiv papers.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from app.core.config import SEMSCHOLAR_BASE_URL, SEMANTIC_SCHOLAR_API_KEY
from app.core.models import Paper
from app.fetcher.http_session import FetchError, RetrySession

logger = logging.getLogger(__name__)


def fetch_papers(
    category_slug: str,
    keywords: List[str],
    session: RetrySession,
    days_back: int = 7,
) -> List[Paper]:
    """
    Search Semantic Scholar for recent papers matching *keywords*.

    Returns a list of Paper instances.  Never raises — returns [] on error.
    """
    query_text = ' OR '.join(keywords)
    url = f'{SEMSCHOLAR_BASE_URL}/paper/search'
    params = {
        'query': query_text,
        'fields': (
            'paperId,title,abstract,authors,year,citationCount,'
            'externalIds,publicationDate,openAccessPdf'
        ),
        'publicationTypes': 'JournalArticle,Conference',
        'limit': 50,
    }

    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers['x-api-key'] = SEMANTIC_SCHOLAR_API_KEY

    try:
        response = session.get(url, params=params, headers=headers)
    except FetchError as exc:
        logger.error('Semantic Scholar fetch failed for %s: %s', category_slug, exc)
        return []

    try:
        data = response.json()
    except ValueError:
        logger.error('Semantic Scholar returned invalid JSON')
        return []

    cutoff = date.today() - timedelta(days=days_back)
    papers: List[Paper] = []

    for item in data.get('data', []):
        try:
            paper = _parse_item(item, category_slug, cutoff)
            if paper is not None:
                papers.append(paper)
        except Exception:
            logger.debug('Skipping malformed Semantic Scholar item', exc_info=True)

    logger.info(
        'Semantic Scholar: fetched %d papers for [%s]',
        len(papers), category_slug,
    )
    return papers


def _parse_item(item: dict, category_slug: str, cutoff: date) -> Optional[Paper]:
    """Parse a single S2 search result into a Paper, or None."""
    pub_date_str = item.get('publicationDate', '')
    if not pub_date_str:
        return None
    try:
        pub_date = date.fromisoformat(pub_date_str)
    except ValueError:
        return None

    if pub_date < cutoff:
        return None

    title = (item.get('title') or '').strip()
    abstract = (item.get('abstract') or '').strip()
    if not title or not abstract:
        return None

    s2_id = item.get('paperId', '')
    ext_ids = item.get('externalIds', {}) or {}
    arxiv_id = ext_ids.get('ArXiv', '')

    paper_id = f'arxiv:{arxiv_id}' if arxiv_id else f's2:{s2_id}'

    authors = [
        a.get('name', '') for a in (item.get('authors') or [])
        if a.get('name')
    ]

    pdf_info = item.get('openAccessPdf') or {}
    pdf_url = pdf_info.get('url')

    abstract_url = f'https://www.semanticscholar.org/paper/{s2_id}'

    return Paper(
        paper_id=paper_id,
        source='semantic_scholar',
        title=title,
        abstract=abstract,
        authors=authors,
        published_date=pub_date,
        categories=[],
        app_category=category_slug,
        pdf_url=pdf_url,
        abstract_url=abstract_url,
        citation_count=item.get('citationCount', 0) or 0,
    )


# ---------------------------------------------------------------------------
# Citation enrichment
# ---------------------------------------------------------------------------

def enrich_citations(papers: List[Paper], session: RetrySession) -> List[Paper]:
    """
    Batch-enrich citation counts from Semantic Scholar.

    This is best-effort: on failure the papers are returned unchanged.
    """
    if not papers:
        return papers

    # Build lookup of arXiv IDs (strip prefix)
    ids = []
    for p in papers:
        if p.paper_id.startswith('arxiv:'):
            ids.append(f'ArXiv:{p.paper_id[6:]}')
        elif p.paper_id.startswith('s2:'):
            ids.append(p.paper_id[3:])

    if not ids:
        return papers

    url = f'{SEMSCHOLAR_BASE_URL}/paper/batch'
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers['x-api-key'] = SEMANTIC_SCHOLAR_API_KEY

    try:
        response = session.post(
            url,
            json={'ids': ids},
            headers=headers,
        )
        results = response.json()
    except (FetchError, ValueError) as exc:
        logger.warning('Citation enrichment failed (best-effort): %s', exc)
        return papers

    # Map S2 results back to papers
    result_map: dict = {}
    for item in results:
        if item and 'paperId' in item:
            ext = item.get('externalIds', {}) or {}
            arxiv = ext.get('ArXiv')
            if arxiv:
                result_map[f'arxiv:{arxiv}'] = item.get('citationCount', 0) or 0
            result_map[f's2:{item["paperId"]}'] = item.get('citationCount', 0) or 0

    for paper in papers:
        if paper.paper_id in result_map:
            paper.citation_count = result_map[paper.paper_id]

    logger.info('Enriched citations for %d papers', len(papers))
    return papers
