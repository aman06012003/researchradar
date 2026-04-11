"""
ResearchRadar — TF-IDF relevance scorer.

Computes cosine similarity between paper text and the user interest profile.
Falls back to a hand-written bag-of-words implementation if scikit-learn
is not available (mobile build edge case).
"""

from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional

from app.core.models import Paper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try scikit-learn; fall back to pure-Python BoW
# ---------------------------------------------------------------------------
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as _cosine

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning('scikit-learn not available — using fallback BoW scorer')


class TfidfRanker:
    """Score papers against a user interest profile using TF-IDF cosine similarity."""

    def __init__(self, cache_dir: str = ''):
        self._cache_dir = cache_dir
        self._vectorizer = None
        self._profile_vectors: Dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit_profile(self, interests: Dict[str, str]) -> None:
        """
        Build / rebuild the TF-IDF model from user interest keywords.

        *interests*: ``{'ml': 'deep learning transformers', ...}``
        """
        if _HAS_SKLEARN:
            self._fit_sklearn(interests)
        else:
            self._fit_bow(interests)

    def score(self, paper: Paper) -> float:
        """
        Return relevance score in [0.0, 1.0] for a paper against its
        category's profile vector.
        """
        cat = paper.app_category
        text = f'{paper.title} {paper.abstract}'

        if _HAS_SKLEARN:
            return self._score_sklearn(text, cat)
        else:
            return self._score_bow(text, cat)

    def score_many(self, papers: List[Paper]) -> List[Paper]:
        """Set ``relevance_score`` on each paper in-place and return the list."""
        for p in papers:
            p.relevance_score = self.score(p)
        return papers

    # ------------------------------------------------------------------
    # scikit-learn implementation
    # ------------------------------------------------------------------

    def _fit_sklearn(self, interests: Dict[str, str]) -> None:
        corpus = list(interests.values())
        self._vectorizer = TfidfVectorizer(
            max_features=5000, stop_words='english'
        )
        self._vectorizer.fit(corpus)
        self._profile_vectors = {}
        for cat, text in interests.items():
            vec = self._vectorizer.transform([text])
            self._profile_vectors[cat] = vec
        self._save_cache()

    def _score_sklearn(self, text: str, category: str) -> float:
        if self._vectorizer is None or category not in self._profile_vectors:
            return 0.0
        paper_vec = self._vectorizer.transform([text])
        sim = _cosine(paper_vec, self._profile_vectors[category])
        return float(max(0.0, min(sim[0][0], 1.0)))

    # ------------------------------------------------------------------
    # Pure-Python bag-of-words fallback
    # ------------------------------------------------------------------

    def _fit_bow(self, interests: Dict[str, str]) -> None:
        self._bow_profiles: Dict[str, Dict[str, int]] = {}
        for cat, text in interests.items():
            self._bow_profiles[cat] = _word_freq(text.lower())

    def _score_bow(self, text: str, category: str) -> float:
        profile = getattr(self, '_bow_profiles', {}).get(category)
        if not profile:
            return 0.0
        paper_freq = _word_freq(text.lower())
        return _cosine_bow(paper_freq, profile)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _save_cache(self) -> None:
        if not self._cache_dir or not _HAS_SKLEARN:
            return
        path = os.path.join(self._cache_dir, 'tfidf_cache.pkl')
        try:
            with open(path, 'wb') as f:
                pickle.dump(
                    (self._vectorizer, self._profile_vectors), f
                )
        except Exception:
            logger.debug('Could not save TF-IDF cache', exc_info=True)

    def load_cache(self) -> bool:
        """Attempt to load a cached vectorizer. Returns True on success."""
        if not self._cache_dir or not _HAS_SKLEARN:
            return False
        path = os.path.join(self._cache_dir, 'tfidf_cache.pkl')
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'rb') as f:
                self._vectorizer, self._profile_vectors = pickle.load(f)
            return True
        except Exception:
            logger.warning('TF-IDF cache corrupt — rebuilding', exc_info=True)
            try:
                os.remove(path)
            except OSError:
                pass
            return False


# ---------------------------------------------------------------------------
# BoW helpers
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    'a an the is are was were be been being have has had do does did '
    'will would shall should may might can could of in to for on with '
    'at by from and or but not no nor so yet both either neither '
    'each every all any few more most other some such that this these '
    'those i me my we our you your he him his she her it its they them '
    'their what which who whom when where why how'.split()
)


def _word_freq(text: str) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for word in text.split():
        w = ''.join(c for c in word if c.isalnum())
        if w and w not in _STOPWORDS and len(w) > 2:
            freq[w] = freq.get(w, 0) + 1
    return freq


def _cosine_bow(a: Dict[str, int], b: Dict[str, int]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    mag_a = sum(v * v for v in a.values()) ** 0.5
    mag_b = sum(v * v for v in b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
