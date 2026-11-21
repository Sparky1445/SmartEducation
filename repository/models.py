"""The knowledge repository: lessons (files, videos, links) organised by subject, class and tag."""

import re
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

INDEXABLE = {".pdf", ".pptx", ".txt", ".md"}


class Subject(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("repository:subject", kwargs={"slug": self.slug})


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.slug = self.slug or slugify(self.name)
        super().save(*args, **kwargs)


def upload_path(instance, filename: str) -> str:
    """media/resources/2026/11/water-cycle-notes.pdf"""
    now = timezone.now()
    name = slugify(Path(filename).stem)[:60] or "lesson"
    return f"resources/{now:%Y}/{now:%m}/{name}{Path(filename).suffix.lower()}"


class ResourceQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Resource.Status.PUBLISHED)

    def search(self, text: str):
        """Simple ORM search across title, description and tags (Unit V: Q objects)."""
        query = models.Q()
        for word in text.split()[:6]:
            query &= (
                models.Q(title__icontains=word)
                | models.Q(description__icontains=word)
                | models.Q(tags__name__icontains=word)
                | models.Q(subject__name__icontains=word)
            )
        return self.filter(query).distinct()


class Resource(models.Model):
    class Kind(models.TextChoices):
        DOCUMENT = "document", "Notes or worksheet"
        SLIDES = "slides", "Slides"
        VIDEO = "video", "Video"
        LINK = "link", "Web link"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    GRADES = [(g, f"Class {g}") for g in range(5, 13)]

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    description = models.TextField(blank=True, help_text="What the lesson covers. Also searchable on the Ask page.")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.DOCUMENT)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="resources")
    grade = models.PositiveSmallIntegerField(choices=GRADES, null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="resources")
    file = models.FileField(upload_to=upload_path, blank=True)
    url = models.URLField(blank=True, help_text="For videos and web links.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    views = models.PositiveIntegerField(default=0)
    indexed_chunks = models.PositiveIntegerField(default=0, editable=False)
    index_note = models.CharField(max_length=200, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ResourceQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["subject", "grade", "status"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.slug = slugify(self.title)[:170] or "lesson"
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("repository:detail", kwargs={"pk": self.pk, "slug": self.slug or "lesson"})

    @property
    def extension(self) -> str:
        return Path(self.file.name).suffix.lower() if self.file else ""

    @property
    def is_image(self) -> bool:
        return bool(self.file) and self.extension in {".jpg", ".jpeg", ".png"}

    @property
    def is_indexable_file(self) -> bool:
        return self.extension in INDEXABLE

    @property
    def youtube_id(self) -> str:
        match = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})", self.url or "")
        return match.group(1) if match else ""

    def search_text(self) -> str:
        """Text indexed for Ask when there is no readable file (videos, links)."""
        tags = ", ".join(t.name for t in self.tags.all()) if self.pk else ""
        return f"{self.title}\n\n{self.description}\n\nTopics: {tags}".strip()


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "resource"], name="one_bookmark_per_user")]

    def __str__(self) -> str:
        return f"{self.user} → {self.resource}"
