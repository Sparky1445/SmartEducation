"""Home page, news (drafts, scheduling, archive, RSS), events (.ics), announcements, kit → news."""

from datetime import timedelta

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from outreach_studio.models import KitItem, OutreachKit

from .models import Announcement, Article, Event


def article(**kw):
    data = {"title": "Science fair winners", "standfirst": "Class 8 took first prize.", "body": "Para one.\n\nPara two.", "status": "published"}
    data.update(kw)
    return Article.objects.create(**data)


class NewsTests(TestCase):
    def test_home_shows_lead_news_and_events(self):
        article(title="Old story", published_at=timezone.now() - timedelta(days=3))
        article(title="Big lead story", featured=True)
        Event.objects.create(title="Parents' meeting", kind="meeting", starts_at=timezone.now() + timedelta(days=2), venue="Hall")
        page = self.client.get("/")
        self.assertContains(page, "Big lead story")
        self.assertContains(page, "Old story")
        self.assertContains(page, "Parents&#x27; meeting")
        self.assertContains(page, 'action="/ask/"')

    def test_drafts_and_scheduled_articles_are_hidden(self):
        draft = article(title="Secret draft", status="draft")
        future = article(title="Tomorrow's story", published_at=timezone.now() + timedelta(days=1))
        listing = self.client.get(reverse("media_portal:news"))
        self.assertNotContains(listing, "Secret draft")
        self.assertNotContains(listing, "Tomorrow")
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(future.get_absolute_url()).status_code, 404)

    def test_teacher_can_preview_draft(self):
        draft = article(title="Secret draft", status="draft")
        user = User.objects.create_user("t", password="pass12345")
        user.user_permissions.add(Permission.objects.get(codename="change_article"))
        self.client.login(username="t", password="pass12345")
        self.assertContains(self.client.get(draft.get_absolute_url()), "Preview")

    def test_detail_paragraphs_category_and_year_archive(self):
        a = article(category="achievement")
        page = self.client.get(a.get_absolute_url())
        self.assertContains(page, "<p>Para one.</p>", html=True)
        self.assertContains(page, "Discussion")
        self.assertContains(self.client.get(reverse("media_portal:news"), {"category": "achievement"}), a.title)
        self.assertNotContains(self.client.get(reverse("media_portal:news"), {"category": "notice"}), a.title)
        self.assertContains(self.client.get(f"/news/{a.published_at.year}/"), a.title)

    def test_rss_feed(self):
        article(title="Feed story")
        response = self.client.get(reverse("media_portal:feed"))
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertIn(b"Feed story", response.content)


class EventTests(TestCase):
    def test_upcoming_past_and_ics(self):
        soon = Event.objects.create(title="Annual day, 2026", kind="cultural", starts_at=timezone.now() + timedelta(days=5), venue="School ground")
        Event.objects.create(title="Old exam", kind="exam", starts_at=timezone.now() - timedelta(days=5))
        page = self.client.get(reverse("media_portal:events"))
        self.assertContains(page, "Annual day")
        self.assertContains(page, "Old exam")
        ics = self.client.get(reverse("media_portal:event_ics", args=[soon.pk]))
        self.assertEqual(ics["Content-Type"], "text/calendar; charset=utf-8")
        body = ics.content.decode()
        self.assertIn("SUMMARY:Annual day\\, 2026", body)
        self.assertIn("BEGIN:VEVENT", body)

    def test_end_before_start_is_invalid(self):
        e = Event(title="Bad", starts_at=timezone.now(), ends_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(ValidationError):
            e.full_clean()


class AnnouncementTests(TestCase):
    def test_banner_shows_current_and_can_be_hidden(self):
        a = Announcement.objects.create(text="School closed on Monday for rain", level="important")
        Announcement.objects.create(text="Expired notice", ends_at=timezone.now() - timedelta(days=1))
        page = self.client.get("/news/")
        self.assertContains(page, "School closed on Monday")
        self.assertNotContains(page, "Expired notice")
        self.client.post(reverse("media_portal:hide_announcement", args=[a.pk]), {"next": "/news/"})
        self.assertNotContains(self.client.get("/news/"), "School closed on Monday")


class KitToNewsTests(TestCase):
    def test_approved_kit_article_becomes_draft_news(self):
        lesson = Group.objects.create(name="Lesson")
        kit = OutreachKit.objects.create(content_type=ContentType.objects.get_for_model(Group), object_id=lesson.pk, source_title="L", title="Rain", status="review")
        item = KitItem.objects.create(kit=kit, kind="article", content={"headline": "How rain forms", "standfirst": "A short read.", "body": ["One.", "Two."]})
        user = User.objects.create_user("t", password="pass12345", is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(codename__in=["add_article", "change_article"]))
        self.client.login(username="t", password="pass12345")
        url = reverse("media_portal:from_kit", args=[kit.pk])
        self.client.post(url)
        self.assertFalse(Article.objects.exists())  # not approved yet
        item.approved = True
        item.save()
        response = self.client.post(url)
        a = Article.objects.get()
        self.assertRedirects(response, reverse("admin:media_portal_article_change", args=[a.pk]))
        self.assertEqual((a.title, a.status, a.category, a.source_kit), ("How rain forms", "draft", "learning", kit))
        self.assertEqual(a.paragraphs, ["One.", "Two."])
