"""
ResearchRadar — DuckDB implementation with migrations and cleanup.

Note: DuckDB is used for its high-performance analytical capabilities 
and ease of use for structured paper storage.
"""

from __future__ import annotations

import json
import logging
import os
import duckdb
import time
from datetime import date, datetime
from typing import List, Optional

from app.core.config import DB_VERSION
from app.core.models import Digest, Paper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT NOT NULL,
    summary_llm     TEXT,
    authors         TEXT NOT NULL,
    published_date  TEXT NOT NULL,
    categories      TEXT NOT NULL,
    app_category    TEXT NOT NULL,
    pdf_url         TEXT,
    abstract_url    TEXT NOT NULL,
    citation_count  INTEGER DEFAULT 0,
    relevance_score REAL    DEFAULT 0.0,
    composite_score REAL    DEFAULT 0.0,
    fetched_at      TEXT NOT NULL,
    is_bookmarked   INTEGER DEFAULT 0,
    is_read         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS digests (
    digest_id     TEXT PRIMARY KEY,
    week_start    TEXT NOT NULL,
    generated_at  TEXT NOT NULL,
    total_fetched INTEGER,
    total_ranked  INTEGER,
    fetch_errors  TEXT,
    videos_json   TEXT
);

CREATE TABLE IF NOT EXISTS digest_papers (
    digest_id  TEXT NOT NULL,
    paper_id   TEXT NOT NULL,
    rank_order INTEGER NOT NULL,
    PRIMARY KEY (digest_id, paper_id)
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id TEXT PRIMARY KEY,
    joined_at TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection."""
    conn = duckdb.connect(db_path)
    return conn


def _retry_on_locked(func):
    """Placeholder for backward compatibility with SQLite functions."""
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Initialisation & Migrations
# ---------------------------------------------------------------------------

def initialize(db_path: str) -> None:
    """Create tables and run any pending migrations."""
    # Automatic migration from SQLite if needed
    sqlite_path = db_path.replace('.duckdb', '.db')
    if not os.path.exists(db_path) and os.path.exists(sqlite_path):
        try:
            _migrate_from_sqlite(sqlite_path, db_path)
        except Exception as e:
            logger.error("Failed to migrate from SQLite: %s", e)

    conn = get_connection(db_path)
    try:
        conn.execute(_SCHEMA_V1)
        # Set version if not present
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'db_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('db_version', ?)",
                [str(DB_VERSION)],
            )
        else:
            current = int(row[0])
            if current < DB_VERSION:
                run_migrations(conn, current, DB_VERSION)
        
        # Recovery: Ensure 'subscribers' exists
        try:
            conn.execute("SELECT 1 FROM subscribers LIMIT 1")
        except Exception:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    joined_at TEXT NOT NULL
                )
            """)
            logger.info('Recovery: Created missing subscribers table.')

    finally:
        conn.close()


def _migrate_from_sqlite(sqlite_path: str, duckdb_path: str) -> None:
    """Migrate data from SQLite to DuckDB using DuckDB's sqlite extension."""
    logger.info('Migrating data from SQLite (%s) to DuckDB (%s)', sqlite_path, duckdb_path)
    # Physical file connection
    conn = duckdb.connect(duckdb_path)
    try:
        conn.execute("INSTALL sqlite;")
        conn.execute("LOAD sqlite;")
        # Attach SQLite using standard ATTACH syntax
        conn.execute(f"ATTACH '{sqlite_path}' AS old_sqlite (TYPE SQLITE);")
        
        # Copy tables with prefix
        for table in ['meta', 'papers', 'digests', 'digest_papers', 'subscribers']:
            try:
                # Drop if exists (could happen if previous attempt failed partially)
                conn.execute(f"DROP TABLE IF EXISTS {table};")
                conn.execute(f"CREATE TABLE {table} AS SELECT * FROM old_sqlite.{table};")
                logger.info('Migrated table: %s', table)
            except Exception as e:
                logger.warning('Could not migrate table %s: %s', table, e)
        
        conn.execute("DETACH old_sqlite;")
    finally:
        conn.close()


