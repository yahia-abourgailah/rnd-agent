"""Duplicate-reference merging is pure, so it is tested without a database.

The backfill builds one areas list from two endpoints with complementary gaps;
collapsing that list last-one-wins discarded whichever fields the last row
lacked.
"""

from db.repository import _merge_duplicate_refs


def test_complementary_rows_merge_instead_of_overwriting():
    rows = [
        {"external_ref": "nawy:2", "name": "New Cairo", "slug": "new-cairo", "city": None},
        {"external_ref": "nawy:2", "name": "New Cairo", "slug": None, "city": "Cairo"},
    ]

    merged = _merge_duplicate_refs(rows)

    assert len(merged) == 1
    assert merged[0]["slug"] == "new-cairo"
    assert merged[0]["city"] == "Cairo"


def test_later_non_null_values_win():
    rows = [
        {"external_ref": "nawy:2", "name": "Old Name"},
        {"external_ref": "nawy:2", "name": "New Name"},
    ]

    assert _merge_duplicate_refs(rows)[0]["name"] == "New Name"


def test_distinct_refs_are_left_alone():
    rows = [{"external_ref": "nawy:1"}, {"external_ref": "nawy:2"}]

    assert len(_merge_duplicate_refs(rows)) == 2


def test_every_row_gets_an_id_for_the_insert_path():
    merged = _merge_duplicate_refs([{"external_ref": "nawy:1"}])

    assert merged[0]["id"] is not None


def test_merging_does_not_mutate_the_caller_s_rows():
    rows = [
        {"external_ref": "nawy:2", "city": None},
        {"external_ref": "nawy:2", "city": "Cairo"},
    ]

    _merge_duplicate_refs(rows)

    assert rows[0]["city"] is None
