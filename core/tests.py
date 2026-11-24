"""seed_demo builds a complete demo site and can be run twice."""

import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from ask.tests import MOCK

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, AI_ENGINE=MOCK, WEB_LINKS={"OFFLINE": True})
class SeedDemoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_seed_twice_and_everything_works(self):
        from ai_engine import services
        from courses.models import Quiz, Topic
        from media_portal.models import Article
        from outreach_studio.models import OutreachKit
        from repository.models import Resource

        call_command("seed_demo", stdout=StringIO())
        counts = (Resource.objects.count(), Topic.objects.count(), Article.objects.count(), Quiz.objects.count())
        call_command("seed_demo", stdout=StringIO())  # idempotent
        self.assertEqual(counts, (Resource.objects.count(), Topic.objects.count(), Article.objects.count(), Quiz.objects.count()))
        self.assertEqual(counts[0], 6)
        self.assertEqual(OutreachKit.objects.filter(status="published").count(), 1)
        self.assertEqual(Quiz.objects.count(), 2)  # hand-written seasons quiz + one from the kit
        self.assertTrue(services.ask("What is condensation in the water cycle?")["in_repository"])

        self.assertTrue(self.client.login(username="student", password="smartedu-demo-26"))
        for url in ("/", "/repository/", "/courses/", "/learn/", "/news/", "/events/", "/dashboard/me/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertTrue(self.client.login(username="teacher", password="smartedu-demo-26"))
        teacher_page = self.client.get("/dashboard/teacher/")
        self.assertContains(teacher_page, "volcanoes")
