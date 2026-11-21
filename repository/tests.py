"""Repository: upload with validation, automatic indexing for Ask, browsing, search, bookmarks, permissions."""

import os
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_engine import services
from ai_engine.models import DocumentChunk
from ask.tests import MOCK, WATER_CYCLE

from .models import Bookmark, Resource, Subject

MEDIA = tempfile.mkdtemp()


def teacher():
    with open(os.devnull, "w") as devnull:
        call_command("setup_roles", stdout=devnull)
    user = User.objects.create_user("teacher", password="pass12345", first_name="Mrs. Naik")
    user.groups.add(Group.objects.get(name="Teacher"))
    return user


@override_settings(MEDIA_ROOT=MEDIA, WEB_LINKS={"OFFLINE": True}, AI_ENGINE=MOCK)
class UploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.science = Subject.objects.get(slug="science")  # created by the data migration
        teacher()
        self.client.login(username="teacher", password="pass12345")

    def upload(self, **extra):
        data = {
            "title": "The Water Cycle", "subject": self.science.pk, "grade": 7, "kind": "document",
            "description": "How water moves around the Earth.", "url": "", "status": "published",
            "tag_names": "Water cycle, evaporation, , EVAPORATION",
            "file": SimpleUploadedFile("Water Cycle Notes.md", WATER_CYCLE.encode(), content_type="text/markdown"),
        }
        data.update(extra)
        return self.client.post(reverse("repository:upload"), data)

    def test_upload_indexes_for_ask_and_tags_are_cleaned(self):
        response = self.upload()
        r = Resource.objects.get()
        self.assertRedirects(response, r.get_absolute_url())
        self.assertRegex(r.file.name, r"^resources/\d{4}/\d{2}/water-cycle-notes(_\w+)?\.md$")
        self.assertEqual(sorted(t.name for t in r.tags.all()), ["evaporation", "water cycle"])
        self.assertGreater(r.indexed_chunks, 0)
        result = services.ask("What is condensation in the water cycle?")
        self.assertTrue(result["in_repository"])
        self.assertEqual(result["citations"][0]["title"], "The Water Cycle")
        self.assertEqual(result["citations"][0]["url"], r.get_absolute_url())

    def test_rejects_wrong_type_and_missing_file(self):
        self.upload(file=SimpleUploadedFile("virus.exe", b"MZ"))
        self.upload(file="", title="No file")
        self.assertFalse(Resource.objects.exists())

    def test_video_link_is_searchable_by_description(self):
        self.upload(kind="video", file="", url="https://youtu.be/WgHmqv_-UbQ", title="Why we have seasons", description="Earth's tilted axis causes the seasons.")
        r = Resource.objects.get()
        self.assertEqual(r.youtube_id, "WgHmqv_-UbQ")
        self.assertTrue(DocumentChunk.objects.filter(object_id=r.pk).exists())
        self.assertContains(self.client.get(r.get_absolute_url()), "youtube-nocookie.com/embed/WgHmqv_-UbQ")

    def test_draft_is_hidden_and_not_searchable(self):
        self.upload(status="draft")
        r = Resource.objects.get()
        self.assertFalse(DocumentChunk.objects.exists())
        self.client.logout()
        self.assertEqual(self.client.get(r.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("repository:list")), "The Water Cycle")

    def test_delete_removes_index(self):
        self.upload()
        r = Resource.objects.get()
        self.client.post(reverse("repository:delete", args=[r.pk]))
        self.assertFalse(Resource.objects.exists())
        self.assertFalse(DocumentChunk.objects.exists())

    def test_students_cannot_upload(self):
        User.objects.create_user("stu", password="pass12345")
        self.client.login(username="stu", password="pass12345")
        self.assertEqual(self.client.get(reverse("repository:upload")).status_code, 403)


@override_settings(WEB_LINKS={"OFFLINE": True}, AI_ENGINE=MOCK)
class BrowseTests(TestCase):
    def setUp(self):
        sci, maths = Subject.objects.get(slug="science"), Subject.objects.get(slug="mathematics")
        self.a = Resource.objects.create(title="Photosynthesis", subject=sci, grade=9, kind="link", url="https://example.com/p", description="How plants make food from sunlight")
        self.b = Resource.objects.create(title="Fractions", subject=maths, grade=6, kind="link", url="https://example.com/f", description="Parts of a whole")

    def test_search_and_filters(self):
        url = reverse("repository:list")
        page = self.client.get(url, {"q": "plants sunlight"})
        self.assertContains(page, "Photosynthesis")
        self.assertNotContains(page, "Fractions")
        self.assertNotContains(self.client.get(url, {"grade": "9"}), "Fractions")
        self.assertContains(self.client.get(reverse("repository:subject", args=["mathematics"])), "Fractions")
        empty = self.client.get(url, {"q": "volcano"})
        self.assertContains(empty, "request a lesson on")

    def test_archive_regex_url(self):
        year = self.a.created_at.year
        self.assertContains(self.client.get(f"/repository/archive/{year}/"), "Photosynthesis")
        self.assertEqual(self.client.get("/repository/archive/1999/").status_code, 404)

    def test_views_counted_once_per_session(self):
        for _ in range(3):
            self.client.get(self.a.get_absolute_url())
        self.a.refresh_from_db()
        self.assertEqual(self.a.views, 1)

    def test_wrong_slug_redirects(self):
        self.assertRedirects(self.client.get(f"/repository/{self.a.pk}-old/"), self.a.get_absolute_url(), status_code=301)

    def test_bookmark_toggle_and_comments(self):
        User.objects.create_user("stu", password="pass12345")
        self.client.login(username="stu", password="pass12345")
        self.client.post(reverse("repository:bookmark", args=[self.a.pk]))
        self.assertTrue(Bookmark.objects.exists())
        self.assertContains(self.client.get(reverse("repository:bookmarks")), "Photosynthesis")
        self.assertContains(self.client.get(reverse("dashboard:student")), "Photosynthesis")
        self.client.post(reverse("repository:bookmark", args=[self.a.pk]))
        self.assertFalse(Bookmark.objects.exists())
        page = self.client.get(self.a.get_absolute_url())
        self.assertContains(page, "Discussion")
        self.assertContains(page, "Rate this lesson")
