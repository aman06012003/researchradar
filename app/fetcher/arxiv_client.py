"""
ResearchRadar — arXiv Atom API client.

Fetches papers submitted/updated within the last N days for given arXiv
categories.  Uses xml.etree.ElementTree (stdlib) — no lxml needed.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import List

from app.core.config import ARXIV_BASE_URL, ARXIV_MAX_RESULTS
from app.core.models import Paper
from app.fetcher.http_session import FetchError, RetrySession

logger = logging.getLogger(__name__)

# arXiv Atom namespace
_NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'arxiv': 'http://arxiv.org/schemas/atom',
}


def fetch_papers(
    category_slug: str,
    arxiv_cats: List[str],
    session: RetrySession,
    days_back: int = 7,
) -> List[Paper]:
    """
    Fetch papers submitted/updated within *days_back* days across all
    arXiv categories in *arxiv_cats*.

    Returns a list of Paper instances.  Never raises — returns [] on error.
    """
    today = date.today()
    start = today - timedelta(days=days_back)
    end = today

    query = '(' + ' OR '.join(f'cat:{c}' for c in arxiv_cats) + ')'

    params = {
        'search_query': query,
        'start': 0,
        'max_results': ARXIV_MAX_RESULTS,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    }

    try:
        response = session.get(ARXIV_BASE_URL, params=params)
    except FetchError as exc:
        logger.error('arXiv fetch failed for %s: %s', category_slug, exc)
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.error(
            'arXiv XML parse error: %s — snippet: %s',
            exc, response.text[:300],
        )
        return []

    papers: List[Paper] = []

    for entry in root.findall('atom:entry', _NS):
        try:
            paper = _parse_entry(entry, category_slug, start, end)
            if paper is not None:
                papers.append(paper)
        except Exception:
            logger.debug('Skipping malformed arXiv entry', exc_info=True)

    logger.info(
        'arXiv: fetched %d papers for [%s] (%s)',
        len(papers), category_slug, ', '.join(arxiv_cats),
    )
    return papers


def _parse_entry(
    entry: ET.Element,
    category_slug: str,
    start: date,
    end: date,
) -> Paper | None:
    """Parse a single <entry> element into a Paper, or return None."""

    title_el = entry.find('atom:title', _NS)
    abstract_el = entry.find('atom:summary', _NS)
    if title_el is None or abstract_el is None:
        return None

    title = ' '.join((title_el.text or '').split())
    abstract = ' '.join((abstract_el.text or '').split())
    if not title or not abstract:
        logger.debug('Skipping entry with empty title/abstract')
        return None

    # arXiv ID
    id_el = entry.find('atom:id', _NS)
    raw_id = (id_el.text or '') if id_el is not None else ''
    arxiv_id = raw_id.replace('http://arxiv.org/abs/', '').strip()
    if not arxiv_id:
        return None
    paper_id = f'arxiv:{arxiv_id}'

    # Authors
    authors = []
    for author_el in entry.findall('atom:author', _NS):
        name_el = author_el.find('atom:name', _NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    # Published date
    pub_el = entry.find('atom:published', _NS)
    pub_text = (pub_el.text or '') if pub_el is not None else ''
    try:
        published = datetime.fromisoformat(
            pub_text.replace('Z', '+00:00')
        ).date()
    except (ValueError, TypeError):
        published = date.today()

    # FILTER BY DATE: Only return papers between start and end inclusive
    if not (start <= published <= end):
        logger.debug(
            'Skipping arXiv entry from %s (outside range %s to %s)',
            published, start, end
        )
        return None

    # Categories
    categories = []
    for cat_el in entry.findall('atom:category', _NS):
        term = cat_el.get('term', '')
        if term:
            categories.append(term)

    # PDF link
    pdf_url = None
    for link_el in entry.findall('atom:link', _NS):
        if link_el.get('title') == 'pdf':
            pdf_url = link_el.get('href')
            break
    if pdf_url is None and arxiv_id:
        pdf_url = f'https://arxiv.org/pdf/{arxiv_id}'

    abstract_url = f'https://arxiv.org/abs/{arxiv_id}'

    return Paper(
        paper_id=paper_id,
        source='arxiv',
        title=title,
        abstract=abstract,
        authors=authors,
        published_date=published,
        categories=categories,
        app_category=category_slug,
        pdf_url=pdf_url,
        abstract_url=abstract_url,
    )
