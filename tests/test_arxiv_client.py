"""
Tests for app.fetcher.arxiv_client — arXiv Atom API client.
"""

from unittest.mock import MagicMock
from datetime import date

import pytest

from app.fetcher import arxiv_client
from app.fetcher.http_session import FetchTimeoutError, RetrySession


# Sample arXiv Atom XML fixture
_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345</id>
    <title>A Great Paper On Transformers</title>
    <summary>We propose a novel architecture for sequence modeling.</summary>
    <published>2026-04-01T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.LG"/>
    <category term="stat.ML"/>
    <link title="pdf" href="https://arxiv.org/pdf/2401.12345"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.12346</id>
    <title>Another Paper</title>
    <summary>More research on deep learning.</summary>
    <published>2026-04-02T00:00:00Z</published>
    <author><name>Charlie Brown</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>
"""

_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""

_MALFORMED_XML = """<not valid xml at all"""

_MISSING_ABSTRACT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.99999</id>
    <title>No Abstract Paper</title>
    <published>2026-04-01T00:00:00Z</published>
    <author><name>Test Author</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>
"""


def _mock_session(text: str, status: int = 200):
    session = MagicMock(spec=RetrySession)
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    session.get.return_value = resp
    return session


class TestFetchPapers:
    def test_success(self):
        session = _mock_session(_SAMPLE_XML)
        papers = arxiv_client.fetch_papers('ml', ['cs.LG', 'stat.ML'], session)
        assert len(papers) == 2
        assert papers[0].paper_id == 'arxiv:2401.12345'
        assert papers[0].source == 'arxiv'
        assert papers[0].title == 'A Great Paper On Transformers'
        assert 'Alice Smith' in papers[0].authors
        assert papers[0].app_category == 'ml'

    def test_empty_results(self):
        session = _mock_session(_EMPTY_XML)
        papers = arxiv_client.fetch_papers('ml', ['cs.LG'], session)
        assert papers == []

    def test_malformed_xml(self):
        session = _mock_session(_MALFORMED_XML)
        papers = arxiv_client.fetch_papers('ml', ['cs.LG'], session)
        assert papers == []

    def test_timeout(self):
        session = MagicMock(spec=RetrySession)
        session.get.side_effect = FetchTimeoutError('timeout')
        papers = arxiv_client.fetch_papers('ml', ['cs.LG'], session)
        assert papers == []

    def test_missing_abstract_skipped(self):
        session = _mock_session(_MISSING_ABSTRACT_XML)
        papers = arxiv_client.fetch_papers('ml', ['cs.LG'], session)
        assert papers == []  # entry skipped due to missing abstract
