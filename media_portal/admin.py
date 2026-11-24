from django.contrib import admin
from django.utils import timezone

from .models import Announcement, Article, Event


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "featured", "published_at", "author")
    list_filter = ("status", "category", "featured", "published_at")
    search_fields = ("title", "standfirst", "body")
    list_editable = ("featured",)
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    readonly_fields = ("source_kit", "updated_at")
    actions = ["publish_now"]
    fieldsets = (
        (None, {"fields": ("title", "slug", "standfirst", "body", "category")}),
        ("Photo", {"fields": ("cover", "cover_caption"), "classes": ("collapse",)}),
        ("Publishing", {"fields": ("status", "published_at", "featured", "author", "source_kit", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected now")
    def publish_now(self, request, queryset):
        n = queryset.update(status=Article.Status.PUBLISHED, published_at=timezone.now())
        self.message_user(request, f"Published {n} article(s).")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "starts_at", "venue", "is_public")
    list_filter = ("kind", "is_public", "starts_at")
    search_fields = ("title", "venue", "description")
    date_hierarchy = "starts_at"
    exclude = ("slug",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("text", "level", "is_active", "starts_at", "ends_at")
    list_filter = ("level", "is_active")
    list_editable = ("is_active",)
