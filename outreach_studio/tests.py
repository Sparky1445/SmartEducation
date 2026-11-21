"""Outreach Studio: fan-out/fan-in pipeline, teacher review, publishing and public pages. Offline (MOCK)."""

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_engine import outreach_pipeline, services
from ai_engine.models import AgentRun
from ask.tests import MOCK, WATER_CYCLE

from .models import KitItem, OutreachKit


def teacher(publish=True) -> User:
    user = User.objects.create_user("teacher", password="pass12345")
    codes = ["add_outreachkit"] + (["publish_outreachkit"] if publish else [])
    user.user_permissions.add(*Permission.objects.filter(codename__in=codes))
    return user


@override_settings(AI_ENGINE=MOCK, OUTREACH_RUN_INLINE=True)
class PipelineTests(TestCase):
    def setUp(self):
        self.lesson = Group.objects.create(name="Class 7 · The Water Cycle")
        services.index_source(self.lesson, text=WATER_CYCLE)

    def test_fan_out_fan_in_builds_every_part(self):
        draft = outreach_pipeline.build_kit(self.lesson, "The Water Cycle")
        self.assertEqual(set(draft.drafts), {"summary", "quiz", "article", "social", "translation"})
        self.assertTrue(draft.drafts["summary"]["points"])
        q = draft.drafts["quiz"]["questions"][0]
        self.assertIn(q["options"][q["answer"]].lower(), WATER_CYCLE.lower())
        self.assertTrue(all(v == "ok" for v in draft.verdicts.values()))
        run = AgentRun.objects.get(pk=draft.run_id)
        self.assertEqual(run.pipeline, "outreach")
        self.assertEqual({s["agent"] for s in run.trace}, {"Summariser", "Quizmaster", "Columnist", "Herald", "Translator", "Editor"})

    def test_service_creates_kit_with_seven_parts(self):
        kit_id = services.build_outreach_kit(self.lesson)
        kit = OutreachKit.objects.get(pk=kit_id)
        self.assertEqual(services.kit_status(kit_id), "review")
        self.assertEqual(kit.items.count(), 7)
        self.assertEqual(sorted(kit.items.filter(kind="translation").values_list("language", flat=True)), ["hi", "kok", "mr"])

    def test_lesson_without_text_fails_politely(self):
        empty = Group.objects.create(name="Empty")
        kit = OutreachKit.objects.get(pk=services.build_outreach_kit(empty))
        self.assertEqual(kit.status, "failed")
        self.assertIn("no readable text", kit.error)

    def test_normalise_rejects_broken_quiz(self):
        content, ok = outreach_pipeline.normalise("quiz", {"questions": [{"q": "x", "options": ["a"], "answer": 5}]})
        self.assertFalse(ok)
        self.assertEqual(content["questions"], [])
        self.assertIsNone(outreach_pipeline.parse_json("not json"))
        self.assertEqual(outreach_pipeline.parse_json('```json\n{"a": 1}\n```'), {"a": 1})


@override_settings(AI_ENGINE=MOCK, OUTREACH_RUN_INLINE=True)
class StudioViewTests(TestCase):
    def setUp(self):
        self.lesson = Group.objects.create(name="Class 7 · The Water Cycle")
        services.index_source(self.lesson, text=WATER_CYCLE)
        self.user = teacher()
        self.client.login(username="teacher", password="pass12345")

    def make_kit(self) -> OutreachKit:
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(Group)
        self.client.post(reverse("outreach_studio:kit_create", args=[ct.pk, self.lesson.pk]))
        return OutreachKit.objects.latest("pk")

    def test_studio_requires_permission(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("outreach_studio:studio")).status_code, 302)
        User.objects.create_user("student", password="pass12345")
        self.client.login(username="student", password="pass12345")
        self.assertEqual(self.client.get(reverse("outreach_studio:studio")).status_code, 403)

    def test_studio_lists_lessons_and_hides_the_engine(self):
        page = self.client.get(reverse("outreach_studio:studio"))
        self.assertContains(page, "The Water Cycle")
        for word in ("agent", "Summariser", "Editor", "MOCK", "Semantic Kernel"):
            self.assertNotContains(page, word)

    def test_full_review_and_publish_flow(self):
        kit = self.make_kit()
        page = self.client.get(kit.get_studio_url())
        self.assertContains(page, "Study notes")
        self.assertNotContains(page, "Quizmaster")

        # Publishing needs approved study notes.
        self.client.post(reverse("outreach_studio:kit_publish", args=[kit.pk]))
        kit.refresh_from_db()
        self.assertEqual(kit.status, "review")

        summary = kit.items.get(kind="summary")
        self.client.post(
            reverse("outreach_studio:item_edit", args=[summary.pk]),
            {f"item{summary.pk}-title": "Water on the move", f"item{summary.pk}-points": "Water evaporates.\nVapour condenses into clouds."},
        )
        summary.refresh_from_db()
        self.assertEqual(summary.content["points"], ["Water evaporates.", "Vapour condenses into clouds."])
        self.assertTrue(summary.edited)

        quiz = kit.items.get(kind="quiz")
        for item in (summary, quiz):
            self.client.post(reverse("outreach_studio:item_approve", args=[item.pk]), {"approved": "1"})
        self.client.post(reverse("outreach_studio:kit_publish", args=[kit.pk]))
        kit.refresh_from_db()
        self.assertEqual(kit.status, "published")

        public = self.client_class().get(kit.get_absolute_url())
        self.assertContains(public, "Water on the move")
        self.assertContains(public, "data-quiz")
        self.assertNotContains(public, "Instagram")  # social posts were not approved
        self.assertIn(kit, services.published_kits())

    def test_bad_edit_is_rejected(self):
        kit = self.make_kit()
        summary = kit.items.get(kind="summary")
        self.client.post(reverse("outreach_studio:item_edit", args=[summary.pk]), {f"item{summary.pk}-title": "T", f"item{summary.pk}-points": "only one"})
        summary.refresh_from_db()
        self.assertFalse(summary.edited)

    def test_teacher_without_publish_permission(self):
        kit = self.make_kit()
        self.client.logout()
        User.objects.filter(username="teacher").delete()
        teacher(publish=False)
        self.client.login(username="teacher", password="pass12345")
        self.assertEqual(self.client.post(reverse("outreach_studio:kit_publish", args=[kit.pk])).status_code, 403)

    def test_status_json(self):
        kit = self.make_kit()
        data = self.client.get(reverse("outreach_studio:kit_status", args=[kit.pk])).json()
        self.assertEqual(data, {"status": "review", "label": "Ready for review", "busy": False})


class LearnPageTests(TestCase):
    def test_unpublished_kits_are_hidden(self):
        lesson = Group.objects.create(name="L")
        from django.contrib.contenttypes.models import ContentType

        kit = OutreachKit.objects.create(content_type=ContentType.objects.get_for_model(Group), object_id=lesson.pk, source_title="L", title="Hidden", slug="hidden", status="review")
        self.assertEqual(self.client.get(kit.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("outreach_studio:learn")), "Hidden")

    def test_wrong_slug_redirects(self):
        lesson = Group.objects.create(name="L")
        from django.contrib.contenttypes.models import ContentType

        kit = OutreachKit.objects.create(content_type=ContentType.objects.get_for_model(Group), object_id=lesson.pk, source_title="L", title="Rain", status="review")
        KitItem.objects.create(kit=kit, kind="summary", content={"title": "Rain", "points": ["a", "b"]}, approved=True)
        kit.publish()
        response = self.client.get(f"/learn/{kit.pk}-old-name/")
        self.assertRedirects(response, kit.get_absolute_url(), status_code=301)
