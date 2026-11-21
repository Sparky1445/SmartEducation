"""Outreach kits: everything made from one uploaded lesson, reviewed by a teacher, then published."""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class OutreachKit(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Preparing"
        REVIEW = "review", "Ready for review"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    # The lesson the kit was made from (Suhaib's Resource, or any indexed object).
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    source = GenericForeignKey("content_type", "object_id")
    source_title = models.CharField(max_length=200)

    title = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=220, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    quality_notes = models.TextField(blank=True, help_text="Automatic check against the source, for the teacher.")
    error = models.TextField(blank=True)
    run = models.ForeignKey("ai_engine.AgentRun", null=True, blank=True, on_delete=models.SET_NULL)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="outreach_kits"
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [("publish_outreachkit", "Can publish outreach kits")]

    def __str__(self) -> str:
        return self.title or self.source_title

    def get_absolute_url(self) -> str:
        return reverse("outreach_studio:learn_kit", kwargs={"pk": self.pk, "slug": self.slug or "kit"})

    def get_studio_url(self) -> str:
        return reverse("outreach_studio:kit", kwargs={"pk": self.pk})

    @property
    def is_busy(self) -> bool:
        return self.status in {self.Status.QUEUED, self.Status.RUNNING}

    def item(self, kind: str, language: str = "en"):
        return next((i for i in self.items.all() if i.kind == kind and i.language == language), None)

    def publish(self, user=None) -> None:
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.published_by = user if getattr(user, "is_authenticated", False) else None
        if not self.slug:
            self.slug = slugify(self.title or self.source_title)[:200] or "kit"
        self.save()


class KitItem(models.Model):
    class Kind(models.TextChoices):
        SUMMARY = "summary", "Study notes"
        QUIZ = "quiz", "Quiz and flashcards"
        ARTICLE = "article", "Article"
        SOCIAL = "social", "Social posts and poster"
        TRANSLATION = "translation", "Translation"

    class Language(models.TextChoices):
        EN = "en", "English"
        HI = "hi", "हिन्दी · Hindi"
        MR = "mr", "मराठी · Marathi"
        KOK = "kok", "कोंकणी · Konkani"

    ORDER = ["summary", "article", "quiz", "social", "translation"]

    kit = models.ForeignKey(OutreachKit, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    language = models.CharField(max_length=3, choices=Language.choices, default=Language.EN)
    content = models.JSONField(default=dict)
    needs_check = models.BooleanField(default=False, help_text="Flagged by the automatic quality check.")
    approved = models.BooleanField(default=False)
    edited = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kit", "kind", "language"], name="one_item_per_kind_language")]

    def __str__(self) -> str:
        suffix = f" ({self.get_language_display()})" if self.kind == self.Kind.TRANSLATION else ""
        return f"{self.get_kind_display()}{suffix}"

    @property
    def sort_key(self) -> tuple:
        return (self.ORDER.index(self.kind), ["en", "hi", "mr", "kok"].index(self.language))
