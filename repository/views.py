"""Repository: browse, search, read, bookmark; teachers upload, edit and delete."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from outreach_studio.models import OutreachKit

from .forms import ResourceForm, SearchForm
from .models import Bookmark, Resource, Subject

SORTS = {"new": "-created_at", "popular": "-views", "title": "title"}


class ResourceListView(ListView):
    template_name = "repository/list.html"
    context_object_name = "resources"
    paginate_by = 12

    def get_queryset(self):
        qs = Resource.objects.published().select_related("subject").prefetch_related("tags")
        self.form = SearchForm(self.request.GET or None)
        self.subject = None
        if "slug" in self.kwargs:
            self.subject = get_object_or_404(Subject, slug=self.kwargs["slug"])
            qs = qs.filter(subject=self.subject)
        if "year" in self.kwargs:
            qs = qs.filter(created_at__year=self.kwargs["year"])
        if tag := self.request.GET.get("tag"):
            qs = qs.filter(tags__slug=tag)
        sort = "new"
        if self.form.is_valid():
            d = self.form.cleaned_data
            if d["q"]:
                qs = qs.search(d["q"])
            if d["subject"]:
                qs = qs.filter(subject=d["subject"])
            if d["grade"]:
                qs = qs.filter(grade=d["grade"])
            if d["kind"]:
                qs = qs.filter(kind=d["kind"])
            sort = d["sort"] or "new"
        return qs.order_by(SORTS.get(sort, "-created_at"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(
            {
                "form": self.form,
                "subject": self.subject,
                "year": self.kwargs.get("year"),
                "subjects": Subject.objects.annotate(n=Count("resources")).filter(n__gt=0),
                "querystring": params.urlencode(),
                "filtered": any(v for k, v in self.request.GET.items() if k not in {"page", "sort"}),
            }
        )
        return ctx


def resource_detail(request, pk: int, slug: str):
    resource = get_object_or_404(Resource.objects.select_related("subject", "uploaded_by").prefetch_related("tags"), pk=pk)
    can_edit = request.user.has_perm("repository.change_resource")
    if resource.status != Resource.Status.PUBLISHED and not can_edit:
        raise Http404("No such lesson")
    if slug != resource.slug:
        return redirect(resource, permanent=True)

    # Count a view once per session, without a race (F expression).
    seen = request.session.get("seen_resources", [])
    if resource.pk not in seen:
        Resource.objects.filter(pk=resource.pk).update(views=F("views") + 1)
        resource.views += 1  # show the new count on this page too
        request.session["seen_resources"] = (seen + [resource.pk])[-50:]

    ct = ContentType.objects.get_for_model(Resource)
    kit = OutreachKit.objects.filter(content_type=ct, object_id=resource.pk, status=OutreachKit.Status.PUBLISHED).order_by("-published_at").first()
    related = (
        Resource.objects.published()
        .filter(subject=resource.subject)
        .exclude(pk=resource.pk)
        .annotate(shared=Count("tags", filter=Q(tags__in=resource.tags.all())))
        .order_by("-shared", "-created_at")[:4]
    )
    return render(
        request,
        "repository/detail.html",
        {
            "r": resource,
            "kit": kit,
            "related": related,
            "can_edit": can_edit,
            "ct_id": ct.pk,
            "bookmarked": request.user.is_authenticated and Bookmark.objects.filter(user=request.user, resource=resource).exists(),
        },
    )


class TeacherRequired(LoginRequiredMixin, PermissionRequiredMixin):
    raise_exception = True


class ResourceCreateView(TeacherRequired, CreateView):
    model = Resource
    form_class = ResourceForm
    template_name = "repository/form.html"
    permission_required = "repository.add_resource"

    def get_initial(self):
        return {"subject": Subject.objects.filter(slug=self.request.GET.get("subject")).first(), "title": self.request.GET.get("title", "")}

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        _report_index(self.request, self.object, "Uploaded")
        return response


class ResourceUpdateView(TeacherRequired, UpdateView):
    model = Resource
    form_class = ResourceForm
    template_name = "repository/form.html"
    permission_required = "repository.change_resource"

    def form_valid(self, form):
        response = super().form_valid(form)
        _report_index(self.request, self.object, "Saved")
        return response


class ResourceDeleteView(TeacherRequired, DeleteView):
    model = Resource
    template_name = "repository/confirm_delete.html"
    permission_required = "repository.delete_resource"
    success_url = reverse_lazy("repository:list")

    def form_valid(self, form):
        messages.info(self.request, f"“{self.object}” was deleted.")
        return super().form_valid(form)


def _report_index(request, resource, verb):
    resource.refresh_from_db(fields=["indexed_chunks", "index_note", "status"])
    if resource.status != Resource.Status.PUBLISHED:
        messages.success(request, f"{verb} as a draft. Publish it to make it visible and searchable.")
    elif resource.index_note:
        messages.warning(request, f"{verb}. {resource.index_note}")
    else:
        messages.success(request, f"{verb}. Students can now ask about it ({resource.indexed_chunks} passages).")


@login_required
@require_POST
def bookmark_toggle(request, pk: int):
    resource = get_object_or_404(Resource, pk=pk)
    mark, created = Bookmark.objects.get_or_create(user=request.user, resource=resource)
    if not created:
        mark.delete()
    messages.success(request, "Saved to your bookmarks." if created else "Removed from your bookmarks.")
    return redirect(resource)


class BookmarkListView(LoginRequiredMixin, ListView):
    template_name = "repository/bookmarks.html"
    context_object_name = "bookmarks"

    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user, resource__status=Resource.Status.PUBLISHED).select_related("resource__subject")
