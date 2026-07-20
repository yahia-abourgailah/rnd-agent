import httpx
import pytest

from config.settings import settings
from launch_intel.watch.fetcher import Fetcher, _is_retryable


def test_404_is_not_retried():
    err = httpx.HTTPStatusError("nf", request=None, response=httpx.Response(404))
    assert _is_retryable(err) is False


def test_503_is_retried():
    err = httpx.HTTPStatusError("busy", request=None, response=httpx.Response(503))
    assert _is_retryable(err) is True


async def test_fetch_json_sends_configured_user_agent(httpx_mock):
    """Asserts against the setting, not a literal, so changing the crawler
    identity is a config decision that doesn't break the test suite."""
    httpx_mock.add_response(json={"ok": True})
    await Fetcher(rate_limit_seconds=0).fetch_json("https://example.com/api")
    assert httpx_mock.get_requests()[0].headers["User-Agent"] == settings.user_agent


@pytest.mark.asyncio
async def test_rate_limiter_delays_second_call_same_host():
    import time
    f = Fetcher(rate_limit_seconds=0.2)
    start = time.monotonic()
    await f._rate_limiter.wait("https://a.com/x")
    await f._rate_limiter.wait("https://a.com/y")
    assert time.monotonic() - start >= 0.2