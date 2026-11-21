"""Runs kit generation in the background so the teacher's page never waits on the model.

A plain daemon thread is enough for this project (one teacher, a few kits).
In tests, settings.OUTREACH_RUN_INLINE = True runs it synchronously.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections, transaction
from django.utils import timezone

from ai_engine import outreach_pipeline

from .models import KitItem, OutreachKit

log = logging.getLogger("ai_engine")


def source_title(obj) -> str:
    return str(getattr(obj, "title", None) or obj)[:200]


def start_kit(source_obj, user=None) -> OutreachKit:
    kit = OutreachKit.objects.create(
        content_type=ContentType.objects.get_for_model(source_obj),
        object_id=source_obj.pk,
        source_title=source_title(source_obj),
        requested_by=user if getattr(user, "is_authenticated", False) else None,
    )
    if getattr(settings, "OUTREACH_RUN_INLINE", False):
        run_kit(kit.pk)
    else:
        # Start only after the kit row is committed, so the thread can see it.
        transaction.on_commit(
            lambda: threading.Thread(target=_thread_main, args=(kit.pk,), daemon=True, name=f"kit-{kit.pk}").start()
        )
    return kit


def _thread_main(kit_id: int) -> None:
    close_old_connections()
    try:
        run_kit(kit_id)
    finally:
        close_old_connections()


def run_kit(kit_id: int) -> None:
    kit = OutreachKit.objects.get(pk=kit_id)
    kit.status = OutreachKit.Status.RUNNING
    kit.save(update_fields=["status"])
    try:
        draft = outreach_pipeline.build_kit(kit.source, kit.source_title, user=kit.requested_by)
    except outreach_pipeline.NoSourceText as exc:
        _fail(kit, str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - logged in full; teachers see a short message
        log.exception("kit %s failed", kit_id)
        _fail(kit, "The kit could not be prepared this time. Please try again in a few minutes.")
        return

    with transaction.atomic():
        kit.items.all().delete()
        for kind, content in draft.drafts.items():
            flag = draft.verdicts.get(kind) != "ok"
            if kind == "translation":
                for lang in ("hi", "mr", "kok"):
                    KitItem.objects.create(kit=kit, kind=kind, language=lang, content={"text": content.get(lang, "")}, needs_check=flag)
            else:
                KitItem.objects.create(kit=kit, kind=kind, content=content, needs_check=flag)
        summary = draft.drafts.get("summary", {})
        article = draft.drafts.get("article", {})
        kit.title = summary.get("title") or article.get("headline") or kit.source_title
        kit.quality_notes = draft.notes
        kit.run_id = draft.run_id
        kit.status = OutreachKit.Status.REVIEW
        kit.ready_at = timezone.now()
        kit.error = ""
        kit.save()


def _fail(kit: OutreachKit, message: str) -> None:
    kit.status = OutreachKit.Status.FAILED
    kit.error = message
    kit.save(update_fields=["status", "error"])
