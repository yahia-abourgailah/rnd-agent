"""The window parser.

A window quietly wider than the caller asked for makes the feed look wrong
rather than empty, so an unparseable value is rejected instead of defaulted.
"""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from api.routes.launches import _window_start


def test_a_relative_window_is_that_many_days_back():
    start = _window_start("7d")

    assert (datetime.now(UTC) - start).days == 7


def test_an_iso_date_is_taken_literally():
    assert _window_start("2026-08-07").date() == datetime(2026, 8, 7).date()


def test_a_naive_iso_date_is_treated_as_utc():
    """Comparing a naive datetime against a timezone-aware column raises."""
    assert _window_start("2026-08-07").tzinfo is not None


def test_nonsense_is_rejected_rather_than_defaulted():
    with pytest.raises(HTTPException) as exc:
        _window_start("last tuesday")

    assert exc.value.status_code == 422
    assert "last tuesday" in exc.value.detail
