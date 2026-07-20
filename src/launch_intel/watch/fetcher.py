import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config.settings import settings
from launch_intel.models import ContentType, RawPage

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    # transport failures and timeouts: always worth a retry
    if isinstance(exc, (httpx.TransportError, TimeoutError)):
        return True
    # HTTP errors: only server-side / rate-limit codes (a 404 won't fix itself)
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    # Playwright timeout (imported lazily so httpx-only installs don't need it)
    return exc.__class__.__name__ == "TimeoutError" and "playwright" in type(exc).__module__


def _retrying():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable),
    )


class _PerHostRateLimiter:
    """Enforces a minimum delay between requests to the same host."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        async with self._lock:
            now = time.monotonic()
            last = self._last_request_at.get(host)
            if last is not None:
                elapsed = now - last
                remaining = self.min_interval_seconds - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_at[host] = time.monotonic()


class Fetcher:
    """
    Thin wrapper over httpx (JSON/plain HTTP endpoints) and Playwright
    (JS-rendered sites), with shared retry + per-host rate limiting so
    individual adapters don't reimplement this.
    """

    def __init__(
        self,
        timeout_seconds: float | None = None,
        rate_limit_seconds: float | None = None,
    ):
        self.timeout_seconds = timeout_seconds or settings.default_request_timeout_seconds
        self._rate_limiter = _PerHostRateLimiter(
            rate_limit_seconds or settings.default_rate_limit_per_host_seconds
        )

    @_retrying()
    async def fetch_json(self, url: str, **httpx_kwargs) -> RawPage:
        """Fetch a JSON/plain HTTP endpoint via httpx. No JS execution."""
        await self._rate_limiter.wait(url)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            response = await client.get(url, **httpx_kwargs)
            response.raise_for_status()
        return RawPage(
            url=url,
            content=response.text,
            content_type=ContentType.JSON,
            fetched_at=datetime.now(timezone.utc),
        )

    @_retrying()
    async def fetch_rendered_html(self, url: str, wait_for_selector: str | None = None) -> RawPage:
        """
        Fetch a JS-rendered page via Playwright and return the final DOM HTML.
        Import of playwright is deferred so environments that only crawl JSON
        sources don't need the browser binaries installed.
        """
        from playwright.async_api import async_playwright

        await self._rate_limiter.wait(url)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.playwright_headless)
            try:
                context = await browser.new_context(user_agent=settings.user_agent)
                page = await context.new_page()
                await page.goto(url, timeout=self.timeout_seconds * 1000)
                if wait_for_selector:
                    await page.wait_for_selector(
                        wait_for_selector, timeout=self.timeout_seconds * 1000
                    )
                html = await page.content()
            finally:
                await browser.close()
        return RawPage(
            url=url,
            content=html,
            content_type=ContentType.HTML,
            fetched_at=datetime.now(timezone.utc),
        )