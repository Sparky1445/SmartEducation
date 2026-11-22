"""A profile for every user: role, class, language. Created automatically with the user."""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent or guardian"
        TEACHER = "teacher", "Teacher"
        VISITOR = "visitor", "Visitor"

    class Language(models.TextChoices):
        EN = "en", "English"
        HI = "hi", "हिन्दी · Hindi"
        MR = "mr", "मराठी · Marathi"
        KOK = "kok", "कोंकणी · Konkani"

    GRADES = [(g, f"Class {g}") for g in range(5, 13)]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VISITOR)
    grade = models.PositiveSmallIntegerField(choices=GRADES, null=True, blank=True, help_text="For students.")
    school = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=3, choices=Language.choices, default=Language.EN)
    bio = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def display_name(self) -> str:
        return self.user.get_full_name() or self.user.username


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        Profile.objects.get_or_create(user=instance)
