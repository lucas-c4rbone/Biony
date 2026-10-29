import unittest
from unittest.mock import Mock, patch
import sys
import os

# Adicionando o diretório atual ao path para importar os módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.openrouter_brain import OpenRouterBrain, OpenRouterBrainError


class FakeOpenRouterClient:
    def __init__(self, response: str = "Resposta do OpenRouter.") -> None:
        self.response = response
        self.calls = []

    def create_response(self, *, model: str, message: str) -> str:
        self.calls.append((model, message))
        return self.response

    def create_interaction(self, *, model: str, message: str, tools: tuple) -> object:
        self.calls.append(("interaction", model, message))
        # Simula uma resposta com função
        class FakeInteraction:
            def __init__(self):
                self.response_id = "test-id"
                self.text = "Resposta com função"
                self.function_calls = ()
        return FakeInteraction()

    def continue_interaction(self, *, model: str, response_id: str, call_id: str, result: object) -> object:
        self.calls.append(("continue", model, response_id, call_id))
        class FakeInteraction:
            def __init__(self):
                self.response_id = "test-id"
                self.text = "Resposta continuada"
                self.function_calls = ()
        return FakeInteraction()


class OpenRouterBrainTests(unittest.TestCase):
    def test_implements_the_textual_brain_contract_with_an_injected_client(self) -> None:
        client = FakeOpenRouterClient()
        brain = OpenRouterBrain(client=client, model="test-model")

        response = brain.respond("Olá, Biony")

        self.assertEqual(response, "Resposta do OpenRouter.")
        self.assertEqual(client.calls, [("test-model", "Olá, Biony")])

    def test_uses_the_model_from_the_environment(self) -> None:
        client = FakeOpenRouterClient()
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "environment-model"}, clear=True):
            brain = OpenRouterBrain(client=client)

        brain.respond("Teste")

        self.assertEqual(client.calls, [("environment-model", "Teste")])

    def test_uses_default_model_when_not_configured(self) -> None:
        client = FakeOpenRouterClient()
        with patch.dict(os.environ, {}, clear=True):  # Limpar variáveis de ambiente
            brain = OpenRouterBrain(client=client)

        brain.respond("Teste")

        # Deve usar o modelo padrão do DeepSeek
        self.assertEqual(client.calls[0][0], "deepseek/deepseek-chat")

    def test_respond_with_tools(self) -> None:
        client = FakeOpenRouterClient()
        brain = OpenRouterBrain(client=client)

        response = brain.respond_with_tools("Teste")

        # Deve retornar uma resposta sem ferramentas no mock
        self.assertIsNotNone(response.message)

    def test_respond_with_context(self) -> None:
        client = FakeOpenRouterClient()
        brain = OpenRouterBrain(client=client)

        # Teste básico de contexto
        response = brain.respond_with_context("Teste", (), ())

        # Deve retornar uma resposta
        self.assertIsNotNone(response.message)


if __name__ == "__main__":
    unittest.main()