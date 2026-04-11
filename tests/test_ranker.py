"""
Tests for app.ranker — TF-IDF, citation, and composite ranker.
"""

from datetime import date, timedelta

import pytest

from app.core.models import Paper, UserProfile
from app.ranker import citation_scorer, composite_ranker
from app.ranker.tfidf_ranker import TfidfRanker


def _make_paper(title, abstract, cat='ml', citations=0, days_old=0):
    return Paper(
        paper_id=f'arxiv:test_{hash(title) % 10000}',
        source='arxiv',
        title=title,
        abstract=abstract,
        authors=['Test Author'],
        published_date=date.today() - timedelta(days=days_old),
        categories=['cs.LG'],
        app_category=cat,
        abstract_url='https://example.com',
        citation_count=citations,
    )


class TestTfidfRanker:
    def test_score_range(self):
        ranker = TfidfRanker()
        ranker.fit_profile({'ml': 'deep learning neural networks transformers'})

        paper = _make_paper(
            'Deep Learning for NLP',
            'We use deep neural networks for natural language processing.',
        )
        score = ranker.score(paper)
        assert 0.0 <= score <= 1.0

    def test_relevant_paper_scores_higher(self):
        ranker = TfidfRanker()
        ranker.fit_profile({'ml': 'deep learning neural network attention transformer'})

        relevant = _make_paper(
            'Attention-Based Transformer Architectures',
            'We extend transformer attention mechanisms for deep learning tasks.',
        )
        irrelevant = _make_paper(
            'Cooking Recipes for Italian Pasta',
            'This paper discusses pasta sauces and Italian cuisine traditions.',
        )

        score_r = ranker.score(relevant)
        score_i = ranker.score(irrelevant)
        assert score_r > score_i


class TestCitationScorer:
    def test_normalised_range(self):
        paper = _make_paper('Test', 'Abstract', citations=100, days_old=10)
        score = citation_scorer.score(paper)
        assert 0.0 <= score <= 1.0

    def test_recency_bonus(self):
        recent = _make_paper('New', 'Abstract', citations=5, days_old=1)
        old = _make_paper('Old', 'Abstract', citations=5, days_old=10)

        score_new = citation_scorer.score(recent)
        score_old = citation_scorer.score(old)
        assert score_new > score_old

    def test_recency_score(self):
        today = _make_paper('Today', 'Abstract', days_old=0)
        assert citation_scorer.recency_score(today) == 1.0

        week_old = _make_paper('Week', 'Abstract', days_old=7)
        assert citation_scorer.recency_score(week_old) == 0.0


class TestCompositeRanker:
    def test_weights_sum_validation(self):
        profile = UserProfile(
            weight_relevance=0.5,
            weight_citation=0.5,
            weight_recency=0.5,
        )
        papers = {
            'ml': [
                _make_paper('Paper A', 'Abstract A', citations=10),
                _make_paper('Paper B', 'Abstract B', citations=5),
            ]
        }
        # Should not raise even though weights don't sum to 1
        result = composite_ranker.rank_all(papers, profile)
        assert 'ml' in result

    def test_top_n_slicing(self):
        profile = UserProfile(top_n_per_category=2)
        papers = {
            'ml': [
                _make_paper(f'Paper {i}', f'Abstract {i}', citations=i)
                for i in range(10)
            ]
        }
        result = composite_ranker.rank_all(papers, profile)
        assert len(result['ml']) == 2

    def test_empty_category(self):
        profile = UserProfile()
        result = composite_ranker.rank_all({'ml': []}, profile)
        assert result['ml'] == []
