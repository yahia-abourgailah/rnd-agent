"""Property Finder mapping, against a saved live payload.

This source had no fixture and no test at all — its mapping was written from an
assumed payload shape and never checked against a real one, which is how a feed
containing completed developments came to be flagged entirely as launches.
"""

import json
import pathlib

import pytest

from collect import property_finder as pf

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "live"
    / "property_finder_new_projects.json"
)


@pytest.fixture
def projects():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["projects"]


def test_completed_developments_are_not_counted_as_launches(projects):
    """The feed is called new-projects but carries finished ones: Mountain View
    Hyde Park has constructionPhase 'completed' and a 2023 delivery."""
    completed = [p for p in projects if p.get("constructionPhase") == "completed"]
    assert completed, "fixture no longer contains a completed project"

    for raw in completed:
        assert pf.map_project(raw).is_launch is False


def test_under_construction_projects_are_launches(projects):
    building = [p for p in projects if p.get("constructionPhase") == "under_construction"]
    assert building

    for raw in building:
        assert pf.map_project(raw).is_launch is True


def test_not_every_row_is_a_launch(projects):
    flags = [pf.map_project(raw).is_launch for raw in projects]

    assert any(flags) and not all(flags)


def test_slug_is_a_slug_not_a_url_path(projects):
    """shareUrl is '/en/new-projects/palm-hills/palm-hills-phase-5'; every other
    source stores a bare slug in this column."""
    for raw in projects:
        slug = pf.map_project(raw).slug
        if slug is not None:
            assert "/" not in slug


def test_delivery_date_is_a_year_matching_the_other_sources(projects):
    """Property Finder sends full ISO datetimes into a column Nawy fills with a
    year; the delivery-pipeline report had to work around the mismatch."""
    for raw in projects:
        project = pf.map_project(raw)
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4
            assert project.delivery_date.isdigit()


def test_property_types_are_canonical(projects):
    for raw in projects:
        for property_type in pf.map_project(raw).property_types:
            assert property_type == property_type.lower()
            assert " " not in property_type


def test_records_missing_an_id_or_title_are_skipped():
    assert pf.map_project({"title": "No id"}) is None
    assert pf.map_project({"id": "abc"}) is None


def test_projects_are_read_out_of_embedded_next_data(projects):
    """Guards the extraction path itself, not just the mapping."""
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(
            {
                "props": {
                    "pageProps": {
                        "searchResult": {
                            "data": {"projects": projects},
                            "meta": {"pagination": {"page": 1, "total": 57}},
                        }
                    }
                }
            }
        )
        + "</script></body></html>"
    )

    extracted, total_pages = pf._extract_projects(html)

    assert len(extracted) == len(projects)
    assert total_pages == 57


def test_a_page_without_next_data_yields_nothing_rather_than_raising():
    assert pf._extract_projects("<html><body>blocked</body></html>") == ([], 0)


def test_district_is_taken_at_the_same_granularity_as_nawy_zones(projects):
    location = next(p for p in projects if p.get("location", {}).get("fullName"))["location"]

    district, city = pf._district_and_city(location)

    assert district and city
    assert district != city
