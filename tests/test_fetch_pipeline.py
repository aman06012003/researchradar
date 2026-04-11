"""
Tests for app.fetcher.fetch_pipeline — orchestration.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import Digest, Paper, UserProfile
from app.fetcher import fetch_pipeline


def _make_paper(paper_id: str, title: str, source: str = 'arxiv', cat: str = 'ml'):
    return Paper(
        paper_id=paper_id,
        source=source,
        title=title,
        abstract=f'Abstract of {title}',
        authors=['Author'],
        published_date=date.today(),
        categories=['cs.LG'],
        app_category=cat,
        abstract_url=f'https://example.com/{paper_id}',
    )


class TestDeduplication:
    def test_exact_id_dedup(self):
        papers = [
            _make_paper('arxiv:001', 'Paper A'),
            _make_paper('arxiv:001', 'Paper A copy'),
        ]
        result = fetch_pipeline._deduplicate(papers)
        assert len(result) == 1

    def test_similar_title_dedup(self):
        papers = [
            _make_paper('arxiv:001', 'Attention Is All You Need'),
            _make_paper('s2:002', 'Attention Is All You Need', source='semantic_scholar'),
        ]
        result = fetch_pipeline._deduplicate(papers)
        assert len(result) == 1
        # Prefer arXiv source
        assert result[0].source == 'arxiv'

    def test_different_papers_kept(self):
        papers = [
            _make_paper('arxiv:001', 'Paper About Cats'),
            _make_paper('arxiv:002', 'Paper About Dogs'),
        ]
        result = fetch_pipeline._deduplicate(papers)
        assert len(result) == 2


class TestRunWeeklyFetch:
    @patch('app.fetcher.fetch_pipeline.semantic_scholar')
    @patch('app.fetcher.fetch_pipeline.arxiv_client')
    def test_arxiv_primary_success(self, mock_arxiv, mock_ss):
        mock_arxiv.fetch_papers.return_value = [
            _make_paper('arxiv:001', 'ML Paper', cat='ml'),
        ]
        mock_ss.enrich_citations.return_value = []

        digest = fetch_pipeline.run_weekly_fetch(':memory:', UserProfile())

        assert isinstance(digest, Digest)
        assert mock_arxiv.fetch_papers.called
        # If arXiv returned results, SS fetch should NOT have been called
        # for the same category (since papers is non-empty)

    @patch('app.fetcher.fetch_pipeline.semantic_scholar')
    @patch('app.fetcher.fetch_pipeline.arxiv_client')
    def test_arxiv_empty_triggers_fallback(self, mock_arxiv, mock_ss):
        mock_arxiv.fetch_papers.return_value = []
        mock_ss.fetch_papers.return_value = [
            _make_paper('s2:001', 'SS Paper', source='semantic_scholar', cat='ml'),
        ]
        mock_ss.enrich_citations.return_value = []

        digest = fetch_pipeline.run_weekly_fetch(':memory:', UserProfile())

        assert mock_ss.fetch_papers.called

    @patch('app.fetcher.fetch_pipeline.semantic_scholar')
    @patch('app.fetcher.fetch_pipeline.arxiv_client')
    def test_both_fail_no_crash(self, mock_arxiv, mock_ss):
        from app.fetcher.http_session import FetchError
        mock_arxiv.fetch_papers.side_effect = FetchError('arxiv down')
        mock_ss.fetch_papers.side_effect = FetchError('ss down')
        mock_ss.enrich_citations.return_value = []

        digest = fetch_pipeline.run_weekly_fetch(':memory:', UserProfile())

        # Must return a Digest, never raise
        assert isinstance(digest, Digest)
        assert len(digest.fetch_errors) > 0

    @patch('app.fetcher.fetch_pipeline.semantic_scholar')
    @patch('app.fetcher.fetch_pipeline.arxiv_client')
    def test_never_raises(self, mock_arxiv, mock_ss):
        mock_arxiv.fetch_papers.side_effect = Exception('catastrophic')
        mock_ss.fetch_papers.side_effect = Exception('also bad')
        mock_ss.enrich_citations.side_effect = Exception('worse')

        digest = fetch_pipeline.run_weekly_fetch(':memory:', UserProfile())
        assert isinstance(digest, Digest)
