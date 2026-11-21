"""The only door from the portal into the AI engine.

Suhaib's views import from here and nowhere else in ai_engine. Signatures
are frozen (gate 1 of the plan); what happens inside grows module by module.

    ping(message, user=None)            -> AgentRun          (Module 1, live)
    index_source(obj, path=None, text=None) -> int (chunks)  (Module 2, live)
    remove_source(obj)                  -> None              (Module 2, live)
    ask(question, user=None)            -> dict              (Module 2, live)
    related_links(topic)                -> dict              (Module 3b, live)
    build_outreach_kit(resource, user=None) -> int (kit id)  (Module 3, live)
    kit_status(kit_id)                  -> str               (Module 3, live)
    published_kits(limit=6)             -> list[OutreachKit] (Module 3, live)
    suggest_next_resources(user, limit=6) -> list[(ct_id, object_id)] (Module 4, live)
    suggest_next_kits(user, limit=4)    -> list[OutreachKit] (Module 4, live)

Until a function's module lands it returns sample data of the final shape,
so pages can be built and tested against it today.
"""

from __future__ import annotations

from typing import Any

from . import ask_pipeline, ingest
from .agents import build_agent
from .llm import ProviderInfo, resolve_provider
from .models import AgentRun
from .runner import run_sync, tracked_run


def engine_status() -> ProviderInfo:
    return resolve_provider()


# --- Module 1 -----------------------------------------------------------------
def ping(message: str, user=None) -> AgentRun:
    """Send one message to the Librarian agent through Semantic Kernel."""

    async def _call(recorder) -> str:
        agent = build_agent("Librarian")
        recorder.step("Librarian", "input", message)
        response = await agent.get_response(messages=message)
        recorder.add_tokens(response.message.metadata.get("usage"))
        return str(response.message.content)

    with tracked_run(AgentRun.Pipeline.PING, message, user) as rec:
        reply = run_sync(_call(rec))
        rec.step("Librarian", "reply", reply)
        rec.run.output = {"reply": reply}
    return rec.run


# --- Contract previews (replaced in later modules) -----------------------------
# --- Module 2 -----------------------------------------------------------------
def index_source(obj, path=None, text=None) -> int:
    """Make a resource searchable. Call it after a Resource is saved with its file:
    ``services.index_source(resource, path=resource.file.path)``. Returns chunks written.
    Raises ingest.UnsupportedFile for file types it cannot read."""
    return ingest.index_source(obj, path=path, text=text)


def remove_source(obj) -> None:
    """Forget a resource (call it when a Resource is deleted)."""
    ingest.remove_source(obj)


def ask(question: str, user=None) -> dict[str, Any]:
    """Answer from the repository only.
    Returns {"answer": str, "citations": [{"n", "title", "url", "locator", "excerpt",
    "content_type", "object_id", "resource_id"}], "trust_score": 0-100, "in_repository": bool, "run_id": int,
    "search_query": str (short topic keywords, good for related_links)}
    When the repository has no good answer, in_repository is False and answer is a polite fallback."""
    return ask_pipeline.ask(question, user).as_dict()


def related_links(topic: str) -> dict[str, Any]:
    """Related videos and websites from the open web for any topic.
    Returns {"query", "videos": [{"title", "url", "channel", "thumbnail", "site"}],
    "sites": [{"title", "url", "snippet", "site"}], "more": [{"title", "url", "site"}]}.
    Never raises: a failing provider just gives fewer links."""
    from . import web_links

    try:
        return web_links.related_links(topic)
    except Exception:  # noqa: BLE001
        return {"query": topic, "videos": [], "sites": [], "more": web_links.search_links(topic)}


# --- Module 3 -----------------------------------------------------------------
def build_outreach_kit(resource, user=None) -> int:
    """Start making an outreach kit from an indexed resource, in the background.
    Returns the kit id at once; poll kit_status(kit_id). Index the resource first."""
    from outreach_studio.tasks import start_kit

    return start_kit(resource, user).pk


def kit_status(kit_id: int) -> str:
    """One of: queued, running, review, published, failed."""
    from outreach_studio.models import OutreachKit

    return OutreachKit.objects.values_list("status", flat=True).get(pk=kit_id)


def published_kits(limit: int = 6):
    """Newest published kits, for the media portal homepage. Each has title, published_at,
    get_absolute_url() and kit.item("summary").content["points"]."""
    from outreach_studio.models import OutreachKit

    return list(
        OutreachKit.objects.filter(status=OutreachKit.Status.PUBLISHED)
        .prefetch_related("items")
        .order_by("-published_at")[:limit]
    )


# --- Module 4 -----------------------------------------------------------------
def suggest_next_resources(user, limit: int = 6) -> list[tuple[int, int]]:
    """Lessons related to what this user has been asking about, best first.
    Returns (content_type_id, object_id) pairs, so it works for any indexed model."""
    from ask.models import ChatQuery

    from .retrieval import search

    if not getattr(user, "is_authenticated", False):
        return []
    questions = list(ChatQuery.objects.filter(user=user).values_list("question", flat=True)[:10])
    if not questions:
        return []
    seen: list[tuple[int, int]] = []
    for hit in search(" ".join(questions), k=20):
        key = (hit.chunk.content_type_id, hit.chunk.object_id)
        if key not in seen:
            seen.append(key)
    return seen[:limit]


def suggest_next_kits(user, limit: int = 4, exclude=()):
    """Published kits made from the lessons suggest_next_resources picks; newest kits fill any gap."""
    from outreach_studio.models import OutreachKit

    published = OutreachKit.objects.filter(status=OutreachKit.Status.PUBLISHED).exclude(pk__in=list(exclude))
    picks = []
    for ct_id, obj_id in suggest_next_resources(user, limit=12):
        kit = published.filter(content_type_id=ct_id, object_id=obj_id).order_by("-published_at").first()
        if kit and kit not in picks:
            picks.append(kit)
    if len(picks) < limit:  # fill with the newest lessons, even ones already opened
        newest = OutreachKit.objects.filter(status=OutreachKit.Status.PUBLISHED).order_by("-published_at")[: limit * 2]
        picks += [k for k in newest if k not in picks]
    return picks[:limit]
