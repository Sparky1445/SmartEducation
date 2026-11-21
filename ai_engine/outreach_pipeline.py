"""Outreach Studio: fan-out / fan-in with Semantic Kernel's ConcurrentOrchestration.

    lesson text --fan-out--> Summariser | Quizmaster | Columnist | Herald | Translator   (in parallel)
                --fan-in---> Editor (checks every draft against the source)

Returns plain data; outreach_studio stores it as a kit for teacher review.
Nothing here is ever shown on the site.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from semantic_kernel.agents import ConcurrentOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatHistory

from .agents import build_agent
from .llm import get_chat_service, mock_responder
from .models import AgentRun, DocumentChunk
from .retrieval import tokenize
from .runner import EventLoop, tracked_run

FAN_OUT = ("Summariser", "Quizmaster", "Columnist", "Herald", "Translator")
KIND_OF = {"Summariser": "summary", "Quizmaster": "quiz", "Columnist": "article", "Herald": "social", "Translator": "translation"}
SOURCE_WORD_LIMIT = 1800
ORCHESTRATION_TIMEOUT = 240  # seconds


class NoSourceText(ValueError):
    pass


@dataclass
class KitDraft:
    drafts: dict[str, dict] = field(default_factory=dict)  # kind -> content
    verdicts: dict[str, str] = field(default_factory=dict)  # kind -> "ok" | "check"
    notes: str = ""
    run_id: int | None = None


# ---------------------------------------------------------------------------
# Source text and JSON helpers
# ---------------------------------------------------------------------------
def source_text(obj) -> str:
    ct = ContentType.objects.get_for_model(obj)
    words: list[str] = []
    for text in DocumentChunk.objects.filter(content_type=ct, object_id=obj.pk).values_list("text", flat=True):
        words.extend(text.split())
        if len(words) >= SOURCE_WORD_LIMIT:
            break
    if not words:
        raise NoSourceText("This resource has no readable text yet. Upload a PDF, PPTX, TXT or MD file.")
    # Overlapping chunks repeat ~30 words; harmless for the model, trimmed by the limit.
    return " ".join(words[:SOURCE_WORD_LIMIT])


def task_message(title: str, text: str) -> str:
    return f"LESSON: {title}\n\nSOURCE:\n{text}"


def parse_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Normalisers: make every draft safe to render, whatever the model returned
# ---------------------------------------------------------------------------
def _strs(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def normalise(kind: str, data: dict | None) -> tuple[dict, bool]:
    """Returns (content, ok). ok=False means the draft is incomplete and needs a teacher."""
    data = data or {}
    if kind == "summary":
        content = {"title": str(data.get("title", "")).strip(), "points": _strs(data.get("points"), 8)}
        return content, bool(content["points"])
    if kind == "quiz":
        questions = []
        for q in data.get("questions", []) if isinstance(data.get("questions"), list) else []:
            options = _strs(q.get("options") if isinstance(q, dict) else None, 4)
            try:
                answer = int(q.get("answer", -1))
            except (TypeError, ValueError):
                answer = -1
            if isinstance(q, dict) and q.get("q") and len(options) >= 2 and 0 <= answer < len(options):
                questions.append({"q": str(q["q"]).strip(), "options": options, "answer": answer, "why": str(q.get("why", "")).strip()})
        cards = [
            {"front": str(c.get("front", "")).strip(), "back": str(c.get("back", "")).strip()}
            for c in (data.get("flashcards") or [])
            if isinstance(c, dict) and c.get("front") and c.get("back")
        ][:8]
        return {"questions": questions[:8], "flashcards": cards}, bool(questions)
    if kind == "article":
        content = {
            "headline": str(data.get("headline", "")).strip(),
            "standfirst": str(data.get("standfirst", "")).strip(),
            "body": _strs(data.get("body"), 6),
        }
        return content, bool(content["headline"] and content["body"])
    if kind == "social":
        posts = [
            {"platform": str(p.get("platform", "")).strip() or "Post", "text": str(p.get("text", "")).strip()}
            for p in (data.get("posts") or [])
            if isinstance(p, dict) and p.get("text")
        ][:4]
        poster = data.get("poster") if isinstance(data.get("poster"), dict) else {}
        poster = {k: str(poster.get(k, "")).strip() for k in ("headline", "subline", "call_to_action")}
        return {"posts": posts, "poster": poster}, bool(posts)
    if kind == "translation":
        content = {lang: str(data.get(lang, "")).strip() for lang in ("hi", "mr", "kok")}
        return content, all(content.values())
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# Mock brain (offline demos and tests): extractive, deterministic
# ---------------------------------------------------------------------------
def _lesson(user_text: str) -> tuple[str, list[str]]:
    title = user_text.split("LESSON:", 1)[-1].split("\n", 1)[0].strip() if "LESSON:" in user_text else "Lesson"
    body = user_text.split("SOURCE:", 1)[-1].split("DRAFTS:", 1)[0]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(body.split())) if len(s.split()) >= 6]
    return title, list(dict.fromkeys(sentences))


@mock_responder("Summariser")
def _mock_summary(user_text: str, history: ChatHistory) -> str:
    title, sentences = _lesson(user_text)
    return json.dumps({"title": title, "points": sentences[:5]})


@mock_responder("Quizmaster")
def _mock_quiz(user_text: str, history: ChatHistory) -> str:
    _, sentences = _lesson(user_text)
    vocab = sorted({w for s in sentences for w in re.findall(r"[A-Za-z]{6,}", s)}, key=str.lower)
    questions, cards = [], []
    for i, sentence in enumerate(sentences[:5]):
        words = re.findall(r"[A-Za-z]{6,}", sentence)
        if not words:
            continue
        key = max(words, key=len)
        distractors = [w for w in vocab if w.lower() != key.lower()][i : i + 3] or ["energy", "matter", "motion"]
        options = distractors[:3]
        answer = i % (len(options) + 1)
        options.insert(answer, key)
        questions.append({"q": "Fill in the blank: " + sentence.replace(key, "_____", 1), "options": options, "answer": answer, "why": sentence})
        match = re.match(r"(.{3,60}?) (?:is|are|means|describes) (.+)", sentence)
        cards.append({"front": match.group(1) if match else key, "back": match.group(2) if match else sentence})
    return json.dumps({"questions": questions, "flashcards": cards})


@mock_responder("Columnist")
def _mock_article(user_text: str, history: ChatHistory) -> str:
    title, s = _lesson(user_text)
    body = [" ".join(s[0:2]), " ".join(s[2:4]), " ".join(s[4:7])]
    return json.dumps({"headline": f"Inside the lesson: {title}", "standfirst": s[0] if s else title, "body": [p for p in body if p]})


@mock_responder("Herald")
def _mock_social(user_text: str, history: ChatHistory) -> str:
    title, s = _lesson(user_text)
    tag = "#" + re.sub(r"\W", "", title.title())[:24]
    first = s[0] if s else title
    return json.dumps(
        {
            "posts": [
                {"platform": "Instagram", "text": f"New in the library: {title}. {first} {tag} #SmartEducation #Learning"},
                {"platform": "WhatsApp", "text": f"Dear parents, this week's lesson is {title}. Ask your child: {first}"},
                {"platform": "X", "text": f"{title}: {first}"[:230] + f" {tag}"},
            ],
            "poster": {"headline": title[:40], "subline": first[:90], "call_to_action": "Read it on Smart Education"},
        }
    )


@mock_responder("Translator")
def _mock_translation(user_text: str, history: ChatHistory) -> str:
    _, s = _lesson(user_text)
    gist = " ".join(s[:2])
    return json.dumps(
        {
            "hi": f"(नमूना — लाइव मॉडल से असली अनुवाद मिलेगा) {gist}",
            "mr": f"(नमुना — लाइव्ह मॉडेलवर खरे भाषांतर मिळेल) {gist}",
            "kok": f"(नमुनो — लायव्ह मॉडेलान खरो अणकार मेळटलो) {gist}",
        }
    )


@mock_responder("Editor")
def _mock_editor(user_text: str, history: ChatHistory) -> str:
    drafts = parse_json(user_text.split("DRAFTS:", 1)[-1]) or {}
    verdicts = {kind: ("ok" if drafts.get(kind) else "check") for kind in KIND_OF.values()}
    flagged = [k for k, v in verdicts.items() if v == "check"]
    notes = "Every draft uses facts from the lesson." if not flagged else f"Please review: {', '.join(flagged)}."
    return json.dumps({"verdicts": verdicts, "notes": notes})


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------
async def _fan_out(task: str, service) -> dict[str, str]:
    agents = [build_agent(name, service) for name in FAN_OUT]
    orchestration = ConcurrentOrchestration(members=agents)
    runtime = InProcessRuntime()
    runtime.start()
    try:
        result = await orchestration.invoke(task=task, runtime=runtime)
        messages = await result.get(timeout=ORCHESTRATION_TIMEOUT)
    finally:
        await runtime.stop_when_idle()
    return {m.name: str(m.content or "") for m in messages}


def build_kit(source_obj, title: str, user=None) -> KitDraft:
    text = source_text(source_obj)  # raises NoSourceText before any model call
    task = task_message(title, text)
    service = get_chat_service()
    draft = KitDraft()

    with tracked_run(AgentRun.Pipeline.OUTREACH, f"Outreach kit: {title}", user) as rec, EventLoop() as loop:
        # Fan-out: five agents work on the same lesson at the same time.
        replies = loop.run(_fan_out(task, service))
        all_ok = {}
        for name in FAN_OUT:
            kind = KIND_OF[name]
            raw = replies.get(name, "")
            content, ok = normalise(kind, parse_json(raw))
            draft.drafts[kind], all_ok[kind] = content, ok
            rec.step(name, kind, raw[:2000])

        # Fan-in: the Editor checks every draft against the source.
        editor = build_agent("Editor", service)
        message = f"SOURCE:\n{text}\n\nDRAFTS:\n{json.dumps(draft.drafts, ensure_ascii=False)[:12000]}"
        reply = loop.run(editor.get_response(messages=message))
        rec.add_tokens(reply.message.metadata.get("usage"))
        review = parse_json(str(reply.message.content)) or {}
        verdicts = review.get("verdicts") if isinstance(review.get("verdicts"), dict) else {}
        for kind, ok in all_ok.items():
            verdict = str(verdicts.get(kind, "check")).lower()
            draft.verdicts[kind] = "ok" if ok and verdict == "ok" else "check"
        draft.notes = str(review.get("notes", "")).strip()[:600]
        rec.step("Editor", "review", json.dumps({"verdicts": draft.verdicts, "notes": draft.notes}, ensure_ascii=False))
        rec.run.output = {"verdicts": draft.verdicts, "notes": draft.notes}
        draft.run_id = rec.run.pk
    return draft
