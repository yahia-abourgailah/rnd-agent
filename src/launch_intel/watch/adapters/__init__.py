from launch_intel.watch.adapters.generic_developer_site import GenericDeveloperSiteAdapter
from launch_intel.watch.adapters.nawy import NawyAdapter
from launch_intel.watch.adapters.palm_hills import PalmHillsAdapter
from launch_intel.watch.adapters.property_finder import PropertyFinderAdapter
from launch_intel.watch.adapters.sodic import SodicAdapter
from launch_intel.watch.base import BaseAdapter

# Registry keyed on SourceConfig.adapter_name — how config/sources.yaml
# selects which adapter class runs a given source.
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    GenericDeveloperSiteAdapter.adapter_name: GenericDeveloperSiteAdapter,
    NawyAdapter.adapter_name: NawyAdapter,
    PropertyFinderAdapter.adapter_name: PropertyFinderAdapter,
    SodicAdapter.adapter_name: SodicAdapter,
    PalmHillsAdapter.adapter_name: PalmHillsAdapter,
}


def get_adapter_class(adapter_name: str) -> type[BaseAdapter]:
    try:
        return ADAPTER_REGISTRY[adapter_name]
    except KeyError:
        raise ValueError(
            f"No adapter registered for adapter_name={adapter_name!r}. "
            f"Known adapters: {sorted(ADAPTER_REGISTRY)}"
        ) from None
