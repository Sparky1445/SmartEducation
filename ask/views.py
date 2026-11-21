"""Ask the Repository: students ask, the page answers from uploaded lessons with sources."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from ai_engine import services

from .forms import AskForm, FeedbackForm
from .models import ChatQuery

HISTORY_KEY = "ask_history"  # session: ids of this visitor's recent questions
HISTORY_SIZE = 12

EXAMPLES = [
    "What causes the seasons on Earth?",
    "Explain photosynthesis in simple words.",
    "What is the difference between weather and climate?",
]


def _history(request) -> list[int]:
    return request.session.get(HISTORY_KEY, [])


def _remember(request, query: ChatQuery) -> None:
    ids = [query.pk] + [i for i in _history(request) if i != query.pk]
    request.session[HISTORY_KEY] = ids[:HISTORY_SIZE]


def _owned(request, pk: int) -> ChatQuery:
    """Visitors can only reopen their own questions (from their session history)."""
    if pk not in _history(request):
        raise ChatQuery.DoesNotExist
    return ChatQuery.objects.get(pk=pk)


@require_http_methods(["GET", "POST"])
def ask_page(request):
    if request.method == "POST":
        form = AskForm(request.POST)
        if form.is_valid():
            question = form.cleaned_data["question"]
            try:
                result = services.ask(question, user=request.user)
            except Exception:  # noqa: BLE001 - logged by the engine; the visitor gets a calm message
                messages.error(request, "Something went wrong while searching. Please try again in a moment.")
                return redirect("ask:home")
            if not request.session.session_key:
                request.session.save()
            query = ChatQuery.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_key=request.session.session_key or "",
                question=question,
                answer=result["answer"],
                citations=result["citations"],
                trust_score=result["trust_score"],
                in_repository=result["in_repository"],
                run_id=result["run_id"],
            )
            _remember(request, query)
            return redirect(f"{reverse('ask:home')}?q={query.pk}#answer")  # POST-redirect-GET
    else:
        form = AskForm()

    current = None
    q = request.GET.get("q", "")
    if q.isdigit():
        try:
            current = _owned(request, int(q))
        except ChatQuery.DoesNotExist:
            messages.info(request, "That answer is not in your history any more.")

    history = list(ChatQuery.objects.filter(pk__in=_history(request)))
    history.sort(key=lambda c: _history(request).index(c.pk))

    return render(
        request,
        "ask/ask.html",
        {"form": form, "current": current, "history": history, "examples": EXAMPLES},
    )


@require_POST
def feedback(request, pk: int):
    query = get_object_or_404(ChatQuery, pk=pk)
    if pk not in _history(request):
        return redirect("ask:home")
    form = FeedbackForm(request.POST)
    if form.is_valid():
        query.helpful = form.cleaned_data["helpful"]
        query.save(update_fields=["helpful"])
        messages.success(request, "Thanks, your feedback helps the teachers improve the repository.")
    return redirect(f"{reverse('ask:home')}?q={pk}#answer")


@require_POST
def clear_history(request):
    request.session.pop(HISTORY_KEY, None)
    messages.info(request, "Your question history on this device was cleared.")
    return redirect("ask:home")
