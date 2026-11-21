# Smart Education

A Django knowledge repository and outreach/media portal with an agentic AI engine (INT253, 2026–27).
Team: Atharwa (AI engine, `ask`, `outreach_studio`, `engagement`, `dashboard`, `repository`) · Suhaib (`accounts`, `media_portal`, `courses`).

## Run it (Windows)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_roles      # creates the "Teacher" group
python manage.py runserver
```

Open http://127.0.0.1:8000/ and http://127.0.0.1:8000/admin/.

The AI engine has no public pages and shows no agent activity on the site. Check it from the terminal; staff can see run records in the admin under *AI engine*:

```bash
python manage.py ai_ping "Hello Librarian"
python manage.py test ai_engine
```

`LLM_PROVIDER=MOCK` needs no key. For a live model set `GITHUB_MODELS` or `AZURE` and fill the
matching keys in `.env` (same names as PackPilot). A missing key falls back to MOCK.

## Design system

All pages extend `templates/base.html` and use `static/css/smartedu.css` ("Ledger": paper,
ink and one rust accent; Instrument Serif headings, IBM Plex Sans body, IBM Plex Mono labels).
Do not add Bootstrap or another framework; reuse the classes:

| Need | Class |
| --- | --- |
| Two-column page | `.split` > `.split__aside` + `.split__main` |
| Section title | `{% load ui %}{% section_head "Title" "meta" %}` or `.section-head` |
| Buttons | `.btn`, `.btn--primary` |
| Text input row | `.field` > `.field__row` > `.field-input` + `.btn` |
| Table | `.ledger` |
| Status label | `.tag`, `.tag--ok`, `.tag--err`, `.tag--live`, `.tag--solid` |
| Callout | `.note`, `.note--error` |

## AI engine contract

Portal code calls only `ai_engine/services.py`. Pages show results only (answers, quizzes, articles), never agents, runs or providers:

| Function | Returns | Live from |
| --- | --- | --- |
| `ping(message, user=None)` | `AgentRun` | Module 1 |
| `index_source(obj, path=None, text=None)` | number of chunks indexed | Module 2 |
| `remove_source(obj)` | `None` | Module 2 |
| `ask(question, user=None)` | `{answer, citations, trust_score, in_repository, run_id}` | Module 2 |
| `build_outreach_kit(resource, user=None)` | kit id (runs in the background) | Module 3 |
| `kit_status(kit_id)` | `queued / running / review / published / failed` | Module 3 |
| `published_kits(limit=6)` | newest published kits, for the homepage | Module 3 |
| `suggest_next_resources(user)` | list of resource ids | Module 4 |

Until a function goes live it returns sample data of the final shape.

## Ask the Repository (Module 2)

Open http://127.0.0.1:8000/ask/. Answers come only from indexed material and show their sources.

Suhaib: when a `Resource` is saved with a file, call

```python
from ai_engine import services
services.index_source(resource, path=resource.file.path)   # on save
services.remove_source(resource)                           # on delete
```

`resource.title` is used as the citation title and `resource.get_absolute_url()` as its link.
Supported files: PDF, PPTX, TXT, MD. Index one by hand with
`python manage.py index_source repository.Resource <id> <path-to-file>`.

## Outreach Studio and Learn (Module 3)

- `/studio/` (teachers): pick an indexed lesson, press **Make kit**. Study notes, a quiz with flashcards,
  an article, social posts with a poster, and Hindi/Marathi/Konkani summaries are written in parallel,
  checked against the lesson, and land in a review page. Edit, approve, publish.
- `/learn/` (public): published kits with key points, the article, a self-check quiz, flip cards and translations.
- Permissions: `outreach_studio.add_outreachkit` to use the studio, `outreach_studio.publish_outreachkit` to publish.
  Put both in a "Teacher" group.

## Related videos and websites (under every answer)

Every question on `/ask/` also gets related videos and websites from the open web, even when the
repository has no answer. Set either or both keys in `.env`:

| Key | Gives | Where to get it |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | YouTube videos (SafeSearch strict) | Google Cloud console → enable "YouTube Data API v3" → Credentials → API key |
| `BRAVE_API_KEY` | websites and videos | brave.com/search/api (free monthly credit) |

With no key you still get Wikipedia articles and search links to YouTube, Khan Academy and Wikipedia.
Results are cached per topic for 24 h (`WebLookup` in the admin). `python manage.py test` never calls the web.

## Engagement and dashboards (Module 4)

| URL | What |
| --- | --- |
| `/feedback/` | Feedback form (validation, honeypot, 3 messages/hour per visitor). `?topic=` prefills a lesson request |
| `/newsletter/` | Subscribe in English, Hindi, Marathi or Konkani; `/newsletter/unsubscribe/<token>/` to leave |
| Learn lesson pages | Star rating and a comment thread (`{% load engagement_tags %}{% rating_for obj %}{% comments_for obj %}`) |
| `/dashboard/` | Sends students to `/dashboard/me/` and teachers to `/dashboard/teacher/` |
| Footer "Dark mode", dashboard Preferences | Theme and preferred language, stored in cookies (`se_theme`, `se_lang`) |
| `/accounts/login/` | Temporary login page until Suhaib's `accounts` app takes over |

Suhaib: to allow comments and ratings on your models, add them to `ALLOWED_TARGETS` in
`engagement/views.py`, e.g. `("repository", "resource")`, then use the two template tags on the detail page.

## Repository (Module 5)

| URL | What |
| --- | --- |
| `/repository/` | Browse and search lessons (GET form: words, subject, class, type, sort), paginated |
| `/repository/subject/<slug>/`, `/repository/archive/<year>/` | By subject; by year (regex URL) |
| `/repository/<id>-<slug>/` | Lesson page: PDF viewer or YouTube player, download, tags, rating, discussion, bookmark |
| `/repository/upload/`, `/<id>/edit/`, `/<id>/delete/` | Teachers only (Teacher group) |
| `/repository/bookmarks/` | A student's saved lessons |

Uploading or editing a published lesson indexes it automatically (signals), so the Ask page can answer
from it and Outreach Studio can make a kit. PDF, PPTX, TXT and MD files are read; for videos and links
the title, description and tags are searchable. Drafts are hidden and not searchable.
Ten subjects are created by a migration; add more in the admin.
