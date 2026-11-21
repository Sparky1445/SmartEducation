"""Numbers for the dashboards, all computed with the ORM (Unit V: aggregation and annotation)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from ai_engine.retrieval import tokenize
from ask.models import ChatQuery
from engagement.models import Comment, Feedback, NewsletterSubscriber, Rating
from outreach_studio.models import OutreachKit

# Words too general to name a missing topic.
GAP_STOPWORDS = {
    "difference", "between", "work", "mean", "example", "simple", "word", "happen", "make", "made", "use",
    "type", "kind", "form", "cause", "caus", "thing", "way", "important", "different", "doe", "does",
}


def question_stats(days: int = 14) -> dict:
    since = timezone.now() - timedelta(days=days)
    qs = ChatQuery.objects.filter(created_at__gte=since)
    agg = qs.aggregate(
        total=Count("id"),
        found=Count("id", filter=Q(in_repository=True)),
        avg_match=Avg("trust_score", filter=Q(in_repository=True)),
        rated=Count("id", filter=Q(helpful__isnull=False)),
        helpful=Count("id", filter=Q(helpful=True)),
    )
    total = agg["total"] or 0
    return {
        "days": days,
        "total": total,
        "found_pct": round(100 * agg["found"] / total) if total else 0,
        "avg_match": round(agg["avg_match"] or 0),
        "helpful_pct": round(100 * agg["helpful"] / agg["rated"]) if agg["rated"] else None,
    }


def questions_per_day(days: int = 14) -> list[dict]:
    """One row per day (including empty days) with total and found counts, for the bar chart."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = (
        ChatQuery.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"), found=Count("id", filter=Q(in_repository=True)))
    )
    by_day = {r["day"]: r for r in rows}
    peak = max([r["total"] for r in rows] or [1])
    series = []
    for i in range(days):
        day = start + timedelta(days=i)
        r = by_day.get(day, {"total": 0, "found": 0})
        series.append(
            {
                "day": day,
                "total": r["total"],
                "found": r["found"],
                "missing": r["total"] - r["found"],
                "total_pct": round(100 * r["total"] / peak),
                "found_pct": round(100 * r["found"] / peak),
            }
        )
    return series


def gap_radar(limit: int = 8, days: int = 60) -> list[dict]:
    """Topics students ask about that the repository cannot answer yet, most asked first.

    Words are grouped by stem ("volcanoes" and "volcano" count together) but shown in
    the form students used. Words that always appear together become one phrase
    ("black hole"), and words that only ever appear inside a bigger topic are dropped.
    """
    since = timezone.now() - timedelta(days=days)
    unanswered = list(
        ChatQuery.objects.filter(in_repository=False, created_at__gte=since).values_list("question", flat=True)[:500]
    )
    asked_in: dict[str, set[int]] = defaultdict(set)
    surface: dict[str, Counter] = defaultdict(Counter)
    for i, question in enumerate(unanswered):
        for word in re.findall(r"[a-z]+", question.lower()):
            for stem in tokenize(word):
                if stem in GAP_STOPWORDS:
                    continue
                asked_in[stem].add(i)
                surface[stem][word] += 1

    def label(stem: str) -> str:
        return surface[stem].most_common(1)[0][0]

    def position(stem: str, question: str) -> int:
        found = [question.lower().find(w) for w in surface[stem] if w in question.lower()]
        return min(found) if found else len(question)

    topics: list[dict] = []
    for stem in sorted(asked_in, key=lambda s: (-len(asked_in[s]), s)):
        qs = asked_in[stem]
        merged = False
        for topic in topics:
            overlap = len(qs & topic["ids"]) / len(qs)
            if qs == topic["ids"]:
                # Always asked together: join into one phrase, in the order students write it.
                sample = unanswered[next(iter(qs))]
                parts = topic["stems"] + [stem]
                parts.sort(key=lambda s: position(s, sample))
                topic["stems"] = parts
                merged = True
                break
            if overlap >= 0.8:
                merged = True  # only ever part of a bigger topic
                break
        if not merged:
            topics.append({"stems": [stem], "ids": qs})
        if len(topics) >= limit * 2:
            break

    result = []
    for topic in sorted(topics, key=lambda t: -len(t["ids"]))[:limit]:
        examples = list(dict.fromkeys(unanswered[i] for i in sorted(topic["ids"])))[:3]
        result.append({"topic": " ".join(label(s) for s in topic["stems"]), "count": len(topic["ids"]), "examples": examples})
    return result


def kit_counts() -> dict:
    return dict(OutreachKit.objects.values_list("status").annotate(n=Count("id")))


def top_rated_kits(limit: int = 5) -> list[dict]:
    ct = ContentType.objects.get_for_model(OutreachKit)
    rows = (
        Rating.objects.filter(content_type=ct)
        .values("object_id")
        .annotate(avg=Avg("stars"), n=Count("id"))
        .order_by("-avg", "-n")[:limit]
    )
    kits = OutreachKit.objects.in_bulk([r["object_id"] for r in rows])
    return [{"kit": kits[r["object_id"]], "avg": round(r["avg"], 1), "n": r["n"]} for r in rows if r["object_id"] in kits]


def community() -> dict:
    return {
        "open_feedback": Feedback.objects.filter(resolved=False).count(),
        "subscribers": NewsletterSubscriber.objects.filter(is_active=True).count(),
        "comments_week": Comment.objects.filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
    }
