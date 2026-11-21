"""Comments, ratings, feedback and newsletter: models, forms, views, CSRF and admin."""

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from outreach_studio.models import KitItem, OutreachKit

from .forms import CommentForm, FeedbackForm
from .models import Comment, Feedback, NewsletterSubscriber, Rating


def published_kit() -> OutreachKit:
    lesson = Group.objects.create(name="Lesson")
    kit = OutreachKit.objects.create(
        content_type=ContentType.objects.get_for_model(Group), object_id=lesson.pk, source_title="Lesson", title="Rain", status="review"
    )
    KitItem.objects.create(kit=kit, kind="summary", content={"title": "Rain", "points": ["a", "b"]}, approved=True)
    kit.publish()
    return kit


class CommentTests(TestCase):
    def setUp(self):
        self.kit = published_kit()
        self.ct = ContentType.objects.get_for_model(OutreachKit)
        self.url = reverse("engagement:comment_create", args=[self.ct.pk, self.kit.pk])
        self.user = User.objects.create_user("riya", password="pass12345", first_name="Riya")

    def test_login_required(self):
        response = self.client.post(self.url, {"body": "Nice lesson"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertFalse(Comment.objects.exists())

    def test_post_reply_and_render_on_kit_page(self):
        self.client.login(username="riya", password="pass12345")
        self.client.post(self.url, {"body": "What is a cloud made of?", "next": self.kit.get_absolute_url()})
        parent = Comment.objects.get()
        self.client.post(self.url, {"body": "Tiny water droplets!", "parent_id": parent.pk})
        reply = Comment.objects.exclude(pk=parent.pk).get()
        self.assertEqual(reply.parent, parent)
        page = self.client.get(self.kit.get_absolute_url())
        self.assertContains(page, "What is a cloud made of?")
        self.assertContains(page, "Tiny water droplets!")
        self.assertContains(page, "2 comments")

    def test_hidden_comment_not_shown(self):
        Comment.objects.create(content_type=self.ct, object_id=self.kit.pk, user=self.user, body="spammy thing", is_visible=False)
        self.assertNotContains(self.client.get(self.kit.get_absolute_url()), "spammy thing")

    def test_only_author_can_delete(self):
        c = Comment.objects.create(content_type=self.ct, object_id=self.kit.pk, user=self.user, body="mine")
        User.objects.create_user("other", password="pass12345")
        self.client.login(username="other", password="pass12345")
        self.assertEqual(self.client.post(reverse("engagement:comment_delete", args=[c.pk])).status_code, 404)
        self.client.login(username="riya", password="pass12345")
        self.client.post(reverse("engagement:comment_delete", args=[c.pk]))
        self.assertFalse(Comment.objects.exists())

    def test_comments_only_on_allowed_models(self):
        self.client.login(username="riya", password="pass12345")
        user_ct = ContentType.objects.get_for_model(User)
        response = self.client.post(reverse("engagement:comment_create", args=[user_ct.pk, self.user.pk]), {"body": "hello there"})
        self.assertEqual(response.status_code, 404)

    def test_form_rules(self):
        self.assertFalse(CommentForm({"body": "ok"}).is_valid())
        self.assertFalse(CommentForm({"body": "see http://a.com and http://b.com"}).is_valid())
        self.assertTrue(CommentForm({"body": "see http://a.com please"}).is_valid())

    def test_open_redirect_blocked(self):
        self.client.login(username="riya", password="pass12345")
        response = self.client.post(self.url, {"body": "Good one", "next": "https://evil.example.com/"})
        self.assertTrue(response["Location"].startswith(self.kit.get_absolute_url()))


class RatingTests(TestCase):
    def test_rate_and_change_rating(self):
        kit = published_kit()
        ct = ContentType.objects.get_for_model(OutreachKit)
        User.objects.create_user("a", password="pass12345")
        self.client.login(username="a", password="pass12345")
        url = reverse("engagement:rate", args=[ct.pk, kit.pk])
        self.client.post(url, {"stars": "4"})
        self.client.post(url, {"stars": "5"})
        self.assertEqual(Rating.objects.get().stars, 5)
        self.assertEqual(Rating.summary(kit), {"average": 5.0, "count": 1})
        self.client.post(url, {"stars": "9"})
        self.assertEqual(Rating.objects.get().stars, 5)
        self.assertContains(self.client.get(kit.get_absolute_url()), "5.0 · 1 rating")


class FeedbackTests(TestCase):
    url = "/feedback/"

    def valid(self, **extra):
        return {"name": "Asha", "email": "asha@example.com", "category": "suggestion", "message": "Please add more maths lessons.", "page_url": "", "website": "", **extra}

    def test_post_redirect_get(self):
        response = self.client.post(self.url, self.valid())
        self.assertRedirects(response, reverse("engagement:feedback_thanks"))
        self.assertEqual(Feedback.objects.get().name, "Asha")

    def test_problem_needs_detail(self):
        form = FeedbackForm(self.valid(category="problem", message="The page is broken now."))
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)

    def test_honeypot(self):
        self.assertFalse(FeedbackForm(self.valid(website="http://spam")).is_valid())

    def test_rate_limit(self):
        for _ in range(3):
            self.client.post(self.url, self.valid())
        response = self.client.post(self.url, self.valid())
        self.assertEqual(Feedback.objects.count(), 3)
        self.assertContains(response, "several messages")

    def test_topic_request_prefills(self):
        page = self.client.get(self.url + "?topic=volcanoes")
        self.assertContains(page, "Please add a lesson on: volcanoes")

    def test_csrf(self):
        client = self.client_class(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, self.valid()).status_code, 403)


class NewsletterTests(TestCase):
    def test_subscribe_sets_language_cookie_and_resubscribe(self):
        data = {"email": "Parent@Example.com", "name": "P", "language": "mr", "consent": "on", "website": ""}
        response = self.client.post("/newsletter/", data)
        self.assertRedirects(response, "/newsletter/")
        self.assertEqual(response.cookies["se_lang"].value, "mr")
        sub = NewsletterSubscriber.objects.get()
        self.assertEqual(sub.email, "parent@example.com")
        self.client.post(reverse("engagement:unsubscribe", args=[sub.token]))
        sub.refresh_from_db()
        self.assertFalse(sub.is_active)
        self.client.post("/newsletter/", data)
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)

    def test_consent_required(self):
        self.client.post("/newsletter/", {"email": "x@example.com", "language": "en", "website": ""})
        self.assertFalse(NewsletterSubscriber.objects.exists())

    def test_admin_csv_export(self):
        NewsletterSubscriber.objects.create(email="a@example.com", language="hi")
        User.objects.create_superuser("admin", "ad@example.com", "pass12345")
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("admin:engagement_newslettersubscriber_changelist"),
            {"action": "export_csv", "_selected_action": NewsletterSubscriber.objects.values_list("pk", flat=True)},
        )
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(b"a@example.com,,hi,True", response.content)
