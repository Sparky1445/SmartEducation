"""Dashboards, stats and preference cookies."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from ask.models import ChatQuery
from ask.tests import MOCK

from . import stats


def make_teacher():
    user = User.objects.create_user("teach", password="pass12345")
    user.user_permissions.add(Permission.objects.get(codename="add_outreachkit"))
    return user


@override_settings(WEB_LINKS={"OFFLINE": True}, AI_ENGINE=MOCK)
class DashboardTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_routes_by_role(self):
        User.objects.create_user("stu", password="pass12345")
        self.client.login(username="stu", password="pass12345")
        self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse("dashboard:student"))
        self.assertEqual(self.client.get(reverse("dashboard:teacher")).status_code, 403)
        make_teacher()
        self.client.login(username="teach", password="pass12345")
        self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse("dashboard:teacher"))

    def test_student_page_shows_own_questions_only(self):
        me = User.objects.create_user("stu", password="pass12345", first_name="Sana")
        other = User.objects.create_user("x", password="pass12345")
        ChatQuery.objects.create(user=me, question="How do volcanoes erupt?", answer="-", in_repository=False)
        ChatQuery.objects.create(user=other, question="Secret question of someone else", answer="-")
        self.client.login(username="stu", password="pass12345")
        page = self.client.get(reverse("dashboard:student"))
        self.assertContains(page, "Hello, Sana.")
        self.assertContains(page, "How do volcanoes erupt?")
        self.assertNotContains(page, "Secret question")
        # and the student can reopen it on the Ask page from any device
        q = ChatQuery.objects.get(user=me)
        self.assertContains(self.client.get(f"{reverse('ask:home')}?q={q.pk}"), "How do volcanoes erupt?")

    def test_teacher_page_and_gap_radar(self):
        for text in ["How do volcanoes erupt?", "Why do volcanoes form near plates?", "What is a black hole?"]:
            ChatQuery.objects.create(question=text, answer="-", in_repository=False)
        ChatQuery.objects.create(question="What is evaporation?", answer="-", in_repository=True, trust_score=80)
        gaps = stats.gap_radar()
        self.assertEqual(gaps[0]["topic"], "volcanoes")
        self.assertIn("black hole", [g["topic"] for g in gaps])
        self.assertEqual(gaps[0]["count"], 2)
        q = stats.question_stats()
        self.assertEqual((q["total"], q["found_pct"], q["avg_match"]), (4, 25, 80))
        self.assertEqual(sum(d["total"] for d in stats.questions_per_day()), 4)
        make_teacher()
        self.client.login(username="teach", password="pass12345")
        page = self.client.get(reverse("dashboard:teacher"))
        self.assertContains(page, "Gap radar")
        self.assertContains(page, "volcano")

    def test_theme_and_language_cookies(self):
        response = self.client.post(reverse("dashboard:preferences"), {"theme": "dark", "next": "/ask/"})
        self.assertRedirects(response, "/ask/", fetch_redirect_response=False)
        self.assertEqual(response.cookies["se_theme"].value, "dark")
        self.assertContains(self.client.get("/ask/"), 'data-theme="dark"')
        response = self.client.post(reverse("dashboard:preferences"), {"lang": "klingon"})
        self.assertNotIn("se_lang", response.cookies)

    def test_preference_redirect_stays_on_site(self):
        response = self.client.post(reverse("dashboard:preferences"), {"theme": "light", "next": "https://evil.example.com"})
        self.assertEqual(response["Location"], "/")
