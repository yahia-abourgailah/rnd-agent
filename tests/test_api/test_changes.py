"""Nawy's minPrice moves as inventory sells, so a feed built on raw deltas would
fire constantly and be ignored within a week. This is the rule that decides
whether a move is worth reporting, so it is tested directly."""

from datetime import UTC, datetime, timedelta

from api.changes import detect_price_change

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _snaps(*prices):
    """Oldest first, one hour apart."""
    return [(NOW - timedelta(hours=len(prices) - 1 - i), p) for i, p in enumerate(prices)]


def test_a_move_above_the_threshold_is_reported():
    change = detect_price_change(_snaps(6_000_000, 7_200_000), min_change_pct=5)

    assert change is not None
    assert change.from_price == 6_000_000
    assert change.to_price == 7_200_000
    assert round(change.change_pct, 1) == 20.0


def test_drift_below_the_threshold_is_silent():
    """A unit selling nudges minPrice; that is not a launch."""
    assert detect_price_change(_snaps(40_500_000, 40_700_000), min_change_pct=5) is None


def test_a_fall_is_reported_with_a_negative_percentage():
    change = detect_price_change(_snaps(10_000_000, 8_000_000), min_change_pct=5)

    assert change is not None
    assert change.change_pct < 0


def test_a_spike_that_already_reverted_stays_quiet():
    """Overall 6.0 -> 6.1 is small, but the middle spike would look material if
    only the extremes were compared."""
    assert detect_price_change(
        _snaps(6_000_000, 9_000_000, 6_100_000), min_change_pct=5
    ) is None


def test_a_sustained_move_reports_even_with_a_wobble():
    """The latest step agrees with the overall direction, so this is real."""
    change = detect_price_change(
        _snaps(6_000_000, 6_800_000, 7_500_000), min_change_pct=5
    )

    assert change is not None
    assert change.from_price == 6_000_000
    assert change.to_price == 7_500_000


def test_a_material_move_whose_latest_step_reverses_is_not_reported():
    """Up 20% then turning back down: the direction is no longer trustworthy."""
    assert detect_price_change(
        _snaps(6_000_000, 8_000_000, 7_400_000), min_change_pct=5
    ) is None


def test_one_snapshot_cannot_show_a_change():
    assert detect_price_change(_snaps(6_000_000), min_change_pct=5) is None


def test_no_snapshots_is_not_a_crash():
    assert detect_price_change([], min_change_pct=5) is None


def test_a_price_appearing_for_the_first_time_is_not_a_change():
    """Unpublished prices are stored as NULL; going from nothing to a number is
    a new entrant, reported separately, not a price move."""
    snapshots = [(NOW - timedelta(hours=2), None), (NOW, 6_000_000)]

    assert detect_price_change(snapshots, min_change_pct=5) is None


def test_a_price_disappearing_is_not_a_change():
    snapshots = [(NOW - timedelta(hours=2), 6_000_000), (NOW, None)]

    assert detect_price_change(snapshots, min_change_pct=5) is None


def test_a_zero_starting_price_does_not_divide_by_zero():
    assert detect_price_change(_snaps(0, 6_000_000), min_change_pct=5) is None


def test_the_threshold_is_tunable():
    snapshots = _snaps(10_000_000, 10_300_000)

    assert detect_price_change(snapshots, min_change_pct=5) is None
    assert detect_price_change(snapshots, min_change_pct=1) is not None


def test_the_change_is_stamped_with_the_latest_observation():
    change = detect_price_change(_snaps(6_000_000, 7_200_000), min_change_pct=5)

    assert change.observed_at == NOW
