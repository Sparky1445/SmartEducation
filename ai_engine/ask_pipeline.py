"""Ask the Repository: a sequential pipeline of three Semantic Kernel agents.

    question -> Retriever (search query) -> BM25 search over DocumentChunks
             -> Answerer (answer with [n] citations, sources only)
             -> Verifier (0-100 support score) -> Trust Score

Nothing here is shown on the site: the portal only receives the final
answer, its citations and the trust score.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from django.conf import settings
from semantic_kernel.contents import ChatHistory

from .agents import build_agent
from .llm import get_chat_service, mock_responder, resolve_provider
from .models import AgentRun
from .retrieval import STOPWORDS, Hit, overlap_ratio, search, tokenize
from .runner import EventLoop, tracked_run

NOT_IN_SOURCES = "NOT_IN_SOURCES"
FALLBACK_ANSWER = (
    "I couldn't find this in the repository yet. Your question has been passed to the teachers "
    "so they can add material on it."
)


def trust_threshold() -> int:
    return int(getattr(settings, "ASK_TRUST_THRESHOLD", 55))


@dataclass
class AskResult:
    answer: str
    citations: list[dict] = field(default_factory=list)
    trust_score: int = 0
    in_repository: bool = False
    run_id: int | None = None
    search_query: str = ""
    answer_kind: str = "none"  # "repository" | "general" | "none"

    def as_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": self.citations,
            "trust_score": self.trust_score,
            "in_repository": self.in_repository,
            "run_id": self.run_id,
            "search_query": self.search_query,
            "answer_kind": self.answer_kind,
        }


# ---------------------------------------------------------------------------
# Prompt building and parsing
# ---------------------------------------------------------------------------
def source_title(hit: Hit) -> str:
    src = hit.chunk.source
    return str(getattr(src, "title", None) or src or f"Source {hit.chunk.object_id}")


def source_url(hit: Hit) -> str:
    src = hit.chunk.source
    getter = getattr(src, "get_absolute_url", None)
    return getter() if callable(getter) else ""


def sources_block(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{n}] ({source_title(h)}, {h.chunk.locator or 'n/a'})\n{h.chunk.text}" for n, h in enumerate(hits, start=1)
    )


def parse_sources_block(text: str) -> list[str]:
    """Inverse of sources_block: returns the text of each numbered source."""
    body = text.split("SOURCES:", 1)[-1]
    parts = re.split(r"^\[\d+\] \([^\n]*\)\n", body, flags=re.M)
    return [p.strip() for p in parts if p.strip()]


def parse_score(text: str) -> tuple[int, str]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return max(0, min(100, int(data.get("score", 0)))), str(data.get("reason", ""))
        except (ValueError, TypeError):
            pass
    number = re.search(r"\b(\d{1,3})\b", text)
    return (max(0, min(100, int(number.group(1)))) if number else 0), text.strip()[:200]


def cited_numbers(answer: str, total: int) -> list[int]:
    found = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 1 <= int(n) <= total})
    return found or list(range(1, total + 1))


# ---------------------------------------------------------------------------
# Mock brain for the three agents (offline demos and tests)
# ---------------------------------------------------------------------------
@mock_responder("Retriever")
def _mock_retriever(user_text: str, history: ChatHistory) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9']+", user_text) if len(w) > 2 and w.lower() not in STOPWORDS]
    return " ".join(dict.fromkeys(w.lower() for w in words))[:120] or user_text


@mock_responder("Answerer")
def _mock_answerer(user_text: str, history: ChatHistory) -> str:
    question = user_text.split("QUESTION:", 1)[-1].split("SOURCES:", 1)[0]
    q_terms = set(tokenize(question))
    sources = parse_sources_block(user_text)
    candidates = []
    for n, text in enumerate(sources, start=1):
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            overlap = len(q_terms & set(tokenize(sentence)))
            if overlap and len(sentence.split()) >= 5:
                candidates.append((overlap, -n, sentence.strip(), n))
    if not candidates:
        return NOT_IN_SOURCES
    candidates.sort(reverse=True)
    picked = []
    for _, _, sentence, n in candidates[:3]:
        sentence = sentence.rstrip(".") + f". [{n}]"
        if sentence not in picked:
            picked.append(sentence)
    return " ".join(picked)


@mock_responder("Verifier")
def _mock_verifier(user_text: str, history: ChatHistory) -> str:
    answer = user_text.split("ANSWER:", 1)[-1].split("SOURCES:", 1)[0]
    ratio = overlap_ratio(re.sub(r"\[\d+\]", "", answer), parse_sources_block(user_text))
    return json.dumps({"score": round(ratio * 100), "reason": "Share of answer terms found in the sources."})


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------
def _pipeline(question: str, rec, loop: EventLoop) -> AskResult:
    service = get_chat_service()
    retriever, answerer, verifier = (build_agent(n, service) for n in ("Retriever", "Answerer", "Verifier"))

    # 1. Retriever: question -> search query
    reply = loop.run(retriever.get_response(messages=question))
    rec.add_tokens(reply.message.metadata.get("usage"))
    query = str(reply.message.content).strip().strip('"')
    rec.step("Retriever", "query", query)

    hits = search(f"{question} {query}", k=4)
    rec.step("Search", "hits", ", ".join(f"{h.chunk} ({h.score})" for h in hits) or "none")
    if not hits:
        return AskResult(FALLBACK_ANSWER)

    # 2. Answerer: sources only, numbered citations
    block = sources_block(hits)
    reply = loop.run(answerer.get_response(messages=f"QUESTION: {question}\n\nSOURCES:\n{block}"))
    rec.add_tokens(reply.message.metadata.get("usage"))
    answer = str(reply.message.content).strip()
    rec.step("Answerer", "answer", answer)
    if NOT_IN_SOURCES in answer or not answer:
        return AskResult(FALLBACK_ANSWER)

    # 3. Verifier: how well is the answer supported?
    reply = loop.run(verifier.get_response(messages=f"ANSWER: {answer}\n\nSOURCES:\n{block}"))
    rec.add_tokens(reply.message.metadata.get("usage"))
    model_score, reason = parse_score(str(reply.message.content))
    lexical = round(overlap_ratio(re.sub(r"\[\d+\]", "", answer), [h.chunk.text for h in hits]) * 100)
    trust = model_score if resolve_provider().is_mock else round(0.6 * model_score + 0.4 * lexical)
    rec.step("Verifier", "score", f"model {model_score}, lexical {lexical}, trust {trust}: {reason}")

    if trust < trust_threshold():
        return AskResult(FALLBACK_ANSWER, trust_score=trust)

    citations = []
    for n in cited_numbers(answer, len(hits)):
        h = hits[n - 1]
        citations.append(
            {
                "n": n,
                "content_type": h.chunk.content_type.model,
                "object_id": h.chunk.object_id,
                "resource_id": h.chunk.object_id,
                "title": source_title(h),
                "url": source_url(h),
                "locator": h.chunk.locator,
                "excerpt": h.chunk.text[:220],
            }
        )
    return AskResult(answer, citations, trust, True, answer_kind="repository")


def general_fallback_enabled() -> bool:
    return bool(getattr(settings, "ASK_GENERAL_FALLBACK", True))


@mock_responder("Tutor")
def _mock_tutor(user_text: str, history: ChatHistory) -> str:
    return (
        f"Here is a short general answer to \u201c{user_text[:120]}\u201d. "
        "(Offline demo: connect an AI provider in .env for a real explanation.)"
    )


def _general_answer(question: str, rec, loop: EventLoop, service) -> str:
    """Step 2: the repository had nothing reliable, so the LLM answers from its own knowledge."""
    tutor = build_agent("Tutor", service)
    reply = loop.run(tutor.get_response(messages=question))
    rec.add_tokens(reply.message.metadata.get("usage"))
    text = str(reply.message.content).strip()
    rec.step("Tutor", "general", text)
    return text


def ask(question: str, user=None) -> AskResult:
    """1) RAG over the repository (Retriever -> search -> Answerer -> Verifier).
    2) If the repository has no reliable answer, the Tutor agent answers with the LLM,
       clearly marked as a general answer. The question still counts as a gap for teachers."""
    with tracked_run(AgentRun.Pipeline.ASK, question, user) as rec:
        with EventLoop() as loop:
            result = _pipeline(question, rec, loop)
            if not result.in_repository and general_fallback_enabled():
                try:
                    text = _general_answer(question, rec, loop, get_chat_service())
                except Exception:  # noqa: BLE001 - keep the polite fallback if the LLM is down
                    text = ""
                if text:
                    result.answer, result.answer_kind = text, "general"
        result.search_query = rec.run.trace[0]["text"] if rec.run.trace else question
        result.run_id = rec.run.pk
        rec.run.output = result.as_dict()
    return result
