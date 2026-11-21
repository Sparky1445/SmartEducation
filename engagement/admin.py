import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from .models import Comment, Feedback, NewsletterSubscriber, Rating


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("short_body", "user", "content_type", "object_id", "is_visible", "is_reply", "created_at")
    list_filter = ("is_visible", "content_type", "created_at")
    search_fields = ("body", "user__username")
    list_editable = ("is_visible",)
    actions = ["hide", "show"]

    @admin.display(description="Comment")
    def short_body(self, obj):
        return obj.body[:70]

    @admin.display(boolean=True, description="Reply")
    def is_reply(self, obj):
        return obj.parent_id is not None

    @admin.action(description="Hide selected comments from the site")
    def hide(self, request, queryset):
        self.message_user(request, f"Hid {queryset.update(is_visible=False)} comment(s).")

    @admin.action(description="Show selected comments on the site")
    def show(self, request, queryset):
        self.message_user(request, f"Showing {queryset.update(is_visible=True)} comment(s).")


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "user", "stars", "updated_at")
    list_filter = ("stars", "content_type")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "short_message", "resolved", "created_at")
    list_filter = ("resolved", "category", "created_at")
    search_fields = ("name", "email", "message")
    list_editable = ("resolved",)
    actions = ["mark_resolved"]

    @admin.display(description="Message")
    def short_message(self, obj):
        return obj.message[:80]

    @admin.action(description="Mark selected as resolved")
    def mark_resolved(self, request, queryset):
        self.message_user(request, f"Resolved {queryset.update(resolved=True)} message(s).")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "language", "is_active", "created_at")
    list_filter = ("is_active", "language")
    search_fields = ("email", "name")
    actions = ["export_csv"]

    @admin.action(description="Download selected as CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        stamp = timezone.now().strftime("%Y%m%d")
        response["Content-Disposition"] = f'attachment; filename="subscribers-{stamp}.csv"'
        writer = csv.writer(response)
        writer.writerow(["email", "name", "language", "active", "joined"])
        for s in queryset:
            writer.writerow([s.email, s.name, s.language, s.is_active, s.created_at.date().isoformat()])
        return response
