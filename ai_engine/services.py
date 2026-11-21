"""The only door from the portal into the AI engine.

Suhaib's views import from here and nowhere else in ai_engine. Signatures
are frozen (gate 1 of the plan); what happens inside grows module by module.

    ping(message, user=None)            -> AgentRun          (Module 1, live)
    index_source(obj, path=None, text=None) -> int (chunks)  (Module 2, live)
    remove_source(obj)                  -> None              (Module 2, live)
    ask(question, user=None)            -> dict              (Module 2, live)
    build_outreach_kit(resource, user=None) -> int (kit id)  (Module 3, live)
    kit_status(kit_id)                  -> str               (Module 3, live)
    published_kits(limit=6)             -> list[OutreachKit] (Module 3, live)
    suggest_next_resources(user)        -> list[int]         (Module 4)

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
    "content_type", "object_id", "resource_id"}], "trust_score": 0-100, "in_repository": bool, "run_id": int}
    When the repository has no good answer, in_repository is False and answer is a polite fallback."""
    return ask_pipeline.ask(question, user).as_dict()


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


def suggest_next_resources(user) -> list[int]:
    """Resource ids to show under 'Up next' on the student dashboard."""
    return []
