"""LLM providers for Semantic Kernel.

One public entry point: ``get_chat_service()`` returns a Semantic Kernel chat
completion service for the configured provider.

Providers (``LLM_PROVIDER`` in .env, same names as PackPilot):
    MOCK           - offline, deterministic replies; no key, no network
    GITHUB_MODELS  - OpenAI-compatible endpoint, GITHUB_TOKEN as key
    AZURE          - Azure OpenAI / Foundry endpoint, AZURE_INFERENCE_KEY

A provider whose key is missing degrades to MOCK, so the site always boots.
The MOCK service is a real Semantic Kernel service: agents, threads and
orchestrations run exactly as they do live; only the "brain" is scripted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import AuthorRole, ChatHistory, ChatMessageContent, StreamingChatMessageContent

GITHUB_MODELS_URL = "https://models.github.ai/inference"
MOCK_MODEL = "mock-scholar-1"


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderInfo:
    requested: str
    active: str
    model: str
    fell_back: bool
    reason: str = ""

    @property
    def is_mock(self) -> bool:
        return self.active == "MOCK"


def resolve_provider() -> ProviderInfo:
    cfg = settings.AI_ENGINE
    requested = cfg["PROVIDER"]
    if requested == "GITHUB_MODELS":
        if cfg["GITHUB_TOKEN"]:
            return ProviderInfo(requested, "GITHUB_MODELS", cfg["GITHUB_MODEL"], False)
        return ProviderInfo(requested, "MOCK", MOCK_MODEL, True, "GITHUB_TOKEN is not set")
    if requested == "AZURE":
        if cfg["AZURE_KEY"] and cfg["AZURE_ENDPOINT"]:
            return ProviderInfo(requested, "AZURE", cfg["AZURE_MODEL"], False)
        return ProviderInfo(
            requested, "MOCK", MOCK_MODEL, True, "AZURE_INFERENCE_ENDPOINT or AZURE_INFERENCE_KEY is not set"
        )
    if requested != "MOCK":
        return ProviderInfo(requested, "MOCK", MOCK_MODEL, True, f"unknown provider '{requested}'")
    return ProviderInfo("MOCK", "MOCK", MOCK_MODEL, False)


# ---------------------------------------------------------------------------
# Mock brain
# ---------------------------------------------------------------------------
# Every agent's instructions start with "ROLE: <Name>." The mock reads that
# line and hands the conversation to the matching responder. Later modules
# register responders for their own agents with @mock_responder("Name").
MockResponder = Callable[[str, ChatHistory], str]
_RESPONDERS: dict[str, MockResponder] = {}


def mock_responder(role: str) -> Callable[[MockResponder], MockResponder]:
    def register(fn: MockResponder) -> MockResponder:
        _RESPONDERS[role.lower()] = fn
        return fn

    return register


def _role_of(history: ChatHistory) -> str:
    for msg in history.messages:
        if msg.role in (AuthorRole.SYSTEM, AuthorRole.DEVELOPER) and msg.content:
            first = msg.content.strip().splitlines()[0]
            if first.upper().startswith("ROLE:"):
                return first.split(":", 1)[1].strip().rstrip(".").lower()
    return ""


def _last_user_text(history: ChatHistory) -> str:
    for msg in reversed(history.messages):
        if msg.role == AuthorRole.USER and msg.content:
            return msg.content.strip()
    return ""


@mock_responder("Librarian")
def _librarian(user_text: str, history: ChatHistory) -> str:
    words = len(user_text.split())
    return (
        f"Kernel online. I read your message ({words} words) and I am ready to search the repository. "
        f"You wrote: “{user_text[:160]}”. "
        "In MOCK mode my replies are scripted; switch LLM_PROVIDER to GITHUB_MODELS or AZURE for a live model."
    )


class MockChatCompletion(ChatCompletionClientBase):
    """A Semantic Kernel chat service that answers from the mock brain."""

    def __init__(self, service_id: str = "mock") -> None:
        super().__init__(ai_model_id=MOCK_MODEL, service_id=service_id)

    async def _inner_get_chat_message_contents(
        self, chat_history: ChatHistory, settings: Any
    ) -> list[ChatMessageContent]:
        role = _role_of(chat_history)
        user_text = _last_user_text(chat_history)
        responder = _RESPONDERS.get(role)
        text = responder(user_text, chat_history) if responder else f"[mock:{role or 'agent'}] {user_text}"
        words_in = sum(len((m.content or "").split()) for m in chat_history.messages)
        return [
            ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content=text,
                ai_model_id=MOCK_MODEL,
                metadata={"usage": {"prompt_tokens": words_in, "completion_tokens": len(text.split())}},
            )
        ]


    async def _inner_get_streaming_chat_message_contents(
        self, chat_history: ChatHistory, settings: Any, function_invoke_attempt: int = 0
    ):
        """Orchestrations stream; the mock sends its whole reply as one chunk."""
        (message,) = await self._inner_get_chat_message_contents(chat_history, settings)
        yield [
            StreamingChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content=message.content,
                choice_index=0,
                ai_model_id=MOCK_MODEL,
                metadata=message.metadata,
            )
        ]


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------
def _fresh_http_client(timeout: int):
    """No kept-alive connections: every call opens a new one.

    Same fix as PackPilot: on some networks an idle pooled connection to
    Azure hangs for ~30 s before failing over. Fresh connections avoid it.
    """
    import httpx

    return httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=20),
        timeout=httpx.Timeout(timeout, connect=10.0),
    )


def get_chat_service(info: ProviderInfo | None = None) -> ChatCompletionClientBase:
    info = info or resolve_provider()
    cfg = settings.AI_ENGINE

    if info.active == "GITHUB_MODELS":
        from openai import AsyncOpenAI
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

        client = AsyncOpenAI(
            base_url=GITHUB_MODELS_URL,
            api_key=cfg["GITHUB_TOKEN"],
            timeout=cfg["TIMEOUT_SECONDS"],
            max_retries=2,
            http_client=_fresh_http_client(cfg["TIMEOUT_SECONDS"]),
        )
        return OpenAIChatCompletion(ai_model_id=info.model, async_client=client, service_id="chat")

    if info.active == "AZURE":
        from openai import AsyncAzureOpenAI
        from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

        endpoint = cfg["AZURE_ENDPOINT"].rstrip("/")
        for suffix in ("/openai/v1", "/openai"):
            if endpoint.endswith(suffix):
                endpoint = endpoint[: -len(suffix)]
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=cfg["AZURE_KEY"],
            api_version=cfg["AZURE_API_VERSION"],
            timeout=cfg["TIMEOUT_SECONDS"],
            max_retries=2,
            http_client=_fresh_http_client(cfg["TIMEOUT_SECONDS"]),
        )
        return AzureChatCompletion(deployment_name=info.model, async_client=client, service_id="chat")

    return MockChatCompletion()
