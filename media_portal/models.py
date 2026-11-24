"""The school's public media: news articles, events and site-wide announcements."""

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class ArticleQuerySet(models.QuerySet):
    def live(self):
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=timezone.now())


class Article(models.Model):
    class Category(models.TextChoices):
        NEWS = "news", "School news"
        LEARNING = "learning", "From the classroom"
        ACHIEVEMENT = "achievement", "Achievements"
        NOTICE = "notice", "Notices"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=170, unique_for_date="published_at")
    standfirst = models.CharField(max_length=260, blank=True, help_text="One sentence under the headline.")
    body = models.TextField(help_text="Leave a blank line between paragraphs.")
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.NEWS, db_index=True)
    cover = models.FileField(
        upload_to="news/%Y/%m/", blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Optional photo, JPG/PNG/WebP.",
    )
    cover_caption = models.CharField(max_length=160, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="articles")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    featured = models.BooleanField(default=False, help_text="Show as the lead story on the home page.")
    published_at = models.DateTimeField(default=timezone.now, help_text="A future time schedules the article.")
    source_kit = models.ForeignKey(
        "outreach_studio.OutreachKit", null=True, blank=True, on_delete=models.SET_NULL, related_name="news_articles",
        help_text="Set when the article was made from an outreach kit.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at"]
        indexes = [models.Index(fields=["status", "published_at"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:160] or "article"
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        local = timezone.localtime(self.published_at)
        return reverse("media_portal:article", kwargs={"year": local.year, "slug": self.slug})

    @property
    def paragraphs(self) -> list[str]:
        return [p.strip() for p in self.body.replace("\r\n", "\n").split("\n\n") if p.strip()]

    @property
    def reading_minutes(self) -> int:
        return max(1, round(len(self.body.split()) / 200))


class Event(models.Model):
    class Kind(models.TextChoices):
        EXAM = "exam", "Exam"
        CULTURAL = "cultural", "Cultural"
        SPORTS = "sports", "Sports"
        MEETING = "meeting", "Parents' meeting"
        HOLIDAY = "holiday", "Holiday"
        OTHER = "other", "Other"

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=170, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OTHER)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=160, blank=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.slug = slugify(self.title)[:160] or "event"
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("media_portal:event", kwargs={"pk": self.pk, "slug": self.slug})

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({"ends_at": "The event cannot end before it starts."})

    @property
    def is_past(self) -> bool:
        return (self.ends_at or self.starts_at) < timezone.now()


class AnnouncementQuerySet(models.QuerySet):
    def current(self):
        now = timezone.now()
        return self.filter(is_active=True, starts_at__lte=now).filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))


class Announcement(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Information"
        IMPORTANT = "important", "Important"

    text = models.CharField(max_length=200)
    link = models.CharField(max_length=300, blank=True, help_text="Optional page to open, e.g. /events/ or a full URL.")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        ordering = ["-level", "-starts_at"]

    def __str__(self) -> str:
        return self.text[:60]
