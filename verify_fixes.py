import os
import sqlite3
from datetime import date, datetime, timedelta
from app.core.models import Paper, Digest, UserProfile
from app.core import database
from app.fetcher import fetch_pipeline, arxiv_client
from app.fetcher.http_session import RetrySession

DB_TEST = "test_verify.db"

def setup_test_db():
    if os.path.exists(DB_TEST):
        os.remove(DB_TEST)
    database.initialize(DB_TEST)

def test_arxiv_date_filtering():
    print("\n--- Testing ArXiv Date Filtering ---")
    session = RetrySession()
    # Fetch papers from 1 day ago to today
    # We'll use a category that definitely has recent papers
    papers = arxiv_client.fetch_papers("ml", ["cs.LG"], session, days_back=1)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    all_in_range = True
    for p in papers:
        if not (yesterday <= p.published_date <= today):
            print(f"FAILED: Paper {p.paper_id} has date {p.published_date} which is outside [{yesterday}, {today}]")
            all_in_range = False
    
    if all_in_range:
        print(f"SUCCESS: All {len(papers)} papers are within the 1-day range.")
    else:
        print("FAILURE in date filtering.")

def test_database_deduplication():
    print("\n--- Testing Database Deduplication ---")
    setup_test_db()
    
    # Create a dummy paper and save it to DB
    dummy_paper = Paper(
        paper_id="arxiv:1234.5678",
        source="arxiv",
        title="Existing Paper",
        abstract="Already sent",
        authors=["Author A"],
        published_date=date.today(),
        categories=["cs.LG"],
        app_category="ml"
    )
    
    digest = Digest.create_new()
    digest.papers = {"ml": [dummy_paper]}
    database.save_digest(DB_TEST, digest)
    
    # Now try to "fetch" a list containing that same paper
    fetched_papers = {
        "ml": [
            dummy_paper, # Existing
            Paper(
                paper_id="arxiv:9999.8888", # New
                source="arxiv",
                title="New Paper",
                abstract="New research",
                authors=["Author B"],
                published_date=date.today(),
                categories=["cs.LG"],
                app_category="ml"
            )
        ]
    }
    
    # Run the filtering logic manually (taken from fetch_pipeline)
    flat_all = [p for cat_list in fetched_papers.values() for p in cat_list]
    existing_ids = database.get_existing_paper_ids(DB_TEST, [p.paper_id for p in flat_all])
    
    filtered_papers = {}
    for cat in fetched_papers:
        filtered_papers[cat] = [p for p in fetched_papers[cat] if p.paper_id not in existing_ids]
    
    if len(filtered_papers["ml"]) == 1 and filtered_papers["ml"][0].paper_id == "arxiv:9999.8888":
        print("SUCCESS: Existing paper was correctly filtered out.")
    else:
        print(f"FAILURE: Expected 1 paper, got {len(filtered_papers['ml'])}")
        for p in filtered_papers["ml"]:
            print(f" - {p.paper_id}")

if __name__ == "__main__":
    test_arxiv_date_filtering()
    test_database_deduplication()
    if os.path.exists(DB_TEST):
        os.remove(DB_TEST)
