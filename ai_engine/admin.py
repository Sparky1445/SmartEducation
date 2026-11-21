from django.contrib import admin

from .models import AgentRun, DocumentChunk, WebLookup


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "pipeline", "status", "provider", "model_name", "tokens_used", "started_at", "duration")
    list_filter = ("pipeline", "status", "provider")
    search_fields = ("prompt", "error")
    readonly_fields = ("started_at", "finished_at", "trace", "output", "tokens_used")
    date_hierarchy = "started_at"

    @admin.display(description="Duration")
    def duration(self, obj):
        return f"{obj.duration_ms} ms" if obj.duration_ms is not None else "—"


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "content_type", "object_id", "chunk_index", "locator", "short_text")
    list_filter = ("content_type",)
    search_fields = ("text",)

    @admin.display(description="Text")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(WebLookup)
class WebLookupAdmin(admin.ModelAdmin):
    list_display = ("query", "fetched_at", "video_count", "site_count")
    search_fields = ("query",)
    readonly_fields = ("results",)
    actions = ["expire"]

    @admin.display(description="Videos")
    def video_count(self, obj):
        return len(obj.results.get("videos", []))

    @admin.display(description="Websites")
    def site_count(self, obj):
        return len(obj.results.get("sites", []))

    @admin.action(description="Refresh these topics on next search")
    def expire(self, request, queryset):
        n = queryset.delete()[0]
        self.message_user(request, f"{n} topic(s) will be looked up again.")
