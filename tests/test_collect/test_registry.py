import pytest

from collect.nawy import NawyCollector
from collect.property_finder import PropertyFinderCollector
from collect.registry import COLLECTOR_REGISTRY, get_collector_class


def test_known_sources_resolve():
    assert get_collector_class("nawy") is NawyCollector
    assert get_collector_class("property_finder") is PropertyFinderCollector


def test_unknown_source_names_the_known_ones():
    """A typo in a schedule must not surface as a bare KeyError at 3am."""
    with pytest.raises(ValueError) as exc:
        get_collector_class("nawi")

    assert "nawi" in str(exc.value)
    assert "nawy" in str(exc.value)


def test_every_registered_collector_declares_its_contract():
    """The registry key and the collector's own name must agree, or a scheduled
    run collects one source under another's floor."""
    for name, collector in COLLECTOR_REGISTRY.items():
        assert collector.name == name
        assert collector.min_projects > 0
