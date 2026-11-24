from django.contrib import admin
from django.db.models import Avg, Count

from .models import Quiz, QuizAttempt, Topic, Unit


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1
    fields = ("order", "title", "objectives")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("__str__", "subject", "grade", "number", "topic_count")
    list_filter = ("subject", "grade")
    search_fields = ("title",)
    inlines = [TopicInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("topics"))

    @admin.display(description="Topics", ordering="n")
    def topic_count(self, obj):
        return obj.n


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "unit", "order")
    list_filter = ("unit__subject", "unit__grade")
    search_fields = ("title", "objectives")
    filter_horizontal = ("resources",)
    exclude = ("slug",)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "size", "generated_by_ai", "is_published", "tries", "average")
    list_filter = ("is_published", "generated_by_ai", "topic__unit__subject")
    search_fields = ("title",)
    readonly_fields = ("kit", "created_by", "created_at")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("attempts"), avg=Avg("attempts__score"))

    @admin.display(description="Attempts", ordering="n")
    def tries(self, obj):
        return obj.n

    @admin.display(description="Average score")
    def average(self, obj):
        return f"{obj.avg:.1f} / {obj.size}" if obj.avg is not None else "—"


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "quiz", "score", "total", "percent", "created_at")
    list_filter = ("quiz", "created_at")
    search_fields = ("user__username", "quiz__title")
    readonly_fields = ("quiz", "user", "answers", "score", "total", "created_at")
