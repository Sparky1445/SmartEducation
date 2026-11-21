"""Ask the Repository: ingestion, search, the three-agent pipeline and the page. Offline (MOCK)."""

import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_engine import services
from ai_engine.ask_pipeline import FALLBACK_ANSWER, parse_score
from ai_engine.ingest import UnsupportedFile, chunk_pages, extract_pages
from ai_engine.models import AgentRun, DocumentChunk
from ai_engine.retrieval import search, tokenize

from .models import ChatQuery

MOCK = {
    "PROVIDER": "MOCK", "GITHUB_TOKEN": "", "GITHUB_MODEL": "x", "AZURE_ENDPOINT": "",
    "AZURE_KEY": "", "AZURE_MODEL": "x", "AZURE_API_VERSION": "2024-10-21", "TIMEOUT_SECONDS": 5,
}

WATER_CYCLE = """The water cycle describes how water moves between the land, the oceans and the atmosphere.

Evaporation happens when the sun heats water in oceans, rivers and lakes and turns it into water vapour.
The water vapour rises into the atmosphere where it cools down.

Condensation is the process in which cooled water vapour turns back into tiny droplets that form clouds.
When the droplets in clouds grow heavy they fall back to the ground as precipitation such as rain, snow or hail.

Collection is the stage where rain water gathers in rivers, lakes, oceans and under the ground, and the cycle starts again."""

PHOTOSYNTHESIS = """Photosynthesis is the process by which green plants make their own food using sunlight.

Plants take in carbon dioxide from the air through tiny pores called stomata and absorb water through their roots.
Chlorophyll in the leaves captures energy from sunlight and uses it to turn carbon dioxide and water into glucose.
Oxygen is released into the air as a by-product of photosynthesis."""


def make_source(name: str, text: str) -> Group:
    """Any model works as a source; Group stands in for Suhaib's Resource in tests."""
    group = Group.objects.create(name=name)
    services.index_source(group, text=text)
    return group


class IngestTests(TestCase):
    def test_chunks_respect_size_and_keep_locators(self):
        pages = [("p. 1", "word " * 300), ("p. 2", "short page"), ("p. 3", "other " * 50)]
        chunks = chunk_pages(pages)
        self.assertTrue(all(len(text.split()) <= 120 for _, text in chunks))
        self.assertEqual(chunks[0][0], "p. 1")
        self.assertIn("p. 2", {loc for loc, _ in chunks})

    def test_index_replaces_old_chunks(self):
        g = make_source("Water cycle", WATER_CYCLE)
        first = DocumentChunk.objects.count()
        services.index_source(g, text=WATER_CYCLE)
        self.assertEqual(DocumentChunk.objects.count(), first)
        services.remove_source(g)
        self.assertFalse(DocumentChunk.objects.exists())

    def test_text_file_and_unsupported_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "notes.md"
            md.write_text(WATER_CYCLE, encoding="utf-8")
            self.assertEqual(len(extract_pages(md)), 4)
            with self.assertRaises(UnsupportedFile):
                extract_pages(Path(tmp) / "movie.mkv")

    def test_management_command(self):
        g = Group.objects.create(name="Cmd")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.txt"
            f.write_text(PHOTOSYNTHESIS, encoding="utf-8")
            call_command("index_source", "auth.Group", str(g.pk), str(f), stdout=StringIO())
        self.assertTrue(DocumentChunk.objects.filter(object_id=g.pk).exists())


class SearchTests(TestCase):
    def test_tokenizer_drops_stopwords_and_stems(self):
        self.assertEqual(tokenize("What are the clouds raining?"), ["cloud", "rain"])

    def test_finds_the_right_source(self):
        make_source("Water cycle", WATER_CYCLE)
        make_source("Photosynthesis", PHOTOSYNTHESIS)
        hits = search("How do plants use sunlight and chlorophyll?")
        self.assertTrue(hits)
        self.assertEqual(hits[0].chunk.source.name, "Photosynthesis")

    def test_nothing_for_unrelated_question(self):
        make_source("Water cycle", WATER_CYCLE)
        self.assertEqual(search("Who won the cricket world cup?"), [])


