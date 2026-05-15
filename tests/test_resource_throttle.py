import unittest
from unittest.mock import patch

from legal_agent.openai_client import summarize_facts
from legal_agent.resource_throttle import ResourceBudget, ThrottlingAgent, reset_throttling_agent


class TestResourceThrottle(unittest.TestCase):
    def tearDown(self):
        reset_throttling_agent(None)

    def test_clamps_ai_context_and_output_budget(self):
        agent = ThrottlingAgent(
            ResourceBudget(
                ai_max_context_chars=1000,
                ai_max_output_tokens=256,
                ai_requests_per_minute=10,
                http_requests_per_minute=10,
            )
        )

        context, status = agent.clamp_ai_context("x" * 1500)

        self.assertEqual(len(context), 1000)
        self.assertTrue(status["truncated"])
        self.assertEqual(agent.clamp_ai_output_tokens(1200), 256)

    def test_openai_client_uses_throttle_budget_and_procedure(self):
        class FakeMessage:
            content = "Short summary."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeCompletions:
            kwargs = {}

            def create(self, **kwargs):
                FakeCompletions.kwargs = kwargs
                return FakeResponse()

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAIModule:
            RateLimitError = type("RateLimitError", (Exception,), {})
            AuthenticationError = type("AuthenticationError", (Exception,), {})
            APIConnectionError = type("APIConnectionError", (Exception,), {})
            APITimeoutError = type("APITimeoutError", (Exception,), {})
            APIError = type("APIError", (Exception,), {})

            class OpenAI:
                def __init__(self, api_key):
                    self.api_key = api_key
                    self.chat = FakeChat()

        reset_throttling_agent(
            ThrottlingAgent(
                ResourceBudget(
                    ai_max_context_chars=1000,
                    ai_max_output_tokens=256,
                    ai_requests_per_minute=10,
                    http_requests_per_minute=10,
                )
            )
        )

        with patch("legal_agent.openai_client.openai", FakeOpenAIModule):
            result = summarize_facts("test-api-key", "Material fact text.")

        self.assertEqual(result, "Short summary.")
        self.assertEqual(FakeCompletions.kwargs["max_tokens"], 256)
        messages = FakeCompletions.kwargs["messages"]
        self.assertIn("mandatory resource throttling procedure", messages[1]["content"].lower())
        self.assertIn("Obey the mandatory resource throttling procedure", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
