"""
ResearchRadar — PubMed E-utilities client.

Supplemental source for Neuroscience and BCI categories only.
Two-step process: ESearch to get IDs, then EFetch to get abstracts.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import List, Optional

from app.core.config import NCBI_API_KEY, PUBMED_BASE_URL
from app.core.models import Paper
from app.fetcher.http_session import FetchError, RetrySession

logger = logging.getLogger(__name__)


def fetch_papers(
    category_slug: str,
    mesh_terms: str,
    session: RetrySession,
    days_back: int = 7,
) -> List[Paper]:
    """
    Fetch recent papers from PubMed matching *mesh_terms*.

    Returns a list of Paper instances.  Never raises — returns [] on error.
    """

    # ---------------------------------------------------------------
    # Step 1 — ESearch
    # ---------------------------------------------------------------
    esearch_params: dict = {
        'db': 'pubmed',
        'term': f'{mesh_terms} AND ("last {days_back} days"[PDat])',
        'retmax': 50,
        'retmode': 'json',
        'usehistory': 'y',
    }
    if NCBI_API_KEY:
        esearch_params['api_key'] = NCBI_API_KEY

    try:
        esearch_resp = session.get(
            f'{PUBMED_BASE_URL}/esearch.fcgi', params=esearch_params
        )
    except FetchError as exc:
        logger.error('PubMed ESearch failed for %s: %s', category_slug, exc)
        return []

    try:
        esearch_data = esearch_resp.json()
    except ValueError:
        logger.error('PubMed ESearch returned invalid JSON')
        return []

    result = esearch_data.get('esearchresult', {})
    count = int(result.get('count', 0))
    if count == 0:
        logger.info('PubMed: 0 results for %s', category_slug)
        return []

    web_env = result.get('webenv', '')
    query_key = result.get('querykey', '')
    if not web_env or not query_key:
        logger.error('PubMed ESearch missing WebEnv / query_key')
        return []

    # ---------------------------------------------------------------
    # Step 2 — EFetch
    # ---------------------------------------------------------------
    efetch_params: dict = {
        'db': 'pubmed',
        'WebEnv': web_env,
        'query_key': query_key,
        'retmax': 50,
        'retmode': 'xml',
        'rettype': 'abstract',
    }
    if NCBI_API_KEY:
        efetch_params['api_key'] = NCBI_API_KEY

    try:
        efetch_resp = session.get(
            f'{PUBMED_BASE_URL}/efetch.fcgi', params=efetch_params
        )
    except FetchError as exc:
        logger.error('PubMed EFetch failed for %s: %s', category_slug, exc)
        return []

    try:
        root = ET.fromstring(efetch_resp.text)
    except ET.ParseError as exc:
        logger.error('PubMed XML parse error: %s', exc)
        return []

    papers: List[Paper] = []
    for article_el in root.findall('.//PubmedArticle'):
        try:
            paper = _parse_article(article_el, category_slug)
            if paper is not None:
                papers.append(paper)
        except Exception:
            logger.debug('Skipping malformed PubMed article', exc_info=True)

    logger.info('PubMed: fetched %d papers for [%s]', len(papers), category_slug)
    return papers


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------

def _parse_article(el: ET.Element, category_slug: str) -> Optional[Paper]:
    """Parse a single <PubmedArticle> element."""

    # PMID
    pmid_el = el.find('.//PMID')
    if pmid_el is None or not pmid_el.text:
        return None
    pmid = pmid_el.text.strip()
    paper_id = f'pubmed:{pmid}'

    # Title
    title_el = el.find('.//ArticleTitle')
    title = (title_el.text or '').strip() if title_el is not None else ''
    if not title:
        return None

    # Abstract — may be structured (Background, Methods, etc.)
    abstract_parts: List[str] = []
    for abs_el in el.findall('.//AbstractText'):
        label = abs_el.get('Label', '')
        text = (abs_el.text or '').strip()
        if label and text:
            abstract_parts.append(f'{label}: {text}')
        elif text:
            abstract_parts.append(text)
    abstract = '\n'.join(abstract_parts)
    if not abstract:
        return None

    # Authors
    authors: List[str] = []
    for author_el in el.findall('.//Author'):
        last = author_el.findtext('LastName', '').strip()
        fore = author_el.findtext('ForeName', '').strip()
        if last:
            name = f'{fore} {last}'.strip()
            authors.append(name)

    # Publication date (best-effort)
    pub_date = _parse_pub_date(el)

    abstract_url = f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'

    return Paper(
        paper_id=paper_id,
        source='pubmed',
        title=title,
        abstract=abstract,
        authors=authors,
        published_date=pub_date,
        categories=[],
        app_category=category_slug,
        pdf_url=None,
        abstract_url=abstract_url,
    )


def _parse_pub_date(el: ET.Element) -> date:
    """Best-effort parse of PubMed date (Year, Month, Day may be partial)."""
    pub_date_el = el.find('.//PubDate')
    if pub_date_el is None:
        return date.today()

    year_text = pub_date_el.findtext('Year', '')
    month_text = pub_date_el.findtext('Month', '')
    day_text = pub_date_el.findtext('Day', '')

    try:
        year = int(year_text)
    except (ValueError, TypeError):
        return date.today()

    # Month may be numeric or abbreviated text
    month = 1
    if month_text:
        try:
            month = int(month_text)
        except ValueError:
            _MONTH_ABBREV = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            }
            month = _MONTH_ABBREV.get(month_text.lower()[:3], 1)

    day = 1
    if day_text:
        try:
            day = int(day_text)
        except ValueError:
            pass

    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 1, 1)
