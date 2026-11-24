"""Home page, news, events, the news RSS feed, and turning a kit's article into news."""

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.syndication.views import Feed
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from ai_engine import services
from ask.forms import AskForm
from engagement.forms import NewsletterForm
from outreach_studio.models import OutreachKit
from repository.models import Resource

from .models import Article, Event


def home(request):
    live = Article.objects.live().select_related("author")
    lead = live.filter(featured=True).first() or live.first()
    return render(
        request,
        "media_portal/home.html",
        {
            "lead": lead,
            "news": live.exclude(pk=getattr(lead, "pk", None))[:4],
            "events": Event.objects.filter(is_public=True, starts_at__gte=timezone.now() - timedelta(hours=6))[:4],
            "lessons": Resource.objects.published().select_related("subject")[:4],
            "kits": services.published_kits(limit=3),
            "ask_form": AskForm(),
            "newsletter_form": NewsletterForm(initial={"language": request.COOKIES.get("se_lang", "en")}),
        },
    )


class ArticleListView(ListView):
    template_name = "media_portal/news_list.html"
    context_object_name = "articles"
    paginate_by = 10

    def get_queryset(self):
        qs = Article.objects.live().select_related("author")
        if year := self.kwargs.get("year"):
            qs = qs.filter(published_at__year=year)
        self.category = self.request.GET.get("category", "")
        if self.category in Article.Category.values:
            qs = qs.filter(category=self.category)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        years = Article.objects.live().dates("published_at", "year", order="DESC")
        ctx.update({"category": self.category, "categories": Article.Category.choices, "year": self.kwargs.get("year"), "years": years})
        return ctx


def article_detail(request, year: int, slug: str):
    article = Article.objects.live().filter(published_at__year=year, slug=slug).select_related("author", "source_kit").first()
    if article is None:
        # Teachers can preview drafts and scheduled articles.
        if request.user.has_perm("media_portal.change_article"):
            article = Article.objects.filter(slug=slug).first()
        if article is None:
            raise Http404("No such article")
    more = Article.objects.live().filter(category=article.category).exclude(pk=article.pk)[:3]
    return render(request, "media_portal/article.html", {"a": article, "more": more})


class EventListView(ListView):
    template_name = "media_portal/events.html"
    context_object_name = "upcoming"

    def get_queryset(self):
        return Event.objects.filter(is_public=True, starts_at__gte=timezone.now() - timedelta(hours=6))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["past"] = Event.objects.filter(is_public=True, starts_at__lt=timezone.now() - timedelta(hours=6)).order_by("-starts_at")[:8]
        return ctx


def event_detail(request, pk: int, slug: str):
    event = get_object_or_404(Event, pk=pk, is_public=True)
    if slug != event.slug:
        return redirect(event, permanent=True)
    return render(request, "media_portal/event.html", {"e": event})


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def event_ics(request, pk: int):
    """Add-to-calendar file (iCalendar), works with Google Calendar, Outlook and phones."""
    event = get_object_or_404(Event, pk=pk, is_public=True)
    fmt = "%Y%m%dT%H%M%SZ"
    start = event.starts_at.astimezone(dt_timezone.utc)
    end = (event.ends_at or event.starts_at + timedelta(hours=1)).astimezone(dt_timezone.utc)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Smart Education//Events//EN", "BEGIN:VEVENT",
        f"UID:event-{event.pk}@smarteducation", f"DTSTAMP:{timezone.now().astimezone(dt_timezone.utc):{fmt}}",
        f"DTSTART:{start:{fmt}}", f"DTEND:{end:{fmt}}", f"SUMMARY:{_ics_text(event.title)}",
        f"LOCATION:{_ics_text(event.venue)}", f"DESCRIPTION:{_ics_text(event.description)}",
        f"URL:{request.build_absolute_uri(event.get_absolute_url())}", "END:VEVENT", "END:VCALENDAR",
    ]
    response = HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{event.slug}.ics"'
    return response


class NewsFeed(Feed):
    """RSS for news (django.contrib.syndication)."""

    title = "Smart Education news"
    link = "/news/"
    description = "News, notices and classroom stories from the school."

    def items(self):
        return Article.objects.live()[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.standfirst or (item.paragraphs[0] if item.paragraphs else "")

    def item_pubdate(self, item):
        return item.published_at


@login_required
@permission_required("media_portal.add_article", raise_exception=True)
@require_POST
def article_from_kit(request, kit_id: int):
    """Outreach Studio's approved article becomes a draft news story for a final check."""
    kit = get_object_or_404(OutreachKit, pk=kit_id)
    item = kit.items.filter(kind="article", approved=True).first()
    if item is None:
        messages.error(request, "Approve the kit's article first, then send it to News.")
        return redirect("outreach_studio:kit", pk=kit.pk)
    c = item.content
    article = Article.objects.create(
        title=c.get("headline") or kit.title,
        standfirst=c.get("standfirst", ""),
        body="\n\n".join(c.get("body", [])),
        category=Article.Category.LEARNING,
        author=request.user,
        source_kit=kit,
    )
    messages.success(request, "Draft news article created. Check it, then publish it in the admin.")
    return redirect("admin:media_portal_article_change", article.pk)


@require_POST
def hide_announcement(request, pk: int):
    hidden = request.session.get("hidden_announcements", [])
    if pk not in hidden:
        request.session["hidden_announcements"] = (hidden + [pk])[-20:]
    back = request.POST.get("next", "/")
    return redirect(back if back.startswith("/") and not back.startswith("//") else "/")
