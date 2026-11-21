"""Related videos and websites: providers are tested against fake HTTP responses, never the real web."""

import httpx
from django.test import TestCase, override_settings

from . import services, web_links
from .models import WebLookup

YOUTUBE = {"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "The Water Cycle &amp; You", "channelTitle": "Science Kids", "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"}}}}]}
BRAVE_WEB = {"web": {"results": [
    {"title": "Water cycle | NOAA", "url": "https://www.noaa.gov/education/water-cycle", "description": "How <strong>water</strong> moves."},
    {"title": "A video", "url": "https://www.youtube.com/watch?v=zzz", "description": "dup"},
]}}
WIKI = {"query": {"search": [{"title": "Water cycle", "snippet": "The <span>water cycle</span> describes"}]}}


def fake_web(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "www.googleapis.com":
        assert request.url.params["safeSearch"] == "strict"
        return httpx.Response(200, json=YOUTUBE)
    if host == "api.search.brave.com":
        assert request.url.params["safesearch"] == "strict"
        if request.url.path.endswith("/web/search"):
            return httpx.Response(200, json=BRAVE_WEB)
        return httpx.Response(200, json={"results": []})
    if host == "en.wikipedia.org":
        return httpx.Response(200, json=WIKI)
    return httpx.Response(404)


KEYS = {"YOUTUBE_API_KEY": "yt", "BRAVE_API_KEY": "br", "CACHE_HOURS": 24, "OFFLINE": False}


@override_settings(WEB_LINKS=KEYS)
class ProviderTests(TestCase):
    def http(self, handler=fake_web):
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_merges_videos_and_sites(self):
        links = web_links.fetch_links("water cycle", client=self.http())
        self.assertEqual(links["videos"][0]["title"], "The Water Cycle & You")
        self.assertEqual(links["videos"][0]["url"], "https://www.youtube.com/watch?v=abc123")
        hosts = [s["site"] for s in links["sites"]]
        self.assertEqual(hosts, ["noaa.gov", "wikipedia.org"])  # YouTube page filtered out of websites
        self.assertEqual(links["sites"][0]["snippet"], "How water moves.")
        self.assertEqual(len(links["more"]), 3)

    def test_one_failing_provider_does_not_break_the_rest(self):
        def flaky(request):
            if request.url.host == "www.googleapis.com":
                return httpx.Response(500)
            return fake_web(request)

        links = web_links.fetch_links("water cycle", client=self.http(flaky))
        self.assertEqual(links["videos"], [])
        self.assertTrue(links["sites"])

    def test_without_keys_only_wikipedia_is_called(self):
        called = []

        def record(request):
            called.append(request.url.host)
            return fake_web(request)

        with self.settings(WEB_LINKS={**KEYS, "YOUTUBE_API_KEY": "", "BRAVE_API_KEY": ""}):
            links = web_links.fetch_links("water cycle", client=self.http(record))
        self.assertEqual(called, ["en.wikipedia.org"])
        self.assertEqual(links["sites"][0]["site"], "wikipedia.org")


@override_settings(WEB_LINKS={**KEYS, "OFFLINE": True})
class ServiceTests(TestCase):
    def test_offline_gives_search_links_only(self):
        links = services.related_links("What is the Water-Cycle?")
        self.assertEqual(links["query"], "what is the water-cycle")
        self.assertEqual(links["videos"], [])
        self.assertIn("youtube.com/results", links["more"][0]["url"])
        self.assertFalse(WebLookup.objects.exists())  # nothing useful, nothing cached

    def test_cache_is_used(self):
        WebLookup.objects.create(query="photosynthesis", results={"query": "photosynthesis", "videos": [{"title": "cached"}], "sites": [], "more": []}, fetched_at=__import__("django.utils.timezone", fromlist=["now"]).now())
        self.assertEqual(services.related_links("Photosynthesis")["videos"][0]["title"], "cached")
