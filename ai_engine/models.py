"""Data the AI engine keeps: one row per agent run, and the text chunks RAG searches."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AgentRun(models.Model):
    """One call into the engine: which pipeline ran, on what, how it went."""

    class Pipeline(models.TextChoices):
        PING = "ping", "Kernel ping"
        ASK = "ask", "Ask the Repository"
        OUTREACH = "outreach", "Outreach Studio"
        INGEST = "ingest", "Ingestion"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    pipeline = models.CharField(max_length=20, choices=Pipeline.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    provider = models.CharField(max_length=20)
    model_name = models.CharField(max_length=80, blank=True)
    prompt = models.TextField(help_text="What the run was asked to do.")
    output = models.JSONField(default=dict, blank=True)
    trace = models.JSONField(default=list, blank=True, help_text="Ordered steps: agent, kind, text.")
    tokens_used = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["pipeline", "status"])]

    def __str__(self) -> str:
        return f"#{self.pk} {self.get_pipeline_display()} · {self.status}"

    @property
    def duration_ms(self) -> int | None:
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class DocumentChunk(models.Model):
    """A slice of any uploaded source, ready for retrieval.

    The source is a generic relation, so the engine does not depend on
    Suhaib's Resource model: a chunk can point at a Resource, an Article,
    or anything else with text.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    source = GenericForeignKey("content_type", "object_id")

    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    locator = models.CharField(
        max_length=40, blank=True, help_text="Where in the source: 'p. 4' or '12:30'."
    )
    vector_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["content_type", "object_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "chunk_index"], name="unique_chunk_per_source"
            )
        ]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.content_type.model}:{self.object_id} [{self.chunk_index}]"
