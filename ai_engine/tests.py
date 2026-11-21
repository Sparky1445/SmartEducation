"""AI engine tests. They run fully offline: LLM_PROVIDER is forced to MOCK."""

from io import StringIO

from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from . import services
from .llm import MockChatCompletion, get_chat_service, resolve_provider
from .models import AgentRun

MOCK = {
    "PROVIDER": "MOCK", "GITHUB_TOKEN": "", "GITHUB_MODEL": "x", "AZURE_ENDPOINT": "",
    "AZURE_KEY": "", "AZURE_MODEL": "x", "AZURE_API_VERSION": "2024-10-21", "TIMEOUT_SECONDS": 5,
}


@override_settings(AI_ENGINE=MOCK)
class ProviderTests(TestCase):
    def test_mock_is_default(self):
        info = resolve_provider()
        self.assertEqual(info.active, "MOCK")
        self.assertFalse(info.fell_back)
        self.assertIsInstance(get_chat_service(), MockChatCompletion)

    def test_missing_key_falls_back_to_mock(self):
        with self.settings(AI_ENGINE={**MOCK, "PROVIDER": "GITHUB_MODELS"}):
            info = resolve_provider()
        self.assertEqual(info.active, "MOCK")
        self.assertTrue(info.fell_back)
        self.assertIn("GITHUB_TOKEN", info.reason)

    def test_unknown_provider_falls_back(self):
        with self.settings(AI_ENGINE={**MOCK, "PROVIDER": "BANANA"}):
            self.assertTrue(resolve_provider().fell_back)


@override_settings(AI_ENGINE=MOCK)
class PingServiceTests(TestCase):
    def test_ping_runs_a_real_semantic_kernel_agent(self):
        run = services.ping("Hello Librarian")
        self.assertEqual(run.status, AgentRun.Status.SUCCESS)
        self.assertIn("Kernel online", run.output["reply"])
        self.assertEqual([s["kind"] for s in run.trace], ["input", "reply"])
        self.assertGreater(run.tokens_used, 0)
        self.assertIsNotNone(run.duration_ms)

    def test_contract_shapes(self):
        result = services.ask("What is osmosis?")
        self.assertEqual(
            set(result), {"answer", "citations", "trust_score", "in_repository", "run_id"}
        )
        self.assertEqual(services.suggest_next_resources(None), [])


@override_settings(AI_ENGINE=MOCK)
class NothingPublicTests(TestCase):
    """The engine works behind the scenes: no public page shows runs or agents."""

    def test_no_public_ai_urls(self):
        for url in ("/ai/", "/ai/runs/1/", "/ai/runs/1.json"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_home_does_not_mention_the_engine(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        for word in ("agent", "Semantic Kernel", "MOCK", "engine"):
            self.assertNotContains(response, word)

    def test_runs_are_visible_to_staff_in_admin(self):
        services.ping("Hello there")
        User.objects.create_superuser("admin", "a@example.com", "pass12345")
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("admin:ai_engine_agentrun_changelist"))
        self.assertContains(response, "Kernel ping")

    def test_runs_are_hidden_from_anonymous_users(self):
        response = self.client.get(reverse("admin:ai_engine_agentrun_changelist"))
        self.assertEqual(response.status_code, 302)


@override_settings(AI_ENGINE=MOCK)
class CommandTests(TestCase):
    def test_ai_ping_command(self):
        out = StringIO()
        call_command("ai_ping", "Hello", stdout=out)
        self.assertIn("provider: MOCK", out.getvalue())
        self.assertIn("Kernel online", out.getvalue())
