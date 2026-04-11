"""
ResearchRadar — DetailScreen.

Displays ranked papers for a single category with bookmark & read
functionality.  Tapping a paper opens a modal with the full abstract.
"""

from __future__ import annotations

import logging
import webbrowser

from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen

logger = logging.getLogger(__name__)

import os
_KV_PATH = os.path.join(os.path.dirname(__file__), 'kv', 'detail.kv')
if os.path.exists(_KV_PATH):
    Builder.load_file(_KV_PATH)


class PaperRow(BoxLayout):
    """A single paper row in the detail list."""

    rank = StringProperty('1')
    title = StringProperty('')
    authors = StringProperty('')
    date_str = StringProperty('')
    score_text = StringProperty('0.00')
    is_bookmarked = BooleanProperty(False)
    paper_id = StringProperty('')
    abstract_url = StringProperty('')
    pdf_url = StringProperty('')
    abstract_text = StringProperty('')

    def toggle_bookmark(self):
        from kivy.app import App
        app = App.get_running_app()
        if app:
            new_state = app.toggle_bookmark(self.paper_id)
            self.is_bookmarked = new_state

    def show_detail(self):
        popup = PaperDetailPopup()
        popup.paper_title = self.title
        popup.paper_authors = self.authors
        popup.paper_abstract = self.abstract_text
        popup.paper_url = self.abstract_url
        popup.paper_pdf = self.pdf_url
        popup.open()


class PaperDetailPopup(ModalView):
    """Modal showing full paper details."""

    paper_title = StringProperty('')
    paper_authors = StringProperty('')
    paper_abstract = StringProperty('')
    paper_url = StringProperty('')
    paper_pdf = StringProperty('')

    def open_in_browser(self):
        if self.paper_url:
            try:
                webbrowser.open(self.paper_url)
            except Exception:
                logger.warning('Could not open browser')

    def open_pdf(self):
        if self.paper_pdf:
            try:
                webbrowser.open(self.paper_pdf)
            except Exception:
                logger.warning('Could not open PDF')


class DetailScreen(Screen):
    """Screen showing papers for a single category."""

    category_slug = StringProperty('')
    category_name = StringProperty('')
    week_range = StringProperty('')
    paper_rows = ListProperty([])

    def load_papers(self, category_slug: str):
        """Populate the screen with papers from the latest digest."""
        from kivy.app import App
        app = App.get_running_app()
        if not app:
            return

        from app.core.config import CATEGORY_LABELS
        self.category_slug = category_slug
        self.category_name = CATEGORY_LABELS.get(category_slug, category_slug.title())

        digest = app.get_latest_digest()
        container = self.ids.get('paper_container')
        if container is None:
            return
        container.clear_widgets()

        if digest is None:
            self.week_range = 'No data'
            return

        self.week_range = f'Week of {digest.week_start.isoformat()}'
        papers = digest.papers.get(category_slug, [])

        for i, paper in enumerate(papers, 1):
            row = PaperRow()
            row.rank = str(i)
            row.paper_id = paper.paper_id
            row.title = paper.title
            row.abstract_text = paper.abstract

            if paper.authors:
                if len(paper.authors) > 2:
                    row.authors = f'{paper.authors[0]} et al.'
                else:
                    row.authors = ', '.join(paper.authors)
            else:
                row.authors = 'Unknown'

            row.date_str = paper.published_date.isoformat()
            row.score_text = f'{paper.composite_score:.2f}'
            row.is_bookmarked = paper.is_bookmarked
            row.abstract_url = paper.abstract_url
            row.pdf_url = paper.pdf_url or ''

            container.add_widget(row)
