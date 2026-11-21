from django.contrib import admin

from .models import Bookmark, Resource, Subject, Tag
from .signals import reindex


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "grade", "kind", "status", "indexed_chunks", "views", "uploaded_by", "created_at")
    list_filter = ("status", "subject", "grade", "kind")
    search_fields = ("title", "description", "tags__name")
    filter_horizontal = ("tags",)
    readonly_fields = ("indexed_chunks", "index_note", "views", "created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = ["publish", "unpublish", "reindex_selected"]

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected lessons")
    def publish(self, request, queryset):
        for r in queryset:
            r.status = Resource.Status.PUBLISHED
            r.save()  # save() so the search index updates
        self.message_user(request, f"Published {queryset.count()} lesson(s).")

    @admin.action(description="Move selected lessons back to draft")
    def unpublish(self, request, queryset):
        for r in queryset:
            r.status = Resource.Status.DRAFT
            r.save()
        self.message_user(request, f"{queryset.count()} lesson(s) are drafts now.")

    @admin.action(description="Re-read files for the Ask page")
    def reindex_selected(self, request, queryset):
        for r in queryset:
            reindex(r)
        self.message_user(request, f"Re-indexed {queryset.count()} lesson(s).")


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "resource", "created_at")
