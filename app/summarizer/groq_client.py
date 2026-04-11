"""
ResearchRadar — Groq LLM summarizer.

Summarizes papers using Groq API (llama-3.1-8b-instant).
Follows user's requested structural (Idea, Method, Results) and
enforces rate limit delays (30 RPM).
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import requests
from app.core.config import (
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL, GROQ_DELAY
)
from app.core.models import Paper

logger = logging.getLogger(__name__)

class GroqSummarizer:
    """Handles LLM calls to Groq with rate-limiting and structured prompts."""

    def __init__(self, api_key: str = GROQ_API_KEY):
        self.api_key = api_key
        self.last_call_time = 0.0

    def summarize_paper(self, paper: Paper) -> Optional[str]:
        """
        Produce a structured summary with automatic retries for rate limits (429).
        """
        if not self.api_key:
            logger.info("Skip Groq summarization: NO API KEY.")
            return None

        prompt = (
            f"Summarize this abstract into three brief sections:\n"
            f"1. Idea: (The core concept)\n"
            f"2. Method: (The proposed approach)\n"
            f"3. Results: (Key findings)\n\n"
            f"Title: {paper.title}\n"
            f"Abstract: {paper.abstract}\n"
        )

        for attempt in range(3):  # Try up to 3 times for rate limits
            # RPM Delay
            elapsed = time.time() - self.last_call_time
            if elapsed < GROQ_DELAY:
                time.sleep(GROQ_DELAY - elapsed)

            try:
                logger.info(f"Summarizing [{paper.paper_id}] (Attempt {attempt+1})...")
                response = requests.post(
                    GROQ_BASE_URL,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": [
                            {"role": "system", "content": "You are a scientific assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 250
                    },
                    timeout=30
                )
                self.last_call_time = time.time()

                if response.status_code == 200:
                    data = response.json()
                    return data['choices'][0]['message']['content'].strip()

                elif response.status_code == 429:
                    # Rate limit hit (TPM/RPM)
                    wait_time = 5.0  # Default hold
                    try:
                        # Extract wait time from error message or header
                        err_msg = response.json().get('error', {}).get('message', '')
                        if 'Please try again in' in err_msg:
                            # Parse "850ms" or "1.2s"
                            parts = err_msg.split('Please try again in ')[1].split(' ')
                            time_str = parts[0]
                            if 'ms' in time_str:
                                wait_time = float(time_str.replace('ms', '')) / 1000.0 + 0.5
                            elif 's' in time_str:
                                wait_time = float(time_str.replace('s', '')) + 0.5
                    except: pass
                    
                    logger.warning(f"Groq 429! Waiting {wait_time:.2f}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Groq API error ({response.status_code}): {response.text}")
                    return None

            except Exception as exc:
                logger.error(f"Groq error: {exc}")
                time.sleep(2)

        return None

    def summarize_many(self, papers: List[Paper]):
        """
        Iterate through papers and update their summary_llm field.
        """
        for p in papers:
            # We only summarize if it doesn't already have a summary
            if not p.summary_llm:
                p.summary_llm = self.summarize_paper(p)
