"""
ResearchRadar — Pure data models.

All models are standard Python dataclasses with no external dependencies,
making them fully testable in isolation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional


@dataclass
class Paper:
    """A single research paper from any source."""

    paper_id:        str                    # arXiv ID or PubMed PMID — primary key
    source:          str                    # 'arxiv' | 'semantic_scholar' | 'pubmed'
    title:           str
    abstract:        str
    authors:         List[str]
    published_date:  date                   # UTC
    categories:      List[str]              # e.g. ['cs.LG', 'stat.ML']
    app_category:    str                    # mapped app category slug
    summary_llm:     Optional[str] = None   # Brief summary (Idea, Method, Results) via Groq
    pdf_url:         Optional[str] = None   # direct PDF link if available
    abstract_url:    str = ''               # canonical web page
    citation_count:  int   = 0
    relevance_score: float = 0.0            # set by ranker
    composite_score: float = 0.0            # set by ranker
    fetched_at:      datetime = field(default_factory=datetime.utcnow)
    is_bookmarked:   bool = False
    is_read:         bool = False


@dataclass
class Digest:
    """A weekly digest containing ranked papers per category."""

    digest_id:     str                              # UUID4 hex
    week_start:    date                             # Monday of the fetched week (ISO)
    generated_at:  datetime
    papers:        Dict[str, List[Paper]] = field(default_factory=dict)
    videos:        List[Dict[str, str]] = field(default_factory=list) # [{'title': '...', 'url': '...'}]
    total_fetched: int = 0
    total_ranked:  int = 0
    fetch_errors:  List[str] = field(default_factory=list)

    @classmethod
    def create_new(cls) -> 'Digest':
        """Factory: create a fresh Digest for this week."""
        today = datetime.utcnow()
        # ISO week starts Monday (weekday 0)
        monday = today.date()
        weekday = monday.weekday()
        monday = monday.__class__.fromordinal(monday.toordinal() - weekday)
        return cls(
            digest_id=uuid.uuid4().hex,
            week_start=monday,
            generated_at=today,
        )


@dataclass
class UserProfile:
    """User interest profile used by the ranker."""

    interests: Dict[str, str] = field(default_factory=lambda: {
        'ml':           'deep learning transformers attention',
        'ai':           'artificial intelligence language models',
        'cs':           'software engineering algorithms',
        'neuroscience': 'synaptic plasticity cortex neurons',
        'bci':          'brain computer interface EEG decoding',
    })
    weight_relevance: float = 0.60
    weight_citation:  float = 0.30
    weight_recency:   float = 0.10
    top_n_per_category: int = 5
