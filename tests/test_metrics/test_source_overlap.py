"""Coverage is the reason for adding sources, so it has to be measurable.

The existing source_coverage counts a project as shared only when it carries a
canonical_id — the duplicate side of a pair. The canonical side counts as
unique, so whichever source wins canonical looks like it contributes everything
by itself: Nawy reported 3 shared of 1,835, while 515 of its projects were the
canonical target of a Property Finder duplicate.

That matters when judging a new source. "Aqarmap adds 1,988 projects" is a very
different claim from "1,988, of which 1,900 are already in Nawy".
"""

from metrics.quality import source_overlap


class FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return self

    def all(self):
        return self._rows


def test_overlap_splits_shared_from_unique():
    overlap = source_overlap(FakeSession([("nawy", 100, 30), ("aqarmap", 80, 30)]))

    by_source = {row["source"]: row for row in overlap}
    assert by_source["nawy"]["shared"] == 30
    assert by_source["nawy"]["unique"] == 70
    assert by_source["aqarmap"]["unique"] == 50


def test_a_source_sharing_nothing_is_all_unique():
    overlap = source_overlap(FakeSession([("nawy", 100, 0)]))

    assert overlap[0]["unique"] == 100
    assert overlap[0]["shared"] == 0


def test_a_source_that_adds_no_coverage_is_visible_as_such():
    """The signal that a new source is redundant rather than additive."""
    overlap = source_overlap(FakeSession([("aqarmap", 1988, 1988)]))

    assert overlap[0]["unique"] == 0
