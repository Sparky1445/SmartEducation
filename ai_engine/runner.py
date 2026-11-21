"""Glue between Django (synchronous) and Semantic Kernel (async), plus run tracking."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from contextlib import contextmanager
from typing import Any, Awaitable, Iterator, TypeVar

from django.utils import timezone

from .llm import resolve_provider
from .models import AgentRun

log = logging.getLogger("ai_engine")
T = TypeVar("T")


def run_sync(coro: Awaitable[T]) -> T:
    """Run a coroutine from sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class RunRecorder:
    """Collects the steps of one run; saved into AgentRun.trace."""

    def __init__(self, run: AgentRun) -> None:
        self.run = run

    def step(self, agent: str, kind: str, text: str) -> None:
        self.run.trace.append({"agent": agent, "kind": kind, "text": text, "at": timezone.now().isoformat()})

    def add_tokens(self, usage: Any) -> None:
        if not usage:
            return
        get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
        self.run.tokens_used += int(get("prompt_tokens", 0) or 0) + int(get("completion_tokens", 0) or 0)


@contextmanager
def tracked_run(pipeline: str, prompt: str, user=None) -> Iterator[RunRecorder]:
    """Create an AgentRun, yield a recorder, and close the run as success or failure.

    Exceptions are recorded on the run and re-raised so the caller decides how
    to show them (Unit II: error handling).
    """
    info = resolve_provider()
    run = AgentRun.objects.create(
        pipeline=pipeline,
        provider=info.active,
        model_name=info.model,
        prompt=prompt,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    recorder = RunRecorder(run)
    log.info("run %s started: %s via %s", run.pk, pipeline, info.active)
    try:
        yield recorder
    except Exception as exc:  # noqa: BLE001 - we log every failure, then re-raise
        run.status = AgentRun.Status.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        log.exception("run %s failed", run.pk)
        raise
    else:
        run.status = AgentRun.Status.SUCCESS
        log.info("run %s succeeded, %s tokens", run.pk, run.tokens_used)
    finally:
        run.finished_at = timezone.now()
        run.save()
