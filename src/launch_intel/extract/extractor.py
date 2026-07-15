from datetime import datetime, timezone

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

from config.settings import settings
from launch_intel.extract.normalize import normalize_developer, normalize_zone
from launch_intel.extract.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_prompt
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


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = instructor.from_openai(OpenAI(api_key=settings.openai_api_key))
    return _client


def extract_launch(candidate: Candidate, client=None) -> Launch:
    """
    Run LLM extraction over a single candidate snippet and assemble a full
    Launch record. Low-confidence results are still returned — filtering
    on `confidence` is a decision for the caller (dedup/notify, in a later
    phase), not something extraction itself should silently drop.
    """
    client = client or _get_client()
    fields: ExtractedFields = client.chat.completions.create(
        model=settings.extraction_model,
        response_model=ExtractedFields,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_user_prompt(candidate.text)},
        ],
    )

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
