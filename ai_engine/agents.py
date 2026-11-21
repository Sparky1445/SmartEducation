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


CURRENT_MODULE = 2

ROSTER: tuple[AgentSpec, ...] = (
    AgentSpec(
        "Librarian", "core", "Health check: proves the kernel, provider and agent loop work.",
        "ROLE: Librarian.\nYou are the Smart Education librarian. Reply in two or three plain sentences. "
        "Confirm you received the message and say what you could help with in the knowledge repository.",
        1,
    ),
    AgentSpec("Ingestor", "core", "Parses uploads, chunks and embeds them, auto-tags subject and level.", "ROLE: Ingestor.", 2),
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
    AgentSpec("Summariser", "outreach", "Key points of a resource.", "ROLE: Summariser.", 3),
    AgentSpec("Quizmaster", "outreach", "Quiz and flashcards.", "ROLE: Quizmaster.", 3),
    AgentSpec("Columnist", "outreach", "Blog or news article for the media portal.", "ROLE: Columnist.", 3),
    AgentSpec("Herald", "outreach", "Social posts and a poster brief.", "ROLE: Herald.", 3),
    AgentSpec("Translator", "outreach", "Hindi, Marathi and Konkani versions.", "ROLE: Translator.", 3),
    AgentSpec("Editor", "outreach", "Fan-in: merges the kit and checks it against the source.", "ROLE: Editor.", 3),
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
