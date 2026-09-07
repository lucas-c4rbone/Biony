"""Adaptador do contrato Brain para a API da OpenAI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Mapping, Protocol

from core.models import BrainResponse, Memory, MemoryRequest, ToolRequest, ToolResult
from core.tools import ToolDefinition


class OpenAIBrainError(RuntimeError):
    """Falha controlada ao obter uma resposta da OpenAI."""


class OpenAIClient(Protocol):
    """Porta mínima do cliente usado pelo OpenAIBrain."""

    def create_response(self, *, model: str, message: str) -> str:
        """Retorna apenas o texto de uma resposta da OpenAI."""

    def create_interaction(
        self, *, model: str, message: str, tools: tuple[Mapping[str, object], ...]
    ) -> "OpenAIInteraction":
        """Inicia uma interação que pode retornar uma chamada de função."""

    def continue_interaction(
        self, *, model: str, response_id: str, call_id: str, result: object
    ) -> "OpenAIInteraction":
        """Envia o resultado de uma chamada de função e obtém a próxima resposta."""


@dataclass(frozen=True)
class OpenAIFunctionCall:
    """Chamada de função normalizada a partir da Responses API."""

    call_id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class OpenAIInteraction:
    """Resposta normalizada da Responses API para o OpenAIBrain."""

    response_id: str
    text: str | None = None
    function_calls: tuple[OpenAIFunctionCall, ...] = ()


class OpenAIResponsesClient:
    """Adapta a Responses API para a porta local de cliente."""

    def __init__(self, client: object) -> None:
        self._client = client

    def create_response(self, *, model: str, message: str) -> str:
        response = self._client.responses.create(model=model, input=message)
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            return self._invalid_response()
        return output_text

    def create_interaction(
        self, *, model: str, message: str, tools: tuple[Mapping[str, object], ...]
    ) -> OpenAIInteraction:
        response = self._client.responses.create(
            model=model,
            input=message,
            tools=list(tools),
            parallel_tool_calls=False,
        )
        return self._extract_interaction(response)

    def continue_interaction(
        self, *, model: str, response_id: str, call_id: str, result: object
    ) -> OpenAIInteraction:
        response = self._client.responses.create(
            model=model,
            previous_response_id=response_id,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str),
                }
            ],
        )
        return self._extract_interaction(response)

    @staticmethod
    def _extract_interaction(response: object) -> OpenAIInteraction:
        response_id = getattr(response, "id", None)
        if not isinstance(response_id, str) or not response_id:
            raise OpenAIBrainError("OpenAI returned an invalid response.")

        function_calls: list[OpenAIFunctionCall] = []
        for item in getattr(response, "output", ()):
            if getattr(item, "type", None) != "function_call":
                continue
            call_id = getattr(item, "call_id", None)
            name = getattr(item, "name", None)
            arguments = OpenAIResponsesClient._parse_arguments(getattr(item, "arguments", None))
            if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
                raise OpenAIBrainError("OpenAI returned an invalid function call.")
            function_calls.append(OpenAIFunctionCall(call_id, name, arguments))

        output_text = getattr(response, "output_text", None)
        text = output_text if isinstance(output_text, str) and output_text.strip() else None
        if text is None and not function_calls:
            raise OpenAIBrainError("OpenAI returned an invalid response.")
        return OpenAIInteraction(response_id=response_id, text=text, function_calls=tuple(function_calls))

    @staticmethod
    def _parse_arguments(arguments: object) -> Mapping[str, object]:
        if not isinstance(arguments, str):
            raise OpenAIBrainError("OpenAI returned invalid function arguments.")
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise OpenAIBrainError("OpenAI returned invalid function arguments.") from error
        if not isinstance(parsed_arguments, dict):
            raise OpenAIBrainError("OpenAI returned invalid function arguments.")
        return parsed_arguments

    @staticmethod
    def _invalid_response() -> str:
        raise OpenAIBrainError("OpenAI returned an invalid response.")


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
        self._response_ids: dict[str, str] = {}

    def respond(self, message: str) -> str:
        """Envia uma mensagem e retorna somente o texto da resposta."""
        client = self._client or self._create_client()
        try:
            return client.create_response(model=self.model, message=message)
        except OpenAIBrainError:
            raise
        except Exception as error:
            raise OpenAIBrainError("Unable to get a response from OpenAI.") from error

    def respond_with_tools(self, message: str) -> BrainResponse:
        """Gera uma resposta que pode solicitar uma ferramenta do Core."""
        return self.respond_with_context(message, (), ())

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        """Devolve ao modelo o resultado de uma ferramenta executada pelo Core."""
        if result.request_id is None:
            raise OpenAIBrainError("Tool result does not identify its request.")
        return self._continue_after_function_call(result.request_id, {"success": result.success, "value": result.value})

    def respond_with_memory(self, message: str, memories: tuple[Memory, ...]) -> BrainResponse:
        """Gera uma resposta usando as memórias relevantes fornecidas pelo Core."""
        return self.respond_with_context(message, memories, ())

    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        """Mantém compatibilidade com a extensão legada de memória."""
        raise OpenAIBrainError("Memory search results require an identified request.")

    def respond_to_identified_memory_result(
        self, request: MemoryRequest, memories: tuple[Memory, ...]
    ) -> BrainResponse:
        """Devolve ao modelo o resultado de uma busca de memória do Core."""
        if request.identifier is None:
            raise OpenAIBrainError("Memory request does not identify its call.")
        return self._continue_after_function_call(
            request.identifier, {"memories": [memory.content for memory in memories]}
        )

    def respond_with_context(
        self, message: str, memories: tuple[Memory, ...], tools: tuple[object, ...]
    ) -> BrainResponse:
        """Gera uma resposta com memórias e definições de ferramentas autorizadas."""
        tool_definitions = tuple(
            self._tool_definition(tool)
            for tool in tools
            if isinstance(tool, ToolDefinition)
        )
        interaction = self._interaction_client().create_interaction(
            model=self.model,
            message=self._message_with_memories(message, memories),
            tools=(self._memory_tool_definition(), *tool_definitions),
        )
        return self._to_brain_response(interaction)

    def _create_client(self) -> OpenAIClient:
        if not self._api_key:
            raise OpenAIBrainError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise OpenAIBrainError("The OpenAI client library is not installed.") from error
        self._client = OpenAIResponsesClient(OpenAI(api_key=self._api_key, timeout=self.timeout))
        return self._client

    def _interaction_client(self) -> OpenAIClient:
        return self._client or self._create_client()

    def _continue_after_function_call(self, call_id: str, result: object) -> BrainResponse:
        client = self._interaction_client()
        try:
            interaction = client.continue_interaction(
                model=self.model,
                response_id=self._response_id_for_call(call_id),
                call_id=call_id,
                result=result,
            )
        except OpenAIBrainError:
            raise
        except Exception as error:
            raise OpenAIBrainError("Unable to get a response from OpenAI.") from error
        return self._to_brain_response(interaction)

    def _to_brain_response(self, interaction: OpenAIInteraction) -> BrainResponse:
        if interaction.function_calls:
            function_call = interaction.function_calls[0]
            self._response_ids[function_call.call_id] = interaction.response_id
            if function_call.name == "search_memory":
                query = function_call.arguments.get("query")
                if not isinstance(query, str) or not query:
                    raise OpenAIBrainError("OpenAI returned invalid function arguments.")
                return BrainResponse(memory_request=MemoryRequest(query, function_call.call_id))
            return BrainResponse(
                tool_requests=(
                    ToolRequest(
                        name=function_call.name,
                        arguments=function_call.arguments,
                        identifier=function_call.call_id,
                    ),
                )
            )
        if interaction.text is None:
            raise OpenAIBrainError("OpenAI returned an invalid response.")
        return BrainResponse(message=interaction.text)

    def _response_id_for_call(self, call_id: str) -> str:
        response_id = self._response_ids.pop(call_id, None)
        if response_id is None:
            raise OpenAIBrainError("Function call does not belong to this Brain.")
        return response_id

    @staticmethod
    def _message_with_memories(message: str, memories: tuple[Memory, ...]) -> str:
        if not memories:
            return message
        memory_lines = "\n".join(f"- {memory.content}" for memory in memories)
        return f"Relevant memories:\n{memory_lines}\n\nUser message:\n{message}"

    @staticmethod
    def _tool_definition(tool: ToolDefinition) -> Mapping[str, object]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": {name: {} for name in tool.expected_arguments},
                "required": list(tool.expected_arguments),
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _memory_tool_definition() -> Mapping[str, object]:
        return {
            "type": "function",
            "name": "search_memory",
            "description": "Searches the user's saved memories by text.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _environment_timeout() -> float:
        configured_timeout = os.environ.get("OPENAI_TIMEOUT")
        if configured_timeout is None:
            return 30.0
        try:
            return float(configured_timeout)
        except ValueError as error:
            raise ValueError("OPENAI_TIMEOUT must be numeric.") from error