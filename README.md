# Smart Education

A Django knowledge repository and outreach/media portal with an agentic AI engine (INT253, 2026–27).
Team: Atharwa (AI engine, `ask`, `outreach_studio`, `engagement`, `dashboard`, `repository`, `accounts`, `media_portal`, `courses`).

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

Open http://127.0.0.1:8000/ (home page) and http://127.0.0.1:8000/admin/.

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

## Accounts (Module 6)

| URL | What |
| --- | --- |
| `/accounts/signup/` | Students, parents and visitors sign up (teachers are added by the school, then put in the Teacher group) |
| `/accounts/login/` | Log in; "Keep me logged in" keeps the session for 2 weeks, otherwise it ends when the browser closes |
| `/accounts/profile/` | Name, email, class, school, preferred language |
| `/accounts/password_change/`, `/accounts/password_reset/` | Django's password views, styled. Reset emails print in the terminal unless `EMAIL_*` is set in `.env` |

Every user gets a `Profile` automatically (signal); a migration creates one for users that already existed.

## News, events and announcements (Module 7)

| URL | What |
| --- | --- |
| `/` | Home page: announcements, Ask box, lead story, news, upcoming events, new lessons, revision kits, newsletter |
| `/news/`, `/news/<year>/`, `/news/<year>/<slug>/` | News by section and year (regex URLs); drafts and scheduled stories stay hidden; teachers can preview |
| `/news/feed/` | RSS feed (`django.contrib.syndication`) |
| `/events/`, `/events/<id>-<slug>/`, `/events/<id>/calendar.ics` | Upcoming and past events; "Add to calendar" downloads an iCalendar file |

Teachers write news, events and announcements in the admin (the Teacher group can, after `setup_roles`).
In Outreach Studio, **Send article to News** turns a kit's approved article into a draft news story.
Announcements show as a banner on every page until they expire; visitors can hide one.

## Courses and quizzes (Module 8)

| URL | What |
| --- | --- |
| `/courses/?grade=7` | Subjects with a syllabus for a class (defaults to the student's class), with each student's progress |
| `/courses/class/<grade>/<subject>/` | Units and topics; a tick marks topics whose quiz the student has passed |
| `/courses/topic/<id>-<slug>/` | Learning objectives, linked lessons, quizzes, previous/next topic |
| `/courses/quiz/<id>/` | Scored quiz (a form built from the questions); results at `/courses/result/<id>/` with explanations |
| `/courses/progress/` | A student's best score per quiz |
| `/courses/quiz/<id>/report/` | Teachers: attempts, average score and the hardest questions |

Teachers add units and topics in the admin (Unit page has topics inline; link lessons to a topic there).
In Outreach Studio, **Make scored quiz** turns a kit's approved quiz into a scored quiz, optionally for a topic;
the Learn page then shows **Take the scored quiz**. Pass mark: 60 %.

## Demo data (Module 9)

```bash
python manage.py seed_demo              # lessons, syllabus, news, events, users, activity + one AI outreach kit
python manage.py seed_demo --skip-kits  # same, without any AI calls
```

Safe to run more than once. Demo logins, all with password `smartedu-demo-26`:

| Username | Role |
| --- | --- |
| `teacher` | Teacher group and staff: upload, Studio, news, quiz reports, admin |
| `student` | Class 7 student with quiz attempts, questions and a comment |
| `parent` | Parent, newsletter subscriber |

It adds 6 lessons (5 readable notes + 1 YouTube video, all searchable on Ask), 6 units with
12 topics, 2 scored quizzes, 4 news stories, 4 events, an announcement, questions for the gap radar, comments,
ratings and feedback. With an AI provider set, it also writes, approves and publishes an outreach kit
for "The water cycle".
