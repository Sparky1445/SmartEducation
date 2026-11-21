"""Student and teacher dashboards, plus the theme and language preferences (cookies)."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from ai_engine import services
from ask.models import ChatQuery
from repository.models import Bookmark
from engagement.models import Comment, Feedback, NewsletterSubscriber
from outreach_studio.models import OutreachKit

from . import stats

TEACHER_PERM = "outreach_studio.add_outreachkit"
THEMES = {"light", "dark"}
LANGS = {"en", "hi", "mr", "kok"}
ONE_YEAR = 365 * 24 * 3600


@login_required
def home(request):
    """One /dashboard/ link for everyone; teachers and students land on their own page."""
    if request.user.has_perm(TEACHER_PERM):
        return redirect("dashboard:teacher")
    return redirect("dashboard:student")


class StudentDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/student.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        mine = ChatQuery.objects.filter(user=user)
        agg = mine.aggregate(total=Count("id"), found=Count("id", filter=Q(in_repository=True)))
        recent_ids = self.request.session.get("recent_kits", [])
        recent = OutreachKit.objects.filter(pk__in=recent_ids, status=OutreachKit.Status.PUBLISHED)
        recent = sorted(recent, key=lambda k: recent_ids.index(k.pk))
        ctx.update(
            {
                "questions": mine[:6],
                "asked": agg["total"],
                "found_pct": round(100 * agg["found"] / agg["total"]) if agg["total"] else 0,
                "recent_kits": recent,
                "up_next": services.suggest_next_kits(user, limit=4, exclude=recent_ids),
                "comments": Comment.objects.filter(user=user).select_related("content_type")[:5],
                "comment_count": Comment.objects.filter(user=user).count(),
                "bookmarks": Bookmark.objects.filter(user=user, resource__status="published").select_related("resource__subject")[:4],
                "subscription": NewsletterSubscriber.objects.filter(email__iexact=user.email, is_active=True).first() if user.email else None,
            }
        )
        return ctx


class TeacherDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "dashboard/teacher.html"
    permission_required = TEACHER_PERM
    raise_exception = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "q": stats.question_stats(14),
                "series": stats.questions_per_day(14),
                "gaps": stats.gap_radar(),
                "kits": stats.kit_counts(),
                "to_review": OutreachKit.objects.filter(status=OutreachKit.Status.REVIEW)[:5],
                "top_kits": stats.top_rated_kits(),
                "community": stats.community(),
                "feedback": Feedback.objects.filter(resolved=False)[:5],
                "latest_comments": Comment.objects.select_related("user", "content_type")[:5],
            }
        )
        return ctx


@require_POST
def set_preference(request):
    """Theme and language live in cookies, so they work without logging in (Unit VI)."""
    back = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = "/"
    response = redirect(back)
    theme = request.POST.get("theme")
    lang = request.POST.get("lang")
    if theme in THEMES:
        response.set_cookie("se_theme", theme, max_age=ONE_YEAR, samesite="Lax")
    if lang in LANGS:
        response.set_cookie("se_lang", lang, max_age=ONE_YEAR, samesite="Lax")
    return response
