from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from config.settings import settings
from launch_intel.extract.normalize import normalize_developer, normalize_zone
from launch_intel.extract.prompts import EXTRACTION_PROMPT
from launch_intel.models import Candidate, Launch, LaunchType, PropertyType, SizeRange


class ExtractedFields(BaseModel):
    """
    What the LLM is asked to produce — a subset of Launch. Fields the
    surrounding pipeline already knows (id, source_url, source_type,
    first_seen_at, raw_content) are filled in by extract_launch, not the LLM.
    """

    developer: str | None = None
    project_name: str
    launch_type: LaunchType
    location_raw: str | None = None
    zone: str | None = None
    property_types: list[PropertyType] = Field(default_factory=list)
    unit_sizes: SizeRange | None = None
    price_from: float | None = None
    price_per_sqm: float | None = None
    payment_plan: str | None = None
    delivery_date: str | None = None
    availability: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class Scraper(Protocol):
    """
    Minimal seam over ScrapeGraphAI so tests can substitute a fake and run
    offline without an API key. Any callable returning the extracted dict works.
    """

    def run(self) -> dict: ...


def build_graph_config() -> dict:
    """ScrapeGraphAI config assembled from settings — no hardcoded secrets."""
    llm: dict = {
        "api_key": settings.openai_api_key,
        "model": settings.extraction_model,
    }
    # Optional: route to an OpenAI-compatible endpoint (self-hosted model,
    # company gateway) instead of api.openai.com.
    if settings.llm_base_url:
        llm["base_url"] = settings.llm_base_url
    # Optional: declare the context window for models ScrapeGraphAI doesn't know.
    if settings.llm_model_tokens:
        llm["model_tokens"] = settings.llm_model_tokens

    return {
        "llm": llm,
        "verbose": False,
        # We already fetched the content ourselves (watch/fetcher.py), so
        # ScrapeGraphAI never needs to open a browser here.
        "headless": True,
    }


def _default_scraper(candidate: Candidate) -> Scraper:
    from scrapegraphai.graphs import SmartScraperGraph

    # `source` is the already-fetched text, NOT a URL. This is deliberate: the
    # watch stage fetches cheaply and change_detector filters out unchanged
    # pages, so the expensive LLM pass only ever runs on new content. Handing
    # ScrapeGraphAI a URL here would re-fetch and defeat that cost control.
    return SmartScraperGraph(
        prompt=EXTRACTION_PROMPT,
        source=candidate.text,
        config=build_graph_config(),
        schema=ExtractedFields,
    )


def extract_launch(candidate: Candidate, scraper: Scraper | None = None) -> Launch:
    """
    Run LLM extraction over a single candidate snippet and assemble a full
    Launch record. Low-confidence results are still returned — filtering
    on `confidence` is a decision for the caller (dedup/notify, in a later
    phase), not something extraction itself should silently drop.
    """
    scraper = scraper or _default_scraper(candidate)
    result = scraper.run()

    # ScrapeGraphAI returns a plain dict shaped like the schema; validate it
    # back into our model so downstream code always gets typed, checked data.
    fields = result if isinstance(result, ExtractedFields) else ExtractedFields.model_validate(result)

    field_values = fields.model_dump()
    field_values["developer"] = normalize_developer(field_values["developer"])
    field_values["zone"] = normalize_zone(field_values["zone"])

    return Launch(
        **field_values,
        source_url=candidate.source_url,
        source_type=candidate.source_type,
        first_seen_at=datetime.now(timezone.utc),
        raw_content=candidate.text,
    )
