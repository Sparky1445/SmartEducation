"""Syllabus, topics, scored quizzes (dynamic form), progress, kit → quiz, teacher report."""

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from outreach_studio.models import KitItem, OutreachKit
from repository.models import Resource, Subject

from .models import Quiz, QuizAttempt, Topic, Unit, validate_questions

QUESTIONS = [
    {"q": "What tilts?", "options": ["Earth's axis", "The Moon", "The Sun"], "answer": 0, "why": "The axis is tilted 23.5°."},
    {"q": "Summer in the north when the north tilts…", "options": ["away", "towards the Sun"], "answer": 1, "why": ""},
]


class CoursesTests(TestCase):
    def setUp(self):
        self.geo = Subject.objects.get(slug="geography")
        self.unit = Unit.objects.create(subject=self.geo, grade=7, number=2, title="Earth and the Sun")
        self.topic = Topic.objects.create(unit=self.unit, order=1, title="Seasons", objectives="Explain why seasons happen\nUse a globe to show tilt")
        Topic.objects.create(unit=self.unit, order=2, title="Day and night")
        self.lesson = Resource.objects.create(title="Why we have seasons", subject=self.geo, grade=7, kind="link", url="https://example.com")
        self.topic.resources.add(self.lesson)
        self.quiz = Quiz.objects.create(title="Seasons quiz", topic=self.topic, questions=QUESTIONS)
        self.user = User.objects.create_user("sana", password="pass12345")

    def test_overview_syllabus_and_topic_pages(self):
        self.assertContains(self.client.get(reverse("courses:overview"), {"grade": 7}), "Geography")
        page = self.client.get(reverse("courses:syllabus", args=[7, "geography"]))
        self.assertContains(page, "Earth and the Sun")
        self.assertContains(page, "1 lesson · quiz")
        topic = self.client.get(self.topic.get_absolute_url())
        self.assertContains(topic, "Explain why seasons happen")
        self.assertContains(topic, "Why we have seasons")
        self.assertContains(topic, "Day and night")  # next-topic link
        self.assertContains(self.client.get(self.lesson.get_absolute_url()), "Syllabus:")

    def test_empty_syllabus_redirects(self):
        response = self.client.get(reverse("courses:syllabus", args=[9, "geography"]))
        self.assertRedirects(response, "/courses/?grade=9")

    def test_quiz_scoring_and_progress(self):
        self.client.login(username="sana", password="pass12345")
        url = self.quiz.get_absolute_url()
        self.assertContains(self.client.post(url, {"q0": "0"}), "Choose an answer")  # q1 missing
        response = self.client.post(url, {"q0": "0", "q1": "1"})
        attempt = QuizAttempt.objects.get()
        self.assertRedirects(response, reverse("courses:result", args=[attempt.pk]))
        self.assertEqual((attempt.score, attempt.total, attempt.passed), (2, 2, True))
        result = self.client.get(reverse("courses:result", args=[attempt.pk]))
        self.assertContains(result, "Passed")
        self.assertContains(result, "The axis is tilted")
        self.assertContains(self.client.get(reverse("courses:syllabus", args=[7, "geography"])), "· done")
        self.assertContains(self.client.get(reverse("courses:progress")), "2 / 2")
        self.assertContains(self.client.get(reverse("dashboard:student")), "Seasons quiz")

    def test_anonymous_must_log_in_to_submit_and_cannot_see_others_results(self):
        response = self.client.post(self.quiz.get_absolute_url(), {"q0": "0", "q1": "0"})
        self.assertIn("/accounts/login/", response["Location"])
        a = QuizAttempt.objects.create(quiz=self.quiz, user=self.user, answers=[1, 0], score=0, total=2)
        User.objects.create_user("other", password="pass12345")
        self.client.login(username="other", password="pass12345")
        self.assertEqual(self.client.get(reverse("courses:result", args=[a.pk])).status_code, 404)

    def test_question_validation(self):
        validate_questions(QUESTIONS)
        for bad in ([], [{"q": "x", "options": ["a"], "answer": 0}], [{"q": "x", "options": ["a", "b"], "answer": 5}]):
            with self.assertRaises(ValidationError):
                validate_questions(bad)

    def test_kit_quiz_becomes_scored_quiz_and_report(self):
        teacher = User.objects.create_user("t", password="pass12345")
        teacher.user_permissions.add(*Permission.objects.filter(codename__in=["add_quiz", "view_quizattempt"]))
        lesson = Group.objects.create(name="L")
        kit = OutreachKit.objects.create(content_type=ContentType.objects.get_for_model(Group), object_id=lesson.pk, source_title="L", title="Seasons", status="published")
        KitItem.objects.create(kit=kit, kind="quiz", content={"questions": QUESTIONS, "flashcards": []}, approved=True)
        self.client.login(username="t", password="pass12345")
        self.client.post(reverse("courses:from_kit", args=[kit.pk]), {"topic": self.topic.pk})
        quiz = Quiz.objects.get(kit=kit)
        self.assertTrue(quiz.generated_by_ai)
        self.assertEqual(quiz.topic, self.topic)
        QuizAttempt.objects.create(quiz=quiz, user=self.user, answers=[1, 1], score=1, total=2)
        report = self.client.get(reverse("courses:report", args=[quiz.pk]))
        self.assertContains(report, "0% right")
        self.assertContains(report, "100% right")
        self.assertContains(report, "Hardest questions")