def run_migrations(conn: duckdb.DuckDBPyConnection, current: int, target: int) -> None:
    """Apply sequential migrations from *current* to *target* version."""
    logger.info('Migrating DB from v%d to v%d', current, target)
    
    if current < 2:
        try:
            conn.execute("ALTER TABLE papers ADD COLUMN summary_llm TEXT")
        except Exception: pass

    if current < 3:
        try:
            conn.execute("ALTER TABLE digests ADD COLUMN videos_json TEXT")
        except Exception: pass

    if current < 4:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    joined_at TEXT NOT NULL
                )
            """)
        except Exception: pass

    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'db_version'",
        [str(target)],
    )


# ---------------------------------------------------------------------------
# Paper helpers
# ---------------------------------------------------------------------------

def _paper_to_row(paper: Paper) -> list:
    return [
        paper.paper_id,
        paper.source,
        paper.title,
        paper.abstract,
        paper.summary_llm,
        json.dumps(paper.authors),
        paper.published_date.isoformat(),
        json.dumps(paper.categories),
        paper.app_category,
        paper.pdf_url,
        paper.abstract_url,
        paper.citation_count,
        paper.relevance_score,
        paper.composite_score,
        paper.fetched_at.isoformat(),
        int(paper.is_bookmarked),
        int(paper.is_read),
    ]


def _row_to_paper(row) -> Paper:
    return Paper(
        paper_id=row[0],
        source=row[1],
        title=row[2],
        abstract=row[3],
        summary_llm=row[4],
        authors=json.loads(row[5]),
        published_date=date.fromisoformat(row[6]),
        categories=json.loads(row[7]),
        app_category=row[8],
        pdf_url=row[9],
        abstract_url=row[10],
        citation_count=row[11],
        relevance_score=row[12],
        composite_score=row[13],
        fetched_at=datetime.fromisoformat(row[14]),
        is_bookmarked=bool(row[15]),
        is_read=bool(row[16]),
    )


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

@_retry_on_locked
def save_digest(db_path: str, digest: Digest) -> None:
    """Transactional insert of a digest + all its papers."""
    conn = get_connection(db_path)
    try:
        conn.begin()

        # Insert digest record
        conn.execute(
            """INSERT OR REPLACE INTO digests
               (digest_id, week_start, generated_at, total_fetched,
                total_ranked, fetch_errors, videos_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                digest.digest_id,
                digest.week_start.isoformat(),
                digest.generated_at.isoformat(),
                digest.total_fetched,
                digest.total_ranked,
                json.dumps(digest.fetch_errors),
                json.dumps(digest.videos),
            ],
        )

        # Insert papers and link to digest
        rank = 0
        for category, papers in digest.papers.items():
            for paper in papers:
                conn.execute(
                    """INSERT OR REPLACE INTO papers
                       (paper_id, source, title, abstract, summary_llm, authors,
                        published_date, categories, app_category, pdf_url,
                        abstract_url, citation_count, relevance_score,
                        composite_score, fetched_at, is_bookmarked, is_read)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    _paper_to_row(paper),
                )
                rank += 1
                conn.execute(
                    """INSERT OR REPLACE INTO digest_papers
                       (digest_id, paper_id, rank_order) VALUES (?, ?, ?)""",
                    [digest.digest_id, paper.paper_id, rank],
                )

        conn.commit()
        logger.info('Saved digest %s with %d papers', digest.digest_id, rank)
    except Exception:
        conn.rollback()
        logger.exception('Failed to save digest — rolled back')
        raise
    finally:
        conn.close()


@_retry_on_locked
def get_latest_digest(db_path: str) -> Optional[Digest]:
    """Load the most recent digest."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT digest_id, week_start, generated_at, total_fetched, total_ranked, fetch_errors, videos_json FROM digests ORDER BY generated_at DESC LIMIT 1'
        ).fetchone()
        if row is None:
            return None

        digest = Digest(
            digest_id=row[0],
            week_start=date.fromisoformat(row[1]),
            generated_at=datetime.fromisoformat(row[2]),
            total_fetched=row[3],
            total_ranked=row[4],
            fetch_errors=json.loads(row[5] or '[]'),
            videos=json.loads(row[6] or '[]'),
        )

        # Load papers linked to this digest
        paper_rows = conn.execute(
            """SELECT p.* FROM papers p
               INNER JOIN digest_papers dp ON p.paper_id = dp.paper_id
               WHERE dp.digest_id = ?
               ORDER BY dp.rank_order""",
            [digest.digest_id],
        ).fetchall()

        papers_by_cat: dict = {}
        for pr in paper_rows:
            paper = _row_to_paper(pr)
            papers_by_cat.setdefault(paper.app_category, []).append(paper)
        digest.papers = papers_by_cat
        return digest
    finally:
        conn.close()


