"""The agent roster and a factory that turns a spec into a Semantic Kernel agent.

Every agent the project will have is listed here from day one, with the
module that brings it to life. The console page shows this roster, so the
viva panel can see the whole design and how far it has been built.
"""

from __future__ import annotations

from dataclasses import dataclass

from semantic_kernel.agents import ChatCompletionAgent

from .llm import get_chat_service


@dataclass(frozen=True)
class AgentSpec:
    name: str
    pipeline: str  # "core", "ask" or "outreach"
    duty: str
    instructions: str
    module: int  # the build module that implements it

    @property
    def ready(self) -> bool:
        return self.module <= CURRENT_MODULE


CURRENT_MODULE = 3

ROSTER: tuple[AgentSpec, ...] = (
    AgentSpec(
        "Librarian", "core", "Health check: proves the kernel, provider and agent loop work.",
        "ROLE: Librarian.\nYou are the Smart Education librarian. Reply in two or three plain sentences. "
        "Confirm you received the message and say what you could help with in the knowledge repository.",
        1,
    ),
    AgentSpec("Ingestor", "core", "Parses uploads, chunks and embeds them, auto-tags subject and level.", "ROLE: Ingestor.", 4),
    AgentSpec(
        "Retriever", "ask", "Turns a student's question into a search query for the repository.",
        "ROLE: Retriever.\nYou turn a student's question into a short keyword search query for a school "
        "knowledge repository. Keep subject terms, drop filler words, add one or two close synonyms. "
        "Reply with the query only: 3 to 10 words, no punctuation, no explanation.",
        2,
    ),
    AgentSpec(
        "Answerer", "ask", "Writes the answer from retrieved chunks only, with citations.",
        "ROLE: Answerer.\nYou answer a student's question using ONLY the numbered SOURCES you are given. "
        "Write 2 to 5 clear sentences for a school student. After each fact put its source number in "
        "square brackets, like [1] or [2]. Never use outside knowledge. If the sources do not answer the "
        "question, reply with exactly: NOT_IN_SOURCES",
        2,
    ),
    AgentSpec(
        "Verifier", "ask", "Scores how well the answer matches its sources (Trust Score).",
        "ROLE: Verifier.\nYou check an ANSWER against its SOURCES. Score from 0 to 100 how fully every "
        "statement in the answer is supported by the sources (100 = every claim is stated in the sources, "
        "0 = none are). Reply with JSON only, no code fence: {\"score\": <int>, \"reason\": \"<one sentence>\"}",
        2,
    ),
    AgentSpec(
        "Summariser", "outreach", "Key points of a resource.",
        "ROLE: Summariser.\nYou write study notes from a school lesson (the SOURCE). Use only facts in the "
        "source. Reply with JSON only, no code fence: "
        '{"title": "<short lesson title>", "points": ["<5 key points, one sentence each>"]}',
        3,
    ),
    AgentSpec(
        "Quizmaster", "outreach", "Quiz and flashcards.",
        "ROLE: Quizmaster.\nYou make revision material from a school lesson (the SOURCE), using only its facts. "
        "Reply with JSON only, no code fence: "
        '{"questions": [{"q": "<question>", "options": ["<4 options>"], "answer": <index 0-3>, '
        '"why": "<one sentence from the source>"}], "flashcards": [{"front": "<term>", "back": "<meaning>"}]} '
        "Write 5 questions and 5 flashcards.",
        3,
    ),
    AgentSpec(
        "Columnist", "outreach", "Blog or news article for the media portal.",
        "ROLE: Columnist.\nYou write a short, friendly article for a school's public website about a lesson "
        "(the SOURCE), for parents and students. 180 to 260 words, only facts from the source. Reply with JSON "
        'only, no code fence: {"headline": "<max 10 words>", "standfirst": "<one sentence>", '
        '"body": ["<3 or 4 paragraphs>"]}',
        3,
    ),
    AgentSpec(
        "Herald", "outreach", "Social posts and a poster brief.",
        "ROLE: Herald.\nYou promote a school lesson (the SOURCE) on social media. Use only its facts. Reply "
        'with JSON only, no code fence: {"posts": [{"platform": "Instagram", "text": "<max 60 words, 3 hashtags>"}, '
        '{"platform": "WhatsApp", "text": "<max 50 words, for parents>"}, {"platform": "X", "text": "<max 240 '
        'characters>"}], "poster": {"headline": "<max 6 words>", "subline": "<max 14 words>", '
        '"call_to_action": "<max 6 words>"}}',
        3,
    ),
    AgentSpec(
        "Translator", "outreach", "Hindi, Marathi and Konkani versions.",
        "ROLE: Translator.\nRead the school lesson (the SOURCE) and write a 3 to 4 sentence summary of it in "
        "Hindi, in Marathi, and in Konkani (Devanagari script). Simple words for school students; keep "
        'scientific terms accurate. Reply with JSON only, no code fence: {"hi": "<Hindi>", "mr": "<Marathi>", '
        '"kok": "<Konkani>"}',
        3,
    ),
    AgentSpec(
        "Editor", "outreach", "Fan-in: merges the kit and checks it against the source.",
        "ROLE: Editor.\nYou check a draft outreach kit (DRAFTS) against the lesson it was made from (SOURCE). "
        "For each draft decide 'ok' if every fact is supported by the source and the format is right, or 'check' "
        "if a teacher must look at it. Reply with JSON only, no code fence: "
        '{"verdicts": {"summary": "ok|check", "quiz": "ok|check", "article": "ok|check", "social": "ok|check", '
        '"translation": "ok|check"}, "notes": "<at most 3 short sentences for the teacher>"}',
        3,
    ),
)

_BY_NAME = {spec.name: spec for spec in ROSTER}


def spec(name: str) -> AgentSpec:
    return _BY_NAME[name]


def build_agent(name: str, service=None) -> ChatCompletionAgent:
    """Create a Semantic Kernel ChatCompletionAgent for a roster entry."""
    s = spec(name)
    return ChatCompletionAgent(
        name=s.name,
        description=s.duty,
        instructions=s.instructions,
        service=service or get_chat_service(),
    )
