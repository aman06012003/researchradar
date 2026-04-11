"""
ResearchRadar — SettingsScreen.

User-configurable interest keywords, ranking weights, and API keys.
All settings are persisted as JSON in the app data directory.
"""

from __future__ import annotations

import json
import logging
import os

from kivy.lang import Builder
from kivy.properties import (
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.screenmanager import Screen

logger = logging.getLogger(__name__)

_KV_PATH = os.path.join(os.path.dirname(__file__), 'kv', 'settings.kv')
if os.path.exists(_KV_PATH):
    Builder.load_file(_KV_PATH)

_DEFAULT_SETTINGS = {
    'interests': {
        'ml': 'deep learning transformers attention',
        'ai': 'artificial intelligence language models',
        'cs': 'software engineering algorithms',
        'neuroscience': 'synaptic plasticity cortex neurons',
        'bci': 'brain computer interface EEG decoding',
    },
    'weight_relevance': 0.60,
    'weight_citation': 0.30,
    'weight_recency': 0.10,
    'top_n': 5,
    'schedule_day': 'sun',
    'schedule_hour': 8,
    'semantic_scholar_key': '',
    'pubmed_key': '',
}


class SettingsScreen(Screen):
    """Settings screen with interest keywords, weights, and API keys."""

    # Interest text fields
    ml_keywords = StringProperty('')
    ai_keywords = StringProperty('')
    cs_keywords = StringProperty('')
    neuro_keywords = StringProperty('')
    bci_keywords = StringProperty('')

    # Weights
    weight_relevance = NumericProperty(0.60)
    weight_citation = NumericProperty(0.30)
    weight_recency = NumericProperty(0.10)

    # Other
    top_n = NumericProperty(5)
    semantic_scholar_key = StringProperty('')
    pubmed_key = StringProperty('')

    def on_enter(self):
        self._load_settings()

    def _get_settings_path(self) -> str:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, 'data_dir'):
            return os.path.join(app.data_dir, 'settings.json')
        return os.path.join(os.path.expanduser('~'), '.researchradar', 'settings.json')

    def _load_settings(self):
        path = self._get_settings_path()
        settings = dict(_DEFAULT_SETTINGS)

        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                settings.update(saved)
            except (json.JSONDecodeError, OSError):
                logger.warning('Could not load settings — using defaults')

        interests = settings.get('interests', {})
        self.ml_keywords = interests.get('ml', '')
        self.ai_keywords = interests.get('ai', '')
        self.cs_keywords = interests.get('cs', '')
        self.neuro_keywords = interests.get('neuroscience', '')
        self.bci_keywords = interests.get('bci', '')

        self.weight_relevance = settings.get('weight_relevance', 0.60)
        self.weight_citation = settings.get('weight_citation', 0.30)
        self.weight_recency = settings.get('weight_recency', 0.10)
        self.top_n = settings.get('top_n', 5)
        self.semantic_scholar_key = settings.get('semantic_scholar_key', '')
        self.pubmed_key = settings.get('pubmed_key', '')

    def save_settings(self):
        """Validate and persist settings to JSON."""
        # Normalise weights to sum to 1.0
        total = self.weight_relevance + self.weight_citation + self.weight_recency
        if total > 0:
            self.weight_relevance /= total
            self.weight_citation /= total
            self.weight_recency /= total

        settings = {
            'interests': {
                'ml': self.ml_keywords,
                'ai': self.ai_keywords,
                'cs': self.cs_keywords,
                'neuroscience': self.neuro_keywords,
                'bci': self.bci_keywords,
            },
            'weight_relevance': round(self.weight_relevance, 2),
            'weight_citation': round(self.weight_citation, 2),
            'weight_recency': round(self.weight_recency, 2),
            'top_n': int(self.top_n),
            'semantic_scholar_key': self.semantic_scholar_key,
            'pubmed_key': self.pubmed_key,
        }

        path = self._get_settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
            logger.info('Settings saved to %s', path)
        except OSError:
            logger.error('Failed to save settings', exc_info=True)

        # Apply to running app
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, 'apply_settings'):
            app.apply_settings(settings)
