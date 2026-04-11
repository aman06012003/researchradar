"""
ResearchRadar — HomeScreen.

Displays the latest digest as a scrollable list of DigestCard widgets,
one per category.  Includes a "Refresh Now" FAB and empty-state onboarding.
"""

from __future__ import annotations

import logging
import threading

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen

from app.core.config import CATEGORY_LABELS

logger = logging.getLogger(__name__)

# Load KV
import os
_KV_PATH = os.path.join(os.path.dirname(__file__), 'kv', 'home.kv')
if os.path.exists(_KV_PATH):
    Builder.load_file(_KV_PATH)


class DigestCard(BoxLayout):
    """A single category card showing paper count and top paper title."""

    category_slug = StringProperty('')
    category_name = StringProperty('')
    paper_count = StringProperty('0')
    top_paper_title = StringProperty('No papers yet')
    top_score = StringProperty('—')

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            app = self._get_app()
            if app:
                app.show_detail(self.category_slug)
        return super().on_touch_up(touch)

    def _get_app(self):
        from kivy.app import App
        return App.get_running_app()


class HomeScreen(Screen):
    """Main screen showing the latest weekly digest."""

    is_fetching = BooleanProperty(False)
    last_fetched = StringProperty('Never')
    digest_cards = ListProperty([])

    def on_enter(self):
        """Load digest when screen becomes visible."""
        self.load_digest()

    def load_digest(self):
        """Load the latest digest from the database and populate cards."""
        from kivy.app import App
        app = App.get_running_app()
        if not app:
            return

        digest = app.get_latest_digest()
        container = self.ids.get('card_container')
        if container is None:
            return

        container.clear_widgets()

        if digest is None:
            self.last_fetched = 'Never — tap Fetch Now!'
            return

        self.last_fetched = digest.generated_at.strftime('%Y-%m-%d %H:%M')

        for cat_slug, papers in digest.papers.items():
            card = DigestCard()
            card.category_slug = cat_slug
            card.category_name = CATEGORY_LABELS.get(cat_slug, cat_slug.title())
            card.paper_count = str(len(papers))
            if papers:
                title = papers[0].title
                if len(title) > 70:
                    title = title[:67] + '...'
                card.top_paper_title = title
                card.top_score = f'{papers[0].composite_score:.2f}'
            container.add_widget(card)

    def trigger_fetch(self):
        """Run the weekly fetch in a background thread."""
        if self.is_fetching:
            return
        self.is_fetching = True
        self.last_fetched = 'Fetching...'

        from kivy.app import App
        app = App.get_running_app()

        def _run():
            try:
                app.run_fetch()
            except Exception:
                logger.exception('Background fetch failed')
            finally:
                Clock.schedule_once(lambda dt: self._on_fetch_done(), 0)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _on_fetch_done(self):
        self.is_fetching = False
        self.load_digest()
