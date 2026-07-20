from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

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
    # Defaults to "unknown" rather than being required: a model that forgets
    # to score itself shouldn't cost us an otherwise-valid launch. Launch
    # itself still requires confidence — we always supply it.
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("property_types", mode="before")
    @classmethod
    def _null_means_empty(cls, value):
        """LLMs routinely emit null for an absent list rather than []. Treat
        that as 'none mentioned' instead of failing the whole extraction."""
        return [] if value is None else value

    @field_validator("confidence", mode="before")
    @classmethod
    def _default_confidence(cls, value):
        """Some models omit confidence entirely; assume mid-confidence rather
        than discarding an otherwise valid launch."""
        return 0.5 if value is None else value


class ExtractedLaunches(BaseModel):
    """
    Wrapper schema handed to the LLM. One fetched page routinely advertises
    several projects/phases, so extraction returns a list — never assume a
    page maps to exactly one launch.
    """

    launches: list[ExtractedFields] = Field(default_factory=list)


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
        schema=ExtractedLaunches,
    )


def _to_launch(fields: ExtractedFields, candidate: Candidate) -> Launch:
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


def extract_launches(candidate: Candidate, scraper: Scraper | None = None) -> list[Launch]:
    """
    Run LLM extraction over one candidate and assemble every Launch it
    describes. Returns a list because a single page routinely advertises
    several projects or phases.

    Low-confidence results are still returned — filtering on `confidence` is a
    decision for the caller (dedup/notify, in a later phase), not something
    extraction should silently drop.
    """
    scraper = scraper or _default_scraper(candidate)
    result = scraper.run()

    # ScrapeGraphAI returns a plain dict shaped like the schema; validate it
    # back into our model so downstream code always gets typed, checked data.
    if isinstance(result, ExtractedLaunches):
        extracted = result
    else:
        extracted = ExtractedLaunches.model_validate(result)

    return [_to_launch(fields, candidate) for fields in extracted.launches]