@override_settings(AI_ENGINE=MOCK, ASK_TRUST_THRESHOLD=55)
class PipelineTests(TestCase):
    def setUp(self):
        make_source("Water cycle", WATER_CYCLE)
        make_source("Photosynthesis", PHOTOSYNTHESIS)

    def test_grounded_answer_with_citations(self):
        result = services.ask("What is condensation in the water cycle?")
        self.assertTrue(result["in_repository"])
        self.assertIn("droplets", result["answer"])
        self.assertRegex(result["answer"], r"\[\d\]")
        self.assertGreaterEqual(result["trust_score"], 55)
        self.assertEqual(result["citations"][0]["title"], "Water cycle")
        run = AgentRun.objects.get(pk=result["run_id"])
        self.assertEqual([s["agent"] for s in run.trace], ["Retriever", "Search", "Answerer", "Verifier"])

    def test_fallback_when_not_in_repository(self):
        result = services.ask("Who won the cricket world cup in 2011?")
        self.assertFalse(result["in_repository"])
        self.assertEqual(result["answer"], FALLBACK_ANSWER)
        self.assertEqual(result["citations"], [])

    def test_low_trust_is_rejected(self):
        with self.settings(ASK_TRUST_THRESHOLD=101):
            result = services.ask("What is condensation in the water cycle?")
        self.assertFalse(result["in_repository"])

    def test_parse_score(self):
        self.assertEqual(parse_score('{"score": 87, "reason": "ok"}'), (87, "ok"))
        self.assertEqual(parse_score("Score: 140")[0], 100)
        self.assertEqual(parse_score("no idea")[0], 0)


@override_settings(AI_ENGINE=MOCK)
class AskPageTests(TestCase):
    def setUp(self):
        make_source("Water cycle", WATER_CYCLE)

    def test_page_renders_without_engine_details(self):
        response = self.client.get(reverse("ask:home"))
        self.assertEqual(response.status_code, 200)
        for word in ("agent", "Retriever", "Verifier", "MOCK", "Semantic Kernel"):
            self.assertNotContains(response, word)

    def test_ask_saves_and_redirects_to_answer(self):
        response = self.client.post(reverse("ask:home"), {"question": "What is evaporation?"})
        query = ChatQuery.objects.get()
        self.assertRedirects(response, f"{reverse('ask:home')}?q={query.pk}#answer", fetch_redirect_response=False)
        page = self.client.get(f"{reverse('ask:home')}?q={query.pk}")
        self.assertContains(page, "Source match")
        self.assertContains(page, 'href="#src-1"')
        self.assertNotContains(page, "Verifier")
        self.assertEqual(self.client.session["ask_history"], [query.pk])

    def test_invalid_question(self):
        response = self.client.post(reverse("ask:home"), {"question": "hi"})
        self.assertContains(response, "at least two words")
        self.assertFalse(ChatQuery.objects.exists())

    def test_other_visitors_cannot_open_my_answer(self):
        self.client.post(reverse("ask:home"), {"question": "What is evaporation?"})
        query = ChatQuery.objects.get()
        stranger = self.client_class()
        page = stranger.get(f"{reverse('ask:home')}?q={query.pk}")
        self.assertNotContains(page, query.answer[:30])

    def test_feedback_and_clear_history(self):
        self.client.post(reverse("ask:home"), {"question": "What is evaporation?"})
        query = ChatQuery.objects.get()
        self.client.post(reverse("ask:feedback", args=[query.pk]), {"helpful": "yes"})
        query.refresh_from_db()
        self.assertTrue(query.helpful)
        self.client.post(reverse("ask:clear_history"))
        self.assertNotIn("ask_history", self.client.session)

    def test_csrf_enforced(self):
        client = self.client_class(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("ask:home"), {"question": "What is evaporation?"}).status_code, 403)

    def test_get_only_for_clear(self):
        self.assertEqual(self.client.get(reverse("ask:clear_history")).status_code, 405)
