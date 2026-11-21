"""Related videos and websites from the open web, shown under every answer.

    related_links(query) -> {"query": str, "videos": [...], "sites": [...], "more": [...]}

Providers (each is optional; the page still gets something without any key):
    Videos : YouTube Data API v3 (YOUTUBE_API_KEY)  ->  Brave video search (BRAVE_API_KEY)
    Sites  : Brave web search (BRAVE_API_KEY)  +  Wikipedia (no key needed)
    More   : plain search links (YouTube, Khan Academy, Wikipedia) that always work

All calls use SafeSearch "strict", short timeouts, and run in parallel. Results
are cached in WebLookup for WEB_LINKS_CACHE_HOURS so repeated questions cost nothing.
"""

from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import quote_plus, urlparse

import httpx
from django.conf import settings
from django.utils import timezone

from .models import WebLookup

log = logging.getLogger("ai_engine")

# Wikimedia rejects requests (403) whose User-Agent has no contact link.
USER_AGENT = "SmartEducationPortal/1.0 (https://github.com/Sparky1445; school project) python-httpx"
TIMEOUT = 6.0
MAX_VIDEOS = 4
MAX_SITES = 5
BLOCKED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}  # videos have their own row


def _cfg(name: str, default=""):
    return getattr(settings, "WEB_LINKS", {}).get(name, default)


def normalise_query(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s-]", " ", text.lower()).split())[:200]


def _host(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _clean(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text or "")).split())


# ---------------------------------------------------------------------------
# Providers. Each takes (client, query) and returns a list of dicts.
# ---------------------------------------------------------------------------
def youtube_videos(client: httpx.Client, query: str) -> list[dict]:
    key = _cfg("YOUTUBE_API_KEY")
    if not key:
        return []
    r = client.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet", "q": query, "type": "video", "maxResults": MAX_VIDEOS,
            "safeSearch": "strict", "videoEmbeddable": "true", "relevanceLanguage": "en",
            "regionCode": "IN", "key": key,
        },
    )
    r.raise_for_status()
    videos = []
    for item in r.json().get("items", []):
        vid = item.get("id", {}).get("videoId")
        sn = item.get("snippet", {})
        if not vid:
            continue
        videos.append(
            {
                "title": _clean(sn.get("title")),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "channel": _clean(sn.get("channelTitle")),
                "thumbnail": (sn.get("thumbnails", {}).get("medium") or {}).get("url", ""),
                "site": "YouTube",
            }
        )
    return videos


def brave_videos(client: httpx.Client, query: str) -> list[dict]:
    key = _cfg("BRAVE_API_KEY")
    if not key:
        return []
    r = client.get(
        "https://api.search.brave.com/res/v1/videos/search",
        params={"q": query, "count": MAX_VIDEOS, "safesearch": "strict"},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    r.raise_for_status()
    videos = []
    for item in r.json().get("results", []):
        video = item.get("video") or {}
        videos.append(
            {
                "title": _clean(item.get("title")),
                "url": item.get("url", ""),
                "channel": _clean(video.get("creator") or video.get("publisher") or ""),
                "thumbnail": (item.get("thumbnail") or {}).get("src", ""),
                "site": (item.get("meta_url") or {}).get("hostname", "") or _host(item.get("url", "")),
            }
        )
    return [v for v in videos if v["url"]]


def brave_sites(client: httpx.Client, query: str) -> list[dict]:
    key = _cfg("BRAVE_API_KEY")
    if not key:
        return []
    r = client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 8, "safesearch": "strict", "result_filter": "web"},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    r.raise_for_status()
    return [
        {"title": _clean(i.get("title")), "url": i.get("url", ""), "snippet": _clean(i.get("description")), "site": _host(i.get("url", ""))}
        for i in (r.json().get("web") or {}).get("results", [])
        if i.get("url")
    ]


def wikipedia_sites(client: httpx.Client, query: str) -> list[dict]:
    r = client.get(
        "https://en.wikipedia.org/w/api.php",
        headers={"User-Agent": USER_AGENT, "Api-User-Agent": USER_AGENT},
        params={"action": "query", "list": "search", "srsearch": query, "srlimit": 3, "format": "json", "utf8": 1},
    )
    r.raise_for_status()
    return [
        {
            "title": hit["title"],
            "url": "https://en.wikipedia.org/wiki/" + quote_plus(hit["title"].replace(" ", "_"), safe="_()"),
            "snippet": _clean(hit.get("snippet")) + "…",
            "site": "wikipedia.org",
        }
        for hit in r.json().get("query", {}).get("search", [])
    ]


def search_links(query: str) -> list[dict]:
    q = quote_plus(query)
    return [
        {"title": "Videos on YouTube", "url": f"https://www.youtube.com/results?search_query={q}", "site": "youtube.com"},
        {"title": "Lessons on Khan Academy", "url": f"https://www.khanacademy.org/search?page_search_query={q}", "site": "khanacademy.org"},
        {"title": "Articles on Wikipedia", "url": f"https://en.wikipedia.org/w/index.php?search={q}", "site": "wikipedia.org"},
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def _safe(fn, client, query) -> list[dict]:
    try:
        return fn(client, query)
    except Exception as exc:  # noqa: BLE001 - one failing provider must not break the page
        # Never log the exception text: provider URLs carry the API key.
        status = getattr(getattr(exc, "response", None), "status_code", "")
        log.warning("web links: %s failed for %r (%s %s)", fn.__name__, query, type(exc).__name__, status)
        return []


def fetch_links(query: str, client: httpx.Client | None = None) -> dict:
    """Ask every configured provider at once and merge the results."""
    if _cfg("OFFLINE", False) and client is None:  # tests and offline demos: no network calls
        return {"query": query, "videos": [], "sites": [], "more": search_links(query)}
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {fn.__name__: pool.submit(_safe, fn, client, query) for fn in (youtube_videos, brave_videos, brave_sites, wikipedia_sites)}
            res = {name: job.result() for name, job in jobs.items()}
    finally:
        if own:
            client.close()

    videos = (res["youtube_videos"] or res["brave_videos"])[:MAX_VIDEOS]
    sites, seen = [], set()
    for site in res["brave_sites"] + res["wikipedia_sites"]:
        host = site["site"]
        if host in BLOCKED_HOSTS or site["url"] in seen:
            continue
        seen.add(site["url"])
        sites.append(site)
    return {"query": query, "videos": videos, "sites": sites[:MAX_SITES], "more": search_links(query)}


def related_links(query: str) -> dict:
    """Cached wrapper: the same topic is looked up at most once per cache period."""
    query = normalise_query(query)
    if not query:
        return {"query": "", "videos": [], "sites": [], "more": []}
    hours = int(_cfg("CACHE_HOURS", 24))
    fresh_after = timezone.now() - timedelta(hours=hours)
    cached = WebLookup.objects.filter(query=query, fetched_at__gte=fresh_after).first()
    if cached:
        return cached.results
    results = fetch_links(query)
    if results["videos"] or results["sites"]:  # never cache a total outage
        WebLookup.objects.update_or_create(query=query, defaults={"results": results, "fetched_at": timezone.now()})
    return results
