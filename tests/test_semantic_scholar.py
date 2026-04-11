"""
Tests for app.fetcher.semantic_scholar — Semantic Scholar client.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.fetcher import semantic_scholar
from app.fetcher.http_session import FetchError, RetrySession
from app.core.models import Paper


def _mock_session(json_data, status=200):
    session = MagicMock(spec=RetrySession)
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    session.get.return_value = resp
    session.post.return_value = resp
    return session


_SAMPLE_RESPONSE = {
    'data': [
        {
            'paperId': 'abc123',
            'title': 'Deep Reinforcement Learning',
            'abstract': 'We explore novel RL methods for robotics.',
            'authors': [{'name': 'Jane Doe'}, {'name': 'John Doe'}],
            'year': 2026,
            'citationCount': 10,
            'externalIds': {'ArXiv': '2401.11111'},
            'publicationDate': date.today().isoformat(),
            'openAccessPdf': {'url': 'https://example.com/paper.pdf'},
        },
        {
            'paperId': 'def456',
            'title': 'Old Paper',
            'abstract': 'This is from long ago.',
            'authors': [{'name': 'Old Author'}],
            'year': 2020,
            'citationCount': 100,
            'externalIds': {},
            'publicationDate': '2020-01-01',
            'openAccessPdf': None,
        },
    ]
}


class TestFetchPapers:
    def test_success_filters_by_date(self):
        session = _mock_session(_SAMPLE_RESPONSE)
        papers = semantic_scholar.fetch_papers(
            'ml', ['machine learning'], session, days_back=7
        )
        # Only the recent paper should pass the date filter
        assert len(papers) == 1
        assert papers[0].title == 'Deep Reinforcement Learning'
        assert papers[0].source == 'semantic_scholar'

    def test_fetch_error_returns_empty(self):
        session = MagicMock(spec=RetrySession)
        session.get.side_effect = FetchError('boom')
        papers = semantic_scholar.fetch_papers('ml', ['ml'], session)
        assert papers == []


class TestEnrichCitations:
    def test_enrichment_updates_counts(self):
        paper = Paper(
            paper_id='arxiv:2401.11111',
            source='arxiv',
            title='Test',
            abstract='Test abstract',
            authors=['Auth'],
            published_date=date.today(),
            categories=['cs.LG'],
            app_category='ml',
            abstract_url='https://arxiv.org/abs/2401.11111',
            citation_count=0,
        )
        enrich_response = [
            {
                'paperId': 'abc123',
                'citationCount': 99,
                'externalIds': {'ArXiv': '2401.11111'},
            }
        ]
        session = _mock_session(enrich_response)
        result = semantic_scholar.enrich_citations([paper], session)
        assert result[0].citation_count == 99

    def test_enrichment_failure_returns_unchanged(self):
        paper = Paper(
            paper_id='arxiv:2401.99999',
            source='arxiv',
            title='Test',
            abstract='Abstract',
            authors=[],
            published_date=date.today(),
            categories=[],
            app_category='ml',
            abstract_url='',
            citation_count=5,
        )
        session = MagicMock(spec=RetrySession)
        session.post.side_effect = FetchError('network')
        result = semantic_scholar.enrich_citations([paper], session)
        assert result[0].citation_count == 5
