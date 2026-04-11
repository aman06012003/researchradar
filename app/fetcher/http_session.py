"""
ResearchRadar — RetrySession.

Single point of contact for all outbound HTTP.
No other module calls `requests` directly.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional, Set

import requests

from app.core.config import (
    HTTP_BACKOFF_BASE,
    HTTP_BACKOFF_MAX,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT,
    RETRY_STATUS_CODES,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class FetchError(Exception):
    """Base exception for all fetch-related errors."""
    pass


class FetchTimeoutError(FetchError):
    """Raised when a request times out."""
    pass


class FetchNetworkError(FetchError):
    """Raised on connection / DNS errors."""
    pass


class SourceNotFoundError(FetchError):
    """Raised on HTTP 404."""
    pass


class SourceAuthError(FetchError):
    """Raised on HTTP 401 / 403."""
    pass


class MaxRetriesExceeded(FetchError):
    """Raised when all retry attempts are exhausted."""
    pass


# ---------------------------------------------------------------------------
# RetrySession
# ---------------------------------------------------------------------------

class RetrySession:
    """HTTP GET wrapper with exponential back-off, retries, and error mapping."""

    def __init__(
        self,
        max_retries: int = HTTP_MAX_RETRIES,
        backoff_base: int = HTTP_BACKOFF_BASE,
        backoff_max: int = HTTP_BACKOFF_MAX,
        timeout: int = HTTP_TIMEOUT,
        retry_status_codes: Optional[Set[int]] = None,
    ):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.timeout = timeout
        self.retry_status_codes = retry_status_codes or RETRY_STATUS_CODES
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': USER_AGENT})

    # ------------------------------------------------------------------
    def get(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> requests.Response:
        """
        GET *url* with automatic retries and exponential back-off.

        Returns a `requests.Response` with status 200 on success.
        Raises a typed `FetchError` subclass on failure.
        """
        merged_headers = dict(self._session.headers)
        if headers:
            merged_headers.update(headers)

        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    headers=merged_headers,
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    return resp

                if resp.status_code in self.retry_status_codes:
                    wait = min(
                        self.backoff_base ** attempt + random.uniform(0, 1),
                        self.backoff_max,
                    )
                    logger.warning(
                        'HTTP %d from %s — retrying in %.1fs (attempt %d/%d)',
                        resp.status_code, url, wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    raise SourceNotFoundError(f'404 Not Found: {url}')

                if resp.status_code in {400, 401, 403}:
                    raise SourceAuthError(
                        f'HTTP {resp.status_code} from {url}'
                    )

                # Other 4xx / unexpected codes
                raise FetchError(
                    f'HTTP {resp.status_code} from {url}: '
                    f'{resp.text[:200]}'
                )

            except requests.exceptions.Timeout as exc:
                raise FetchTimeoutError(f'Timeout on {url}') from exc

            except requests.exceptions.ConnectionError as exc:
                raise FetchNetworkError(f'Connection error on {url}') from exc

            except requests.exceptions.RequestException as exc:
                raise FetchError(f'Request error on {url}: {exc}') from exc

            except FetchError:
                raise  # re-raise our own typed exceptions

        raise MaxRetriesExceeded(
            f'All {self.max_retries} retries exhausted for {url}'
        )

    # ------------------------------------------------------------------
    def post(
        self,
        url: str,
        json: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> requests.Response:
        """POST with the same retry / error logic as GET."""
        merged_headers = dict(self._session.headers)
        if headers:
            merged_headers.update(headers)

        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    url,
                    json=json,
                    headers=merged_headers,
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    return resp

                if resp.status_code in self.retry_status_codes:
                    wait = min(
                        self.backoff_base ** attempt + random.uniform(0, 1),
                        self.backoff_max,
                    )
                    logger.warning(
                        'POST %d from %s — retrying in %.1fs (attempt %d/%d)',
                        resp.status_code, url, wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    raise SourceNotFoundError(f'404 Not Found: {url}')

                if resp.status_code in {400, 401, 403}:
                    raise SourceAuthError(
                        f'HTTP {resp.status_code} from {url}'
                    )

                raise FetchError(
                    f'HTTP {resp.status_code} from {url}: '
                    f'{resp.text[:200]}'
                )

            except requests.exceptions.Timeout as exc:
                raise FetchTimeoutError(f'Timeout on {url}') from exc

            except requests.exceptions.ConnectionError as exc:
                raise FetchNetworkError(f'Connection error on {url}') from exc

            except requests.exceptions.RequestException as exc:
                raise FetchError(f'Request error on {url}: {exc}') from exc

            except FetchError:
                raise

        raise MaxRetriesExceeded(
            f'All {self.max_retries} retries exhausted for POST {url}'
        )
