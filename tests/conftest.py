"""
Shared pytest fixtures for ResearchRadar tests.
"""

import os
import sys
import tempfile

import pytest

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.models import Paper, Digest, UserProfile
from app.core import database
from datetime import date, datetime


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path, initialised."""
    db_path = str(tmp_path / 'test.db')
    database.initialize(db_path)
    return db_path


@pytest.fixture
def sample_paper():
    """A sample Paper instance."""
    return Paper(
        paper_id='arxiv:2401.12345',
        source='arxiv',
        title='Attention Is All You Need (Again)',
        abstract='We revisit the transformer architecture with new improvements.',
        authors=['Alice Smith', 'Bob Jones'],
        published_date=date.today(),
        categories=['cs.LG', 'stat.ML'],
        app_category='ml',
        pdf_url='https://arxiv.org/pdf/2401.12345',
        abstract_url='https://arxiv.org/abs/2401.12345',
        citation_count=42,
        relevance_score=0.85,
        composite_score=0.72,
    )


@pytest.fixture
def sample_digest(sample_paper):
    """A sample Digest with one paper."""
    return Digest(
        digest_id='test-digest-001',
        week_start=date.today(),
        generated_at=datetime.utcnow(),
        papers={'ml': [sample_paper]},
        total_fetched=1,
        total_ranked=1,
        fetch_errors=[],
    )


@pytest.fixture
def user_profile():
    """Default user profile."""
    return UserProfile()
