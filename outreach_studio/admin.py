from django.contrib import admin

from .models import KitItem, OutreachKit


class KitItemInline(admin.TabularInline):
    model = KitItem
    extra = 0
    fields = ("kind", "language", "approved", "needs_check", "edited", "content")
    readonly_fields = ("kind", "language")


@admin.register(OutreachKit)
class OutreachKitAdmin(admin.ModelAdmin):
    list_display = ("__str__", "source_title", "status", "requested_by", "created_at", "published_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "source_title")
    readonly_fields = ("content_type", "object_id", "run", "created_at", "ready_at", "published_at", "published_by")
    inlines = [KitItemInline]
    actions = ["publish_selected", "unpublish_selected"]

    @admin.action(description="Publish selected kits")
    def publish_selected(self, request, queryset):
        done = 0
        for kit in queryset.exclude(status__in=["queued", "running", "failed"]):
            kit.publish(request.user)
            done += 1
        self.message_user(request, f"Published {done} kit(s).")

    @admin.action(description="Take selected kits off the Learn page")
    def unpublish_selected(self, request, queryset):
        n = queryset.filter(status="published").update(status="review")
        self.message_user(request, f"Unpublished {n} kit(s).")