@_retry_on_locked
def get_papers(db_path: str, category: str, limit: int = 10) -> List[Paper]:
    """Get papers for a category, ordered by composite score."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM papers
               WHERE app_category = ?
               ORDER BY composite_score DESC
               LIMIT ?""",
            [category, limit],
        ).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()


@_retry_on_locked
def get_existing_paper_ids(db_path: str, candidate_ids: List[str]) -> set[str]:
    """Return a set of paper_ids that already exist in the database."""
    if not candidate_ids:
        return set()
    conn = get_connection(db_path)
    try:
        placeholders = ', '.join(['?'] * len(candidate_ids))
        query = f"SELECT paper_id FROM papers WHERE paper_id IN ({placeholders})"
        rows = conn.execute(query, candidate_ids).fetchall()
        existing = set(r[0] for r in rows)
        return existing
    finally:
        conn.close()


@_retry_on_locked
def toggle_bookmark(db_path: str, paper_id: str) -> bool:
    """Toggle bookmark state; returns the new state."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """UPDATE papers
               SET is_bookmarked = CASE WHEN is_bookmarked = 0 THEN 1 ELSE 0 END
               WHERE paper_id = ?""",
            [paper_id],
        )
        row = conn.execute(
            'SELECT is_bookmarked FROM papers WHERE paper_id = ?',
            [paper_id],
        ).fetchone()
        return bool(row[0]) if row else False
    finally:
        conn.close()


@_retry_on_locked
def mark_read(db_path: str, paper_id: str) -> None:
    """Mark a paper as read."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            'UPDATE papers SET is_read = 1 WHERE paper_id = ?',
            [paper_id],
        )
    finally:
        conn.close()


@_retry_on_locked
def get_bookmarked_papers(db_path: str) -> List[Paper]:
    """Return all bookmarked papers ordered by composite score."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM papers
               WHERE is_bookmarked = 1
               ORDER BY composite_score DESC"""
        ).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()


@_retry_on_locked
def add_subscriber(db_path: str, chat_id: str) -> bool:
    """Add a new subscriber if they don't exist. Returns True if new."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT chat_id FROM subscribers WHERE chat_id = ?',
            [chat_id]
        ).fetchone()
        if row:
            return False
        
        conn.execute(
            'INSERT INTO subscribers (chat_id, joined_at) VALUES (?, ?)',
            [chat_id, datetime.now().isoformat()]
        )
        return True
    finally:
        conn.close()


@_retry_on_locked
def get_all_subscribers(db_path: str) -> List[str]:
    """Get all registered Telegram chat IDs."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute('SELECT chat_id FROM subscribers').fetchall()
        return [str(r[0]) for r in rows]
    finally:
        conn.close()


@_retry_on_locked
def remove_subscriber(db_path: str, chat_id: str) -> None:
    """Remove a subscriber ($stop)."""
    conn = get_connection(db_path)
    try:
        conn.execute('DELETE FROM subscribers WHERE chat_id = ?', [chat_id])
    finally:
        conn.close()


@_retry_on_locked
def cleanup_old_data(db_path: str, days: int = 7) -> None:
    """Remove old papers and digests, keeping bookmarks."""
    logger.info('Cleaning up data older than %d days...', days)
    conn = get_connection(db_path)
    try:
        # Delete old links
        conn.execute(f"""
            DELETE FROM digest_papers 
            WHERE digest_id IN (
                SELECT digest_id FROM digests 
                WHERE CAST(generated_at AS DATE) < CURRENT_DATE - INTERVAL '{days}' DAY
            )
        """)
        
        # Delete old digests
        conn.execute(f"""
            DELETE FROM digests 
            WHERE CAST(generated_at AS DATE) < CURRENT_DATE - INTERVAL '{days}' DAY
        """)
        
        # Delete old papers (unless bookmarked)
        conn.execute(f"""
            DELETE FROM papers 
            WHERE is_bookmarked = 0 
            AND CAST(fetched_at AS DATE) < CURRENT_DATE - INTERVAL '{days}' DAY
        """)
        
        logger.info('Cleanup complete.')
    finally:
        conn.close()


@_retry_on_locked
def get_papers_for_period(db_path: str, days: int = 7) -> List[Paper]:
    """Get all papers fetched in the last N days."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"""SELECT * FROM papers 
               WHERE CAST(fetched_at AS DATE) > CURRENT_DATE - INTERVAL '{days}' DAY
               ORDER BY composite_score DESC"""
        ).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()
