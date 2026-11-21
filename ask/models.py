from django.conf import settings
from django.db import models


class ChatQuery(models.Model):
    """One question asked on the Ask page and the answer it got."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    question = models.CharField(max_length=500)
    answer = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    trust_score = models.PositiveSmallIntegerField(default=0)
    in_repository = models.BooleanField(default=False, db_index=True)
    web_links = models.JSONField(default=dict, blank=True, help_text="Related videos and websites shown under the answer.")
    helpful = models.BooleanField(null=True, blank=True, help_text="Student feedback: was this answer useful?")
    run = models.ForeignKey("ai_engine.AgentRun", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "question"

    def __str__(self) -> str:
        return self.question[:60]

    @property
    def source_count(self) -> int:
        return len(self.citations)
