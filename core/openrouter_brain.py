"""Adaptador do contrato Brain para a API do OpenRouter com DeepSeek v4 Flash."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Mapping, Protocol

from core.models import BrainResponse, Memory, MemoryRequest, ToolRequest, ToolResult
from core.tools import ToolDefinition


class OpenRouterBrainError(RuntimeError):
    """Falha controlada ao obter uma resposta do OpenRouter."""
    

class OpenRouterClient(Protocol):
    """Porta mínima do cliente usado pelo OpenRouterBrain."""
    
    def create_response(self, *, model: str, message: str) -> str:
        """Retorna apenas o texto de uma resposta do OpenRouter."""
        
    def create_interaction(
        self, *, model: str, message: str, tools: tuple[Mapping[str, object], ...]
    ) -> "OpenRouterInteraction":
        """Inicia uma interação que pode retornar uma chamada de função."""
        
    def continue_interaction(
        self, *, model: str, response_id: str, call_id: str, result: object
    ) -> "OpenRouterInteraction":
        """Envia o resultado de uma chamada de função e obtém a próxima resposta."""


@dataclass(frozen=True)
class OpenRouterFunctionCall:
    """Chamada de função normalizada a partir da API do OpenRouter."""
    
    call_id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class OpenRouterInteraction:
    """Resposta normalizada da API do OpenRouter para o OpenRouterBrain."""
    
    response_id: str
    text: str | None = None
    function_calls: tuple[OpenRouterFunctionCall, ...] = ()


class OpenRouterClientImpl:
    """Cliente HTTP para a API do OpenRouter."""
    
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._session = None
        
    def _get_session(self):
        """Cria uma sessão HTTP com as configurações necessárias."""
        if self._session is None:
            try:
                import httpx
                self._session = httpx.Client(
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0
                )
            except ImportError:
                raise OpenRouterBrainError("O pacote httpx é necessário para usar o OpenRouter. Instale com 'pip install httpx'")
        return self._session
    
    def create_response(self, *, model: str, message: str) -> str:
        """Envia uma mensagem e retorna somente o texto da resposta."""
        try:
            session = self._get_session()
            response = session.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": message}],
                    "stream": False,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Verificar se há conteúdo na resposta
            if not data.get("choices"):
                raise OpenRouterBrainError("Resposta vazia do OpenRouter")
                
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise OpenRouterBrainError("Resposta inválida do OpenRouter")
                
            return content
        except Exception as error:
            raise OpenRouterBrainError(f"Erro ao obter resposta do OpenRouter: {error}") from error
    
    def create_interaction(
        self, *, model: str, message: str, tools: tuple[Mapping[str, object], ...]
    ) -> OpenRouterInteraction:
        """Inicia uma interação com ferramentas."""
        try:
            session = self._get_session()
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "tools": list(tools),
                "tool_choice": "auto",
                "stream": False,
            }
            response = session.post(
                f"{self._base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            # Processar a resposta
            if not data.get("choices"):
                raise OpenRouterBrainError("Resposta vazia do OpenRouter")
                
            message_content = data["choices"][0]["message"]
            response_id = data.get("id", "")
            
            # Verificar se há chamadas de função
            function_calls = []
            if "tool_calls" in message_content:
                for tool_call in message_content["tool_calls"]:
                    function_calls.append(
                        OpenRouterFunctionCall(
                            call_id=tool_call.get("id", ""),
                            name=tool_call["function"].get("name", ""),
                            arguments=tool_call["function"].get("arguments", {}),
                        )
                    )
            
            # Verificar se há texto na resposta
            text = message_content.get("content", None)
            if text is not None and not isinstance(text, str):
                text = None
                
            return OpenRouterInteraction(
                response_id=response_id,
                text=text,
                function_calls=tuple(function_calls)
            )
        except Exception as error:
            raise OpenRouterBrainError(f"Erro ao iniciar interação com OpenRouter: {error}") from error
    
    def continue_interaction(
        self, *, model: str, response_id: str, call_id: str, result: object
    ) -> OpenRouterInteraction:
        """Continua uma interação após uma chamada de função."""
        try:
            session = self._get_session()
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result, default=str),
                    }
                ],
                "stream": False,
            }
            response = session.post(
                f"{self._base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            # Processar a resposta
            if not data.get("choices"):
                raise OpenRouterBrainError("Resposta vazia do OpenRouter")
                
            message_content = data["choices"][0]["message"]
            response_id = data.get("id", "")
            
            # Verificar se há chamadas de função
            function_calls = []
            if "tool_calls" in message_content:
                for tool_call in message_content["tool_calls"]:
                    function_calls.append(
                        OpenRouterFunctionCall(
                            call_id=tool_call.get("id", ""),
                            name=tool_call["function"].get("name", ""),
                            arguments=tool_call["function"].get("arguments", {}),
                        )
                    )
            
            # Verificar se há texto na resposta
            text = message_content.get("content", None)
            if text is not None and not isinstance(text, str):
                text = None
                
            return OpenRouterInteraction(
                response_id=response_id,
                text=text,
                function_calls=tuple(function_calls)
            )
        except Exception as error:
            raise OpenRouterBrainError(f"Erro ao continuar interação com OpenRouter: {error}") from error


class OpenRouterBrain:
    """Produz respostas textuais por meio da API do OpenRouter com DeepSeek v4 Flash."""
    
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        *,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._api_key = os.environ.get("OPENROUTER_API_KEY")
        self.model = model or os.environ.get("OPENROUTER_MODEL") or "deepseek/deepseek-chat"
        self.timeout = timeout if timeout is not None else self._environment_timeout()
        self._response_ids: dict[str, str] = {}
    
    def respond(self, message: str) -> str:
        """Envia uma mensagem e retorna somente o texto da resposta."""
        client = self._client or self._create_client()
        try:
            return client.create_response(model=self.model, message=message)
        except OpenRouterBrainError:
            raise
        except Exception as error:
            raise OpenRouterBrainError("Unable to get a response from OpenRouter.") from error
    
    def respond_with_tools(self, message: str) -> BrainResponse:
        """Gera uma resposta que pode solicitar uma ferramenta do Core."""
        return self.respond_with_context(message, (), ())
    
    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        """Devolve ao modelo o resultado de uma ferramenta executada pelo Core."""
        if result.request_id is None:
            raise OpenRouterBrainError("Tool result does not identify its request.")
        return self._continue_after_function_call(result.request_id, {"success": result.success, "value": result.value})
    
    def respond_with_memory(self, message: str, memories: tuple[Memory, ...]) -> BrainResponse:
        """Gera uma resposta usando as memórias relevantes fornecidas pelo Core."""
        return self.respond_with_context(message, memories, ())
    
    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        """Mantém compatibilidade com a extensão legada de memória."""
        raise OpenRouterBrainError("Memory search results require an identified request.")
    
    def respond_to_identified_memory_result(
        self, request: MemoryRequest, memories: tuple[Memory, ...]
    ) -> BrainResponse:
        """Devolve ao modelo o resultado de uma busca de memória do Core."""
        if request.identifier is None:
            raise OpenRouterBrainError("Memory request does not identify its call.")
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
    
    def _create_client(self) -> OpenRouterClient:
        if not self._api_key:
            raise OpenRouterBrainError("OPENROUTER_API_KEY is not configured.")
        self._client = OpenRouterClientImpl(self._api_key)
        return self._client
    
    def _interaction_client(self) -> OpenRouterClient:
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
        except OpenRouterBrainError:
            raise
        except Exception as error:
            raise OpenRouterBrainError("Unable to get a response from OpenRouter.") from error
        return self._to_brain_response(interaction)
    
    def _to_brain_response(self, interaction: OpenRouterInteraction) -> BrainResponse:
        if interaction.function_calls:
            function_call = interaction.function_calls[0]
            self._response_ids[function_call.call_id] = interaction.response_id
            if function_call.name == "search_memory":
                query = function_call.arguments.get("query")
                if not isinstance(query, str) or not query:
                    raise OpenRouterBrainError("OpenRouter returned invalid function arguments.")
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
            raise OpenRouterBrainError("OpenRouter returned an invalid response.")
        return BrainResponse(message=interaction.text)
    
    def _response_id_for_call(self, call_id: str) -> str:
        response_id = self._response_ids.pop(call_id, None)
        if response_id is None:
            raise OpenRouterBrainError("Function call does not belong to this Brain.")
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
        configured_timeout = os.environ.get("OPENROUTER_TIMEOUT")
        if configured_timeout is None:
            return 30.0
        try:
            return float(configured_timeout)
        except ValueError as error:
            raise ValueError("OPENROUTER_TIMEOUT must be numeric.") from error