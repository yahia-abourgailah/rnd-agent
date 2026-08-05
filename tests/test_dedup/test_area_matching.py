"""Areas were never deduplicated, so the same zone existed once per source and
every zone-level aggregate was split between the spellings.

The traps here are real pairs from the collected data: "New Capital City" and
"New Cairo City" score 80, HIGHER than the true pair "New Cairo"/"New Cairo
City" at 78 — so no threshold separates them and the guards must.
"""

import pytest

from dedup.matcher import cluster_entities
from dedup.normalize import normalize_area_name, normalize_name


def _cluster(name_a, name_b):
    return cluster_entities(
        [{"id": 1, "name": name_a}, {"id": 2, "name": name_b}],
        normalizer=normalize_area_name,
    )


@pytest.mark.parametrize(
    "name_a,name_b",
    [
        ("New Cairo", "New Cairo City"),
        ("El Sheikh Zayed", "Sheikh Zayed City"),
        ("Ain Sokhna", "Al Ain Al Sokhna"),
        ("Ras El Hekma", "Ras Al Hekma"),
        ("El Shorouk", "Shorouk City"),
    ],
)
def test_the_same_zone_spelled_differently_merges(name_a, name_b):
    assert _cluster(name_a, name_b) == [[1, 2]]


@pytest.mark.parametrize(
    "name_a,name_b",
    [
        ("New Capital City", "New Cairo City"),
        ("Heliopolis", "New Heliopolis"),
        ("South New Cairo", "New Cairo City"),
        ("Maadi", "Makadi"),
        ("North Coast Resorts", "North Coast-Sahel"),
    ],
)
def test_different_zones_are_not_merged(name_a, name_b):
    assert _cluster(name_a, name_b) == []


def test_city_is_not_stripped_for_non_area_names():
    """'city' is area-only noise on purpose: as a shared noise word it reduces
    the developer 'City Edge Developments' to 'edge' and merges it with the
    unrelated 'EDGE HOLDING'."""
    assert normalize_name("City Edge Developments") != normalize_name("EDGE HOLDING")

    assert cluster_entities(
        [{"id": 1, "name": "City Edge Developments"}, {"id": 2, "name": "EDGE HOLDING"}]
    ) == []
