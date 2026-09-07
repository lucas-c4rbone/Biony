"""Adaptador do contrato Brain para a API da OpenAI."""

from __future__ import annotations

import os
from typing import Protocol


class OpenAIBrainError(RuntimeError):
    """Falha controlada ao obter uma resposta da OpenAI."""


class OpenAIClient(Protocol):
    """Porta mínima do cliente usado pelo OpenAIBrain."""

    def create_response(self, *, model: str, message: str) -> str:
        """Retorna apenas o texto de uma resposta da OpenAI."""


class OpenAIResponsesClient:
    """Adapta a Responses API para a porta local de cliente."""

    def __init__(self, client: object) -> None:
        self._client = client

    def create_response(self, *, model: str, message: str) -> str:
        response = self._client.responses.create(model=model, input=message)
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise OpenAIBrainError("OpenAI returned an invalid response.")
        return output_text


class OpenAIBrain:
    """Produz respostas textuais por meio de um cliente OpenAI injetável."""

    def __init__(
        self,
        client: OpenAIClient | None = None,
        *,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._api_key = os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
        self.timeout = timeout if timeout is not None else self._environment_timeout()

    def respond(self, message: str) -> str:
        """Envia uma mensagem e retorna somente o texto da resposta."""
        client = self._client or self._create_client()
        try:
            return client.create_response(model=self.model, message=message)
        except OpenAIBrainError:
            raise
        except Exception as error:
            raise OpenAIBrainError("Unable to get a response from OpenAI.") from error

    def _create_client(self) -> OpenAIClient:
        if not self._api_key:
            raise OpenAIBrainError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise OpenAIBrainError("The OpenAI client library is not installed.") from error
        self._client = OpenAIResponsesClient(OpenAI(api_key=self._api_key, timeout=self.timeout))
        return self._client

    @staticmethod
    def _environment_timeout() -> float:
        configured_timeout = os.environ.get("OPENAI_TIMEOUT")
        if configured_timeout is None:
            return 30.0
        try:
            return float(configured_timeout)
        except ValueError as error:
            raise ValueError("OPENAI_TIMEOUT must be numeric.") from error