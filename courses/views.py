"""Syllabus browser, topic pages, scored quizzes and progress."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count, Max, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from outreach_studio.models import OutreachKit
from repository.models import Resource, Subject

from .forms import QuizForm, QuizFromKitForm
from .models import GRADES, PASS_MARK, Quiz, QuizAttempt, Topic, Unit


def passed_topic_ids(user) -> set[int]:
    """Topics whose quiz this user has passed at least once."""
    if not user.is_authenticated:
        return set()
    best = (
        QuizAttempt.objects.filter(user=user, quiz__topic__isnull=False)
        .values("quiz__topic", "quiz")
        .annotate(best=Max("score"), total=Max("total"))
    )
    return {r["quiz__topic"] for r in best if r["total"] and 100 * r["best"] / r["total"] >= PASS_MARK}


def overview(request):
    """Pick a class: subjects with units for that class, and progress if logged in."""
    profile_grade = getattr(getattr(request.user, "profile", None), "grade", None)
    grade = request.GET.get("grade")
    grade = int(grade) if grade and grade.isdigit() else (profile_grade or 7)
    subjects = (
        Subject.objects.filter(units__grade=grade)
        .annotate(n_units=Count("units", distinct=True), n_topics=Count("units__topics", distinct=True))
        .order_by("name")
    )
    done = passed_topic_ids(request.user)
    rows = []
    for s in subjects:
        topic_ids = set(Topic.objects.filter(unit__subject=s, unit__grade=grade).values_list("pk", flat=True))
        rows.append({"subject": s, "done": len(topic_ids & done), "total": len(topic_ids)})
    return render(request, "courses/overview.html", {"grade": grade, "grades": GRADES, "rows": rows})


def syllabus(request, grade: int, subject: str):
    subject = get_object_or_404(Subject, slug=subject)
    units = (
        Unit.objects.filter(subject=subject, grade=grade)
        .prefetch_related(
            Prefetch(
                "topics",
                queryset=Topic.objects.annotate(
                    n_lessons=Count("resources", distinct=True), n_quizzes=Count("quizzes", distinct=True)
                ),
            )
        )
    )
    if not units:
        messages.info(request, f"No syllabus for {subject} in class {grade} yet.")
        return redirect(f"/courses/?grade={grade}")
    return render(request, "courses/syllabus.html", {"subject": subject, "grade": grade, "units": units, "done": passed_topic_ids(request.user)})


def topic_detail(request, pk: int, slug: str):
    topic = get_object_or_404(Topic.objects.select_related("unit__subject"), pk=pk)
    if slug != topic.slug:
        return redirect(topic, permanent=True)
    lessons = topic.resources.filter(status=Resource.Status.PUBLISHED).select_related("subject")
    quizzes = topic.quizzes.filter(is_published=True)
    siblings = list(topic.unit.topics.all())
    idx = siblings.index(topic)
    return render(
        request,
        "courses/topic.html",
        {
            "topic": topic,
            "lessons": lessons,
            "quizzes": quizzes,
            "prev": siblings[idx - 1] if idx > 0 else None,
            "next": siblings[idx + 1] if idx + 1 < len(siblings) else None,
            "is_done": topic.pk in passed_topic_ids(request.user),
        },
    )


@require_http_methods(["GET", "POST"])
def take_quiz(request, pk: int):
    quiz = get_object_or_404(Quiz, pk=pk, is_published=True)
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        form = QuizForm(quiz, request.POST)
        if form.is_valid():
            attempt = QuizAttempt.objects.create(quiz=quiz, user=request.user, answers=form.answers(), score=form.score(), total=quiz.size)
            return redirect("courses:result", pk=attempt.pk)
        messages.error(request, "Answer every question, then submit.")
    else:
        form = QuizForm(quiz)
    best = None
    if request.user.is_authenticated:
        best = quiz.attempts.filter(user=request.user).order_by("-score", "-created_at").first()
    return render(request, "courses/quiz.html", {"quiz": quiz, "form": form, "best": best})


@login_required
def quiz_result(request, pk: int):
    attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz__topic"), pk=pk, user=request.user)
    review = [
        {"q": q, "chosen": chosen, "right": chosen == q["answer"]}
        for q, chosen in zip(attempt.quiz.questions, attempt.answers)
    ]
    history = attempt.quiz.attempts.filter(user=request.user)[:5]
    return render(request, "courses/result.html", {"a": attempt, "review": review, "history": history, "pass_mark": PASS_MARK})


@login_required
def my_progress(request):
    attempts = QuizAttempt.objects.filter(user=request.user).select_related("quiz__topic__unit__subject")
    per_quiz = (
        attempts.values("quiz", "quiz__title")
        .annotate(best=Max("score"), total=Max("total"), tries=Count("id"))
        .order_by("quiz__title")
    )
    return render(request, "courses/progress.html", {"recent": attempts[:10], "per_quiz": per_quiz})


@login_required
@permission_required("courses.add_quiz", raise_exception=True)
@require_POST
def quiz_from_kit(request, kit_id: int):
    """An approved Outreach Studio quiz becomes a scored quiz, optionally linked to a syllabus topic."""
    kit = get_object_or_404(OutreachKit, pk=kit_id)
    item = kit.items.filter(kind="quiz", approved=True).first()
    if item is None or not item.content.get("questions"):
        messages.error(request, "Approve the kit's quiz first.")
        return redirect("outreach_studio:kit", pk=kit.pk)
    form = QuizFromKitForm(request.POST)
    topic = form.cleaned_data["topic"] if form.is_valid() else None
    quiz = Quiz.objects.create(
        title=f"Quiz: {kit.title}", topic=topic, kit=kit, questions=item.content["questions"], generated_by_ai=True, created_by=request.user
    )
    messages.success(request, "Scored quiz created. Students' results now count towards their progress.")
    return redirect(quiz)


def quiz_stats(quiz) -> list[dict]:
    """Share of students who got each question right (first attempts only), hardest first."""
    firsts = {}
    for a in quiz.attempts.order_by("created_at"):
        firsts.setdefault(a.user_id, a)
    rows = []
    for i, q in enumerate(quiz.questions):
        answered = [a for a in firsts.values() if i < len(a.answers)]
        right = sum(1 for a in answered if a.answers[i] == q["answer"])
        rows.append({"q": q["q"], "right_pct": round(100 * right / len(answered)) if answered else None, "n": len(answered)})
    return sorted([r for r in rows if r["right_pct"] is not None], key=lambda r: r["right_pct"])


def class_quiz_summary(limit: int = 6):
    """For the teacher dashboard: quizzes with attempt counts and average score."""
    return (
        Quiz.objects.annotate(tries=Count("attempts"), avg=Avg("attempts__score"))
        .filter(tries__gt=0)
        .order_by("-tries")[:limit]
    )


@login_required
@permission_required("courses.view_quizattempt", raise_exception=True)
def quiz_report(request, pk: int):
    quiz = get_object_or_404(Quiz, pk=pk)
    agg = quiz.attempts.aggregate(tries=Count("id"), students=Count("user", distinct=True), avg=Avg("score"))
    return render(request, "courses/report.html", {"quiz": quiz, "agg": agg, "out_of": f"/{quiz.size}", "rows": quiz_stats(quiz), "latest": quiz.attempts.select_related("user")[:15]})
