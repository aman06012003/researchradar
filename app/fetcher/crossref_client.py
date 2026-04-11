"""
ResearchRadar — CrossRef DOI client.

DOI resolution & citation metadata fallback.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from app.core.config import CROSSREF_BASE_URL
from app.fetcher.http_session import FetchError, RetrySession

logger = logging.getLogger(__name__)


def get_citation_count(doi: str, session: RetrySession) -> Optional[int]:
    """
    Retrieve the 'is-referenced-by-count' from CrossRef for a given DOI.

    Returns None on any error — this is best-effort enrichment.
    """
    url = f'{CROSSREF_BASE_URL}/{doi}'
    try:
        response = session.get(
            url,
            headers={'Accept': 'application/json'},
        )
        data = response.json()
        message = data.get('message', {})
        return message.get('is-referenced-by-count')
    except (FetchError, ValueError, KeyError) as exc:
        logger.debug('CrossRef lookup failed for DOI %s: %s', doi, exc)
        return None


def resolve_doi(doi: str, session: RetrySession) -> Optional[dict]:
    """
    Resolve a DOI and return basic metadata dict including title, authors.
    """
    url = f'{CROSSREF_BASE_URL}/{doi}'
    try:
        response = session.get(
            url,
            headers={'Accept': 'application/json'},
        )
        data = response.json()
        msg = data.get('message', {})

        title_parts = msg.get('title', [])
        title = title_parts[0] if title_parts else ''

        authors = []
        for a in msg.get('author', []):
            given = a.get('given', '')
            family = a.get('family', '')
            authors.append(f'{given} {family}'.strip())

        return {
            'doi': doi,
            'title': title,
            'authors': authors,
            'citation_count': msg.get('is-referenced-by-count', 0),
        }
    except (FetchError, ValueError, KeyError) as exc:
        logger.debug('CrossRef resolve failed for DOI %s: %s', doi, exc)
        return None
