from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from launch_intel.db.engine import session_scope
from launch_intel.db.tables import FetchLog, LaunchRow, RawContent
from launch_intel.models import ContentType, Launch, RawPage
from launch_intel.watch.change_detector import hash_content


def store_fetch(page: RawPage, source_name: str, content_hash: str, changed: bool) -> None:
    """Persist a fetched payload and log the fetch.

    Called for EVERY fetch, changed or not — an unchanged crawl costs one
    small log row, and the content itself is stored only once per hash.
    """
    with session_scope() as session:
        session.execute(
            insert(RawContent)
            .values(
                content_hash=content_hash,
                content=page.content,
                content_type=page.content_type.value,
                byte_size=len(page.content.encode("utf-8")),
                first_stored_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
        )
        session.add(
            FetchLog(
                source_name=source_name,
                url=page.url,
                content_hash=content_hash,
                fetched_at=page.fetched_at,
                changed=changed,
            )
        )


def latest_hash_for(url: str) -> str | None:
    """What change detection compares against — replaces the JSON state file."""
    with session_scope() as session:
        return session.scalar(
            select(FetchLog.content_hash)
            .where(FetchLog.url == url)
            .order_by(FetchLog.fetched_at.desc())
            .limit(1)
        )


def save_launches(launches: list[Launch]) -> int:
    """Persist extracted launches, storing each one's source text once.

    Every launch carries its full raw_content, and a page's worth of launches
    all share the same text — so the payload is upserted by hash and the rows
    reference it. 24 launches from one page cost one raw_content row, not 24
    copies of the same 6KB.
    """
    with session_scope() as session:
        for launch in launches:
            content_hash = hash_content(launch.raw_content)
            session.execute(
                insert(RawContent)
                .values(
                    content_hash=content_hash,
                    content=launch.raw_content,
                    content_type=ContentType.JSON.value
                    if launch.raw_content.lstrip().startswith(("{", "["))
                    else ContentType.HTML.value,
                    byte_size=len(launch.raw_content.encode("utf-8")),
                    first_stored_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            data = launch.model_dump(mode="json", exclude={"raw_content"})
            data["property_types"] = [str(t) for t in data["property_types"]]
            session.add(LaunchRow(**data, raw_content_hash=content_hash))
    return len(launches)