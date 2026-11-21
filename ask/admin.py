from django.contrib import admin

from .models import ChatQuery


@admin.register(ChatQuery)
class ChatQueryAdmin(admin.ModelAdmin):
    list_display = ("question", "in_repository", "trust_score", "source_count", "helpful", "user", "created_at")
    list_filter = ("in_repository", "helpful", "created_at")
    search_fields = ("question", "answer")
    readonly_fields = ("citations", "run", "session_key", "created_at")
    date_hierarchy = "created_at"
    actions = ["clear_feedback"]

    @admin.display(description="Sources")
    def source_count(self, obj):
        return obj.source_count

    @admin.action(description="Clear student feedback on selected questions")
    def clear_feedback(self, request, queryset):
        updated = queryset.update(helpful=None)
        self.message_user(request, f"Cleared feedback on {updated} question(s).")
