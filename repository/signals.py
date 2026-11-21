"""Keep the Ask/Studio search index in step with the repository.

Saving a resource (re)indexes it; deleting it removes its passages. Tags are
re-read after the form saves them (m2m_changed), so they are searchable too.
"""

import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from ai_engine import services
from ai_engine.ingest import UnsupportedFile

from .models import Resource

log = logging.getLogger("ai_engine")


def reindex(resource: Resource) -> None:
    note = ""
    try:
        if resource.status != Resource.Status.PUBLISHED:
            services.remove_source(resource)
            count, note = 0, "Draft: not searchable until published."
        elif resource.file and resource.is_indexable_file:
            count = services.index_source(resource, path=resource.file.path)
            if count == 0:
                # Scanned PDFs have no text layer; fall back to the description.
                count = services.index_source(resource, text=resource.search_text())
                note = "No text found in the file (is it a scanned PDF?). Searching the description instead."
        else:
            count = services.index_source(resource, text=resource.search_text())
            if resource.file:
                note = f"{resource.extension or 'This'} files can't be read yet; the description is searchable."
    except (UnsupportedFile, FileNotFoundError, ValueError) as exc:
        count, note = 0, str(exc)[:200]
    except Exception:  # noqa: BLE001 - a broken file must never block the upload
        log.exception("indexing resource %s failed", resource.pk)
        count, note = 0, "The file could not be read. Try saving it again as PDF."
    Resource.objects.filter(pk=resource.pk).update(indexed_chunks=count, index_note=note)
    resource.indexed_chunks, resource.index_note = count, note


@receiver(post_save, sender=Resource)
def resource_saved(sender, instance: Resource, raw=False, **kwargs):
    if not raw:
        reindex(instance)


@receiver(m2m_changed, sender=Resource.tags.through)
def tags_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"} and isinstance(instance, Resource):
        if not (instance.file and instance.is_indexable_file):
            reindex(instance)


@receiver(post_delete, sender=Resource)
def resource_deleted(sender, instance: Resource, **kwargs):
    services.remove_source(instance)
    if instance.file:
        instance.file.delete(save=False)
