"""The syllabus (units and topics per subject and class), scored quizzes and students' attempts."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from repository.models import Resource, Subject

GRADES = [(g, f"Class {g}") for g in range(5, 13)]
PASS_MARK = 60  # percent; a topic counts as done when its quiz is passed


class Unit(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="units")
    grade = models.PositiveSmallIntegerField(choices=GRADES)
    number = models.PositiveSmallIntegerField(help_text="Unit or chapter number in the textbook.")
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["subject__name", "grade", "number"]
        constraints = [models.UniqueConstraint(fields=["subject", "grade", "number"], name="one_unit_number_per_class")]

    def __str__(self) -> str:
        return f"{self.subject} {self.grade} · Unit {self.number}: {self.title}"

    def get_absolute_url(self) -> str:
        return reverse("courses:syllabus", kwargs={"grade": self.grade, "subject": self.subject.slug}) + f"#unit-{self.number}"


class Topic(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="topics")
    order = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, blank=True)
    objectives = models.TextField(blank=True, help_text="What students should be able to do. One per line.")
    resources = models.ManyToManyField(Resource, blank=True, related_name="topics", help_text="Lessons that teach this topic.")

    class Meta:
        ordering = ["unit", "order"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.slug = slugify(self.title)[:120] or "topic"
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("courses:topic", kwargs={"pk": self.pk, "slug": self.slug})

    @property
    def objective_list(self) -> list[str]:
        return [line.strip("-• ").strip() for line in self.objectives.splitlines() if line.strip()]


def validate_questions(value):
    """questions = [{"q": str, "options": [str, ...], "answer": int, "why": str}, ...]"""
    if not isinstance(value, list) or not value:
        raise ValidationError("A quiz needs at least one question.")
    for i, q in enumerate(value, start=1):
        if not isinstance(q, dict) or not str(q.get("q", "")).strip():
            raise ValidationError(f"Question {i} has no text.")
        options = q.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise ValidationError(f"Question {i} needs at least two options.")
        if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(options):
            raise ValidationError(f"Question {i}: 'answer' must be the index of the right option (0 = first).")


class Quiz(models.Model):
    title = models.CharField(max_length=160)
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL, related_name="quizzes")
    kit = models.ForeignKey("outreach_studio.OutreachKit", null=True, blank=True, on_delete=models.SET_NULL, related_name="quizzes")
    questions = models.JSONField(validators=[validate_questions])
    generated_by_ai = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "quizzes"

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("courses:quiz", kwargs={"pk": self.pk})

    @property
    def size(self) -> int:
        return len(self.questions)


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    answers = models.JSONField(default=list, help_text="Chosen option index per question.")
    score = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "quiz"])]

    def __str__(self) -> str:
        return f"{self.user} · {self.quiz} · {self.score}/{self.total}"

    @property
    def percent(self) -> int:
        return round(100 * self.score / self.total) if self.total else 0

    @property
    def passed(self) -> bool:
        return self.percent >= PASS_MARK
