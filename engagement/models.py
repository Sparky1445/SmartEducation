"""Community features: comments, star ratings, feedback messages and the newsletter."""

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count


class TargetQuerySet(models.QuerySet):
    """Filter by the object a comment or rating belongs to."""

    def for_object(self, obj):
        return self.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk)


class Comment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    body = models.TextField(max_length=1000)
    is_visible = models.BooleanField(default=True, help_text="Untick to hide a comment from the site.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TargetQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["content_type", "object_id", "is_visible"])]

    def __str__(self) -> str:
        return f"{self.user} on {self.content_type.model} #{self.object_id}"


class Rating(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ratings")
    stars = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    updated_at = models.DateTimeField(auto_now=True)

    objects = TargetQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "content_type", "object_id"], name="one_rating_per_user"),
            models.CheckConstraint(condition=models.Q(stars__gte=1, stars__lte=5), name="stars_1_to_5"),
        ]

    def __str__(self) -> str:
        return f"{self.stars}★ by {self.user}"

    @classmethod
    def summary(cls, obj) -> dict:
        data = cls.objects.for_object(obj).aggregate(average=Avg("stars"), count=Count("id"))
        data["average"] = round(data["average"] or 0, 1)
        return data


class Feedback(models.Model):
    class Category(models.TextChoices):
        SUGGESTION = "suggestion", "A suggestion"
        CONTENT = "content", "Request a lesson or topic"
        PROBLEM = "problem", "Something is not working"
        OTHER = "other", "Something else"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=80)
    email = models.EmailField()
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.SUGGESTION)
    message = models.TextField(max_length=2000)
    page_url = models.CharField(max_length=300, blank=True)
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "feedback"

    def __str__(self) -> str:
        return f"{self.get_category_display()} from {self.name}"


class NewsletterSubscriber(models.Model):
    class Language(models.TextChoices):
        EN = "en", "English"
        HI = "hi", "हिन्दी · Hindi"
        MR = "mr", "मराठी · Marathi"
        KOK = "kok", "कोंकणी · Konkani"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=3, choices=Language.choices, default=Language.EN)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email
