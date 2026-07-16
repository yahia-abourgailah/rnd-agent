import pytest

from launch_intel.models import SourceTier, SourceType
from launch_intel.pipeline.tasks import load_source_config

REGISTRY_YAML = """\
sources:
  - name: demo
    tier: 1
    source_type: developer_site
    urls: ["https://example.com/launches"]
    crawl_frequency: "30m"
    adapter_name: generic_developer_site
"""


@pytest.fixture
def registry_path(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(REGISTRY_YAML, encoding="utf-8")
    return path


def test_load_source_config_parses_yaml_entry(registry_path):
    source = load_source_config.fn("demo", registry_path=registry_path)
    assert source.name == "demo"
    assert source.tier == SourceTier.TIER_1
    assert source.source_type == SourceType.DEVELOPER_SITE
    assert source.adapter_name == "generic_developer_site"


def test_load_source_config_unknown_name_raises(registry_path):
    with pytest.raises(ValueError, match="No source named"):
        load_source_config.fn("nope", registry_path=registry_path)
