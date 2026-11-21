"""Outreach Studio (teachers) and Learn (public pages for published kits)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView

from ai_engine.models import DocumentChunk

from .forms import form_for
from .models import KitItem, OutreachKit
from .tasks import start_kit

STUDIO_PERM = "outreach_studio.add_outreachkit"
PUBLISH_PERM = "outreach_studio.publish_outreachkit"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def indexed_lessons():
    """Every object that has searchable text: [{content_type, object_id, title, chunks, obj}]."""
    rows = (
        DocumentChunk.objects.values("content_type", "object_id")
        .annotate(chunks=Count("id"))
        .order_by("content_type", "object_id")
    )
    lessons = []
    for row in rows:
        ct = ContentType.objects.get_for_id(row["content_type"])
        obj = ct.get_object_for_this_type(pk=row["object_id"]) if ct.model_class() else None
        if obj is None:
            continue
        lessons.append({**row, "title": str(getattr(obj, "title", None) or obj), "ct_label": ct.model})
    return lessons


def sorted_items(kit):
    return sorted(kit.items.all(), key=lambda i: i.sort_key)


# ---------------------------------------------------------------------------
# Studio (teachers)
# ---------------------------------------------------------------------------
@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
def studio_home(request):
    kits = OutreachKit.objects.annotate(
        n_items=Count("items"), n_approved=Count("items", filter=Q(items__approved=True))
    )
    status = request.GET.get("status", "")
    if status in OutreachKit.Status.values:
        kits = kits.filter(status=status)
    lessons = indexed_lessons()
    made = set(OutreachKit.objects.values_list("content_type_id", "object_id"))
    for lesson in lessons:
        lesson["has_kit"] = (lesson["content_type"], lesson["object_id"]) in made
    counts = dict(OutreachKit.objects.values_list("status").annotate(n=Count("id")))
    return render(
        request,
        "outreach_studio/studio_home.html",
        {"kits": kits[:50], "lessons": lessons, "status": status, "counts": counts, "statuses": OutreachKit.Status.choices},
    )


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
@require_POST
def kit_create(request, ct_id: int, object_id: int):
    ct = get_object_or_404(ContentType, pk=ct_id)
    try:
        obj = ct.get_object_for_this_type(pk=object_id)
    except ct.model_class().DoesNotExist as exc:
        raise Http404("No such lesson") from exc
    if not DocumentChunk.objects.filter(content_type=ct, object_id=object_id).exists():
        messages.error(request, "This lesson has no readable text yet, so a kit cannot be made from it.")
        return redirect("outreach_studio:studio")
    kit = start_kit(obj, request.user)
    messages.success(request, f"Preparing a kit for “{kit.source_title}”. It usually takes under a minute.")
    return redirect("outreach_studio:kit", pk=kit.pk)


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
def kit_detail(request, pk: int):
    kit = get_object_or_404(OutreachKit.objects.prefetch_related("items"), pk=pk)
    items = sorted_items(kit)
    cards = [{"item": item, "form": form_for(item)} for item in items]
    approved = sum(i.approved for i in items)
    return render(
        request,
        "outreach_studio/kit_detail.html",
        {
            "kit": kit,
            "cards": cards,
            "approved": approved,
            "total": len(items),
            "can_publish": request.user.has_perm(PUBLISH_PERM),
        },
    )


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
@require_GET
def kit_status_json(request, pk: int):
    kit = get_object_or_404(OutreachKit, pk=pk)
    return JsonResponse({"status": kit.status, "label": kit.get_status_display(), "busy": kit.is_busy})


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
@require_POST
def item_edit(request, pk: int):
    item = get_object_or_404(KitItem.objects.select_related("kit"), pk=pk)
    form = form_for(item, data=request.POST)
    if form is None:
        messages.error(request, "Quizzes are approved as a whole; edit questions in the admin if needed.")
    elif form.is_valid():
        item.content = form.to_content(item.content)
        item.edited = True
        item.needs_check = False
        item.save()
        messages.success(request, f"{item} saved.")
    else:
        errors = "; ".join(f"{form.fields[f].label or f}: {', '.join(e)}" for f, e in form.errors.items())
        messages.error(request, f"{item} was not saved. {errors}")
    return redirect(f"{item.kit.get_studio_url()}#item-{item.pk}")


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
@require_POST
def item_approve(request, pk: int):
    item = get_object_or_404(KitItem.objects.select_related("kit"), pk=pk)
    item.approved = request.POST.get("approved") == "1"
    item.save(update_fields=["approved", "updated_at"])
    return redirect(f"{item.kit.get_studio_url()}#item-{item.pk}")


@login_required
@permission_required(PUBLISH_PERM, raise_exception=True)
@require_POST
def kit_publish(request, pk: int):
    kit = get_object_or_404(OutreachKit, pk=pk)
    if kit.is_busy or kit.status == OutreachKit.Status.FAILED:
        messages.error(request, "Only a finished kit can be published.")
    elif not kit.items.filter(kind=KitItem.Kind.SUMMARY, approved=True).exists():
        messages.error(request, "Approve at least the study notes before publishing.")
    else:
        kit.publish(request.user)
        messages.success(request, "Published. Approved parts are now live on the Learn page.")
    return redirect("outreach_studio:kit", pk=kit.pk)


@login_required
@permission_required(PUBLISH_PERM, raise_exception=True)
@require_POST
def kit_unpublish(request, pk: int):
    kit = get_object_or_404(OutreachKit, pk=pk, status=OutreachKit.Status.PUBLISHED)
    kit.status = OutreachKit.Status.REVIEW
    kit.save(update_fields=["status"])
    messages.info(request, "Taken off the Learn page. You can publish it again any time.")
    return redirect("outreach_studio:kit", pk=kit.pk)


@login_required
@permission_required(STUDIO_PERM, raise_exception=True)
@require_POST
def kit_regenerate(request, pk: int):
    old = get_object_or_404(OutreachKit, pk=pk)
    if old.is_busy:
        messages.info(request, "This kit is still being prepared.")
        return redirect("outreach_studio:kit", pk=old.pk)
    if old.source is None:
        messages.error(request, "The original lesson no longer exists.")
        return redirect("outreach_studio:kit", pk=old.pk)
    kit = start_kit(old.source, request.user)
    messages.success(request, "Making a fresh kit from the same lesson. The old one is kept until you delete it.")
    return redirect("outreach_studio:kit", pk=kit.pk)


# ---------------------------------------------------------------------------
# Learn (public)
# ---------------------------------------------------------------------------
class LearnListView(ListView):
    template_name = "outreach_studio/learn_list.html"
    context_object_name = "kits"
    paginate_by = 12

    def get_queryset(self):
        return (
            OutreachKit.objects.filter(status=OutreachKit.Status.PUBLISHED)
            .prefetch_related("items")
            .order_by("-published_at")
        )


def learn_kit(request, pk: int, slug: str):
    kit = get_object_or_404(OutreachKit.objects.prefetch_related("items"), pk=pk, status=OutreachKit.Status.PUBLISHED)
    if slug != kit.slug:
        return redirect(kit, permanent=True)
    items = [i for i in sorted_items(kit) if i.approved]
    by_kind = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)
    return render(request, "outreach_studio/learn_kit.html", {"kit": kit, "by_kind": by_kind})
