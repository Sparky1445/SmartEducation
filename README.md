# Smart Education

A Django knowledge repository and outreach/media portal with an agentic AI engine (INT253, 2026–27).
Team: Atharwa (AI engine, `engagement`, `dashboard`) · Suhaib (`accounts`, `repository`, `media_portal`, `courses`).

## Run it (Windows)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
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
| `ask(question, user=None)` | `{answer, citations, trust_score, in_repository, run_id}` | Module 2 |
| `build_outreach_kit(resource_id)` | kit id | Module 3 |
| `kit_status(kit_id)` | `queued / running / review / published / failed` | Module 3 |
| `suggest_next_resources(user)` | list of resource ids | Module 4 |

Until a function goes live it returns sample data of the final shape.
# SmartEducation
