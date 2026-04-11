"""
Tests for app.fetcher.pubmed_client — PubMed E-utilities client.
"""

from unittest.mock import MagicMock

import pytest

from app.fetcher import pubmed_client
from app.fetcher.http_session import FetchError, RetrySession


_ESEARCH_RESPONSE = {
    'esearchresult': {
        'count': '1',
        'webenv': 'WEBENV_TOKEN',
        'querykey': '1',
    }
}

_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <ArticleTitle>Neural Oscillations in Cortex</ArticleTitle>
        <Abstract>
          <AbstractText Label="Background">We studied oscillations.</AbstractText>
          <AbstractText Label="Results">Theta power increased.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <ForeName>Jane</ForeName>
            <LastName>Neuroscientist</LastName>
          </Author>
        </AuthorList>
      </Article>
      <DateCompleted>
        <Year>2026</Year>
        <Month>03</Month>
        <Day>15</Day>
      </DateCompleted>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _make_session():
    session = MagicMock(spec=RetrySession)

    # ESearch response
    esearch_resp = MagicMock()
    esearch_resp.json.return_value = _ESEARCH_RESPONSE

    # EFetch response
    efetch_resp = MagicMock()
    efetch_resp.text = _EFETCH_XML

    session.get.side_effect = [esearch_resp, efetch_resp]
    return session


class TestFetchPapers:
    def test_success(self):
        session = _make_session()
        papers = pubmed_client.fetch_papers(
            'neuroscience', 'Neurosciences[MeSH]', session
        )
        assert len(papers) == 1
        assert papers[0].paper_id == 'pubmed:12345678'
        assert papers[0].source == 'pubmed'
        assert 'Neural Oscillations' in papers[0].title
        assert 'Background: We studied' in papers[0].abstract
        assert 'Jane Neuroscientist' in papers[0].authors

    def test_zero_results(self):
        session = MagicMock(spec=RetrySession)
        resp = MagicMock()
        resp.json.return_value = {'esearchresult': {'count': '0'}}
        session.get.return_value = resp

        papers = pubmed_client.fetch_papers(
            'neuroscience', 'Neurosciences[MeSH]', session
        )
        assert papers == []

    def test_fetch_error(self):
        session = MagicMock(spec=RetrySession)
        session.get.side_effect = FetchError('network')
        papers = pubmed_client.fetch_papers(
            'bci', 'Brain-Computer Interfaces[MeSH]', session
        )
        assert papers == []
