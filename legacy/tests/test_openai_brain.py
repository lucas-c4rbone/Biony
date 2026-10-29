import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.openai_brain import OpenAIBrain, OpenAIBrainError, OpenAIResponsesClient


class FakeOpenAIClient:
    def __init__(self, response: str = "Resposta da OpenAI.", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def create_response(self, *, model: str, message: str) -> str:
        self.calls.append((model, message))
        if self.error is not None:
            raise self.error
        return self.response


class FakeResponsesAPI:
    def __init__(self, output_text: object) -> None:
        self.output_text = output_text
        self.calls: list[tuple[str, str]] = []

    def create(self, *, model: str, input: str) -> SimpleNamespace:
        self.calls.append((model, input))
        return SimpleNamespace(output_text=self.output_text)


class OpenAIBrainTests(unittest.TestCase):
    def test_implements_the_textual_brain_contract_with_an_injected_client(self) -> None:
        client = FakeOpenAIClient()
        brain = OpenAIBrain(client=client, model="test-model")

        response = brain.respond("Olá, Biony")

        self.assertEqual(response, "Resposta da OpenAI.")
        self.assertEqual(client.calls, [("test-model", "Olá, Biony")])

    def test_uses_the_model_from_the_environment(self) -> None:
        client = FakeOpenAIClient()
        with patch.dict(os.environ, {"OPENAI_MODEL": "environment-model"}, clear=False):
            brain = OpenAIBrain(client=client)

        brain.respond("Teste")

        self.assertEqual(client.calls, [("environment-model", "Teste")])

    def test_extracts_text_from_the_responses_api_adapter(self) -> None:
        responses = FakeResponsesAPI("Texto extraído.")
        client = OpenAIResponsesClient(SimpleNamespace(responses=responses))

        response = client.create_response(model="test-model", message="Teste")

        self.assertEqual(response, "Texto extraído.")
        self.assertEqual(responses.calls, [("test-model", "Teste")])

    def test_reports_a_missing_api_key_when_a_real_client_is_used(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            brain = OpenAIBrain()

            with self.assertRaisesRegex(OpenAIBrainError, "OPENAI_API_KEY"):
                brain.respond("Teste")

    def test_converts_client_errors_to_a_controlled_error(self) -> None:
        brain = OpenAIBrain(client=FakeOpenAIClient(error=TimeoutError("interno")))

        with self.assertRaisesRegex(OpenAIBrainError, "Unable to get a response") as context:
            brain.respond("Teste")

        self.assertNotIn("interno", str(context.exception))

    def test_rejects_an_invalid_response(self) -> None:
        responses = FakeResponsesAPI("")
        client = OpenAIResponsesClient(SimpleNamespace(responses=responses))

        with self.assertRaisesRegex(OpenAIBrainError, "invalid response"):
            client.create_response(model="test-model", message="Teste")