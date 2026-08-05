"""Dedup regressions, named for the real-world case each one protects.

A false merge is far more damaging than a missed one here: merging two real
projects deletes a competitor launch from every downstream count, and nothing
downstream can tell that it happened.
"""

from dedup.matcher import cluster_entities
from dedup.normalize import normalize_name


def test_same_name_under_different_developers_is_not_merged():
    """Blocking existed to prevent this, but the exact-match pass ignored it."""
    items = [
        {"id": 1, "name": "The Address", "developer_id": "dev-a"},
        {"id": 2, "name": "The Address", "developer_id": "dev-b"},
    ]

    assert cluster_entities(items, block_key="developer_id") == []


def test_same_name_under_the_same_developer_is_still_merged():
    items = [
        {"id": 1, "name": "The Address", "developer_id": "dev-a"},
        {"id": 2, "name": "The  Address", "developer_id": "dev-a"},
    ]

    assert cluster_entities(items, block_key="developer_id") == [[1, 2]]


def test_roman_numeral_phases_stay_distinct():
    """'Badya Phase I' vs 'Badya Phase II' scored 96 and merged: the number
    guard only recognised Arabic digits, so a whole phase launch vanished."""
    items = [{"id": 1, "name": "Badya Phase I"}, {"id": 2, "name": "Badya Phase II"}]

    assert cluster_entities(items) == []


def test_digit_phases_stay_distinct():
    items = [{"id": 1, "name": "La Vista 1"}, {"id": 2, "name": "La Vista 2"}]

    assert cluster_entities(items) == []


def test_the_same_phase_in_either_notation_does_merge():
    items = [{"id": 1, "name": "Badya Phase II"}, {"id": 2, "name": "Badya Phase 2"}]

    assert cluster_entities(items) == [[1, 2]]


def test_names_made_entirely_of_noise_words_still_dedup():
    """These normalised to "" and were skipped outright, so duplicates of
    'Egypt Real Estate Group' could never be found."""
    assert normalize_name("Egypt Real Estate Group") != ""

    items = [
        {"id": 1, "name": "Egypt Real Estate Group"},
        {"id": 2, "name": "Egypt Real Estate  Group"},
    ]
    assert cluster_entities(items) == [[1, 2]]


def test_legal_suffixes_still_collapse():
    items = [{"id": 1, "name": "SODIC"}, {"id": 2, "name": "SODIC Developments"}]

    assert cluster_entities(items) == [[1, 2]]


def test_unrelated_names_are_left_alone():
    items = [{"id": 1, "name": "Zed East"}, {"id": 2, "name": "Zed West"}]

    assert cluster_entities(items) == []


def test_one_swapped_word_is_not_a_duplicate():
    """'Elan Villas Cairo Gate' and 'Eden Villas Cairo Gate' are different Emaar
    projects that scored 91 overall, because only one of four words differs."""
    items = [
        {"id": 1, "name": "ELAN Villas Cairo Gate"},
        {"id": 2, "name": "Eden Villas Cairo Gate"},
    ]

    assert cluster_entities(items) == []


def test_a_near_identical_word_still_merges():
    """The guard must not block real variants: tower/towers, masqad/maqsad."""
    assert cluster_entities(
        [{"id": 1, "name": "Modon Mega Tower"}, {"id": 2, "name": "Modon Mega Towers"}]
    ) == [[1, 2]]
    assert cluster_entities(
        [{"id": 1, "name": "Al Masqad Residences"}, {"id": 2, "name": "Al Maqsad Residences"}]
    ) == [[1, 2]]


def test_compass_point_variants_stay_apart():
    items = [{"id": 1, "name": "Swan Lake West"}, {"id": 2, "name": "Swan Lake East"}]

    assert cluster_entities(items) == []
