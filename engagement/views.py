"""Engagement views: every POST is CSRF-protected and ends in a redirect (POST-redirect-GET)."""

import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CommentForm, FeedbackForm, NewsletterForm, RatingForm
from .models import Comment, NewsletterSubscriber, Rating

FEEDBACK_LIMIT = 3  # messages per visitor per hour (kept in the session)
ALLOWED_TARGETS = {("outreach_studio", "outreachkit")}  # Suhaib adds e.g. ("repository", "resource")


def _back(request, fallback="/"):
    """Return to the page the form was on, but only within this site."""
    url = request.POST.get("next") or request.META.get("HTTP_REFERER") or fallback
    if url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return fallback


def _target(ct_id: int, object_id: int):
    ct = get_object_or_404(ContentType, pk=ct_id)
    if (ct.app_label, ct.model) not in ALLOWED_TARGETS:
        raise Http404("Comments are not open here.")
    try:
        return ct, ct.get_object_for_this_type(pk=object_id)
    except ct.model_class().DoesNotExist as exc:
        raise Http404 from exc


# ---------------------------------------------------------------------------
# Comments and ratings
# ---------------------------------------------------------------------------
@login_required
@require_POST
def comment_create(request, ct_id: int, object_id: int):
    ct, obj = _target(ct_id, object_id)
    form = CommentForm(request.POST)
    back = _back(request, getattr(obj, "get_absolute_url", lambda: "/")())
    if form.is_valid():
        comment = form.save(commit=False)
        comment.content_type, comment.object_id, comment.user = ct, obj.pk, request.user
        parent_id = form.cleaned_data.get("parent_id")
        if parent_id:
            parent = Comment.objects.filter(pk=parent_id, content_type=ct, object_id=obj.pk, parent__isnull=True).first()
            comment.parent = parent  # replies go one level deep only
        comment.save()
        messages.success(request, "Comment posted.")
        return redirect(f"{back.split('#')[0]}#comment-{comment.pk}")
    messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect(f"{back.split('#')[0]}#comments")


@login_required
@require_POST
def comment_delete(request, pk: int):
    comment = get_object_or_404(Comment, pk=pk)
    if comment.user != request.user and not request.user.has_perm("engagement.delete_comment"):
        raise Http404
    comment.delete()
    messages.info(request, "Comment deleted.")
    return redirect(f"{_back(request).split('#')[0]}#comments")


@login_required
@require_POST
def rate(request, ct_id: int, object_id: int):
    ct, obj = _target(ct_id, object_id)
    form = RatingForm(request.POST)
    if form.is_valid():
        Rating.objects.update_or_create(
            user=request.user, content_type=ct, object_id=obj.pk, defaults={"stars": form.cleaned_data["stars"]}
        )
        messages.success(request, f"Thanks for rating it {form.cleaned_data['stars']} out of 5.")
    return redirect(_back(request, obj.get_absolute_url()))


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def feedback(request):
    recent = [t for t in request.session.get("feedback_times", []) if t > time.time() - 3600]
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if len(recent) >= FEEDBACK_LIMIT:
            messages.error(request, "You have sent several messages in the last hour. Please try again later.")
        elif form.is_valid():
            item = form.save(commit=False)
            item.user = request.user if request.user.is_authenticated else None
            item.save()
            request.session["feedback_times"] = recent + [time.time()]
            return redirect("engagement:feedback_thanks")
    else:
        initial = {"page_url": request.GET.get("from", "")[:300]}
        if request.user.is_authenticated:
            initial.update(name=request.user.get_full_name() or request.user.username, email=request.user.email)
        if request.GET.get("topic"):
            initial.update(category="content", message=f"Please add a lesson on: {request.GET['topic'][:200]}")
        form = FeedbackForm(initial=initial)
    return render(request, "engagement/feedback.html", {"form": form})


def feedback_thanks(request):
    return render(request, "engagement/feedback_thanks.html")


# ---------------------------------------------------------------------------
# Newsletter
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            sub, created = NewsletterSubscriber.objects.update_or_create(
                email=form.cleaned_data["email"],
                defaults={
                    "name": form.cleaned_data["name"],
                    "language": form.cleaned_data["language"],
                    "is_active": True,
                    "unsubscribed_at": None,
                },
            )
            request.session["newsletter_email"] = sub.email
            messages.success(request, "You're subscribed." if created else "Welcome back, you're subscribed again.")
            response = redirect("engagement:newsletter")
            response.set_cookie("se_lang", sub.language, max_age=365 * 24 * 3600, samesite="Lax")
            return response
    else:
        form = NewsletterForm(initial={"language": request.COOKIES.get("se_lang", "en")})
    subscribed = NewsletterSubscriber.objects.filter(email=request.session.get("newsletter_email", ""), is_active=True).first()
    return render(request, "engagement/newsletter.html", {"form": form, "subscribed": subscribed})


@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    sub = get_object_or_404(NewsletterSubscriber, token=token)
    if request.method == "POST":
        sub.is_active = False
        sub.unsubscribed_at = timezone.now()
        sub.save(update_fields=["is_active", "unsubscribed_at"])
        messages.info(request, f"{sub.email} will not get any more emails from us.")
        return redirect("engagement:newsletter")
    return render(request, "engagement/unsubscribe.html", {"sub": sub})
