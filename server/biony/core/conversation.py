"""Loop de conversa: usuário → LLM → ferramentas → LLM → resposta."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, tzinfo
import logging
from typing import Callable
from uuid import uuid4

from biony.core.confirmation import Answer, interpret
from biony.core.models import Channel, ChatMessage, Emotion, PendingConfirmation, Reply, Role, ToolCall
from biony.core.permissions import Decision, PermissionPolicy
from biony.core.persona import system_prompt
from biony.core.ports import ConversationStore, LLMClient
from biony.core.tools import ToolRegistry, ToolResult

log = logging.getLogger(__name__)

AWAITING_RESULT = "Aguardando confirmação do usuário; ainda não executado."


class ConversationEngine:
    def __init__(
        self,
        llm: LLMClient,
        store: ConversationStore,
        tools: ToolRegistry,
        policy: PermissionPolicy,
        *,
        user_name: str,
        timezone: tzinfo,
        history_limit: int = 30,
        max_tool_rounds: int = 5,
        clock: Callable[[tzinfo], datetime] = datetime.now,
        extra_context: Callable[[], str] | None = None,
    ) -> None:
        self._llm = llm
        self._store = store
        self._tools = tools
        self._policy = policy
        self._user_name = user_name
        self._timezone = timezone
        self._history_limit = history_limit
        self._max_tool_rounds = max_tool_rounds
        self._clock = clock
        # Texto a mais no prompt de sistema a cada chamada (ex.: as memórias salvas).
        self._extra_context = extra_context
        self._pending: dict[str, PendingConfirmation] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle(
        self, text: str, session_id: str | None = None, channel: Channel = Channel.TEXT
    ) -> Reply:
        session_id = session_id or uuid4().hex
        async with self._locks[session_id]:
            pending = self._pending.pop(session_id, None)
            self._append(session_id, ChatMessage(Role.USER, text))
            executed: list[ToolResult] = []  # para escolher a emoção da resposta

            if pending is not None:
                answer = interpret(text)
                if answer is Answer.NO:
                    return self._say(session_id, "Beleza, cancelei.")
                if answer is Answer.YES:
                    # O LLM só vê o resultado depois do "sim"; reapresentamos as
                    # chamadas para manter a sequência assistant → tool válida.
                    calls = tuple(
                        ToolCall(f"{call.id}-ok", call.name, call.arguments) for call in pending.calls
                    )
                    self._append(session_id, ChatMessage(Role.ASSISTANT, tool_calls=calls))
                    results = await asyncio.gather(*(self._run(call, confirmed=True) for call in calls))
                    for call, result in zip(calls, results):
                        self._append_result(session_id, call, result)
                    executed.extend(results)
                # UNCLEAR: a ação é descartada e a mensagem segue como um pedido novo.

            return await self._loop(session_id, channel, executed)

    def transcript(self, session_id: str, limit: int = 100) -> list[ChatMessage]:
        """Só as falas do usuário e do Biony (sem chamadas e resultados de ferramentas)."""
        return [
            message
            for message in self._store.recent(session_id, limit)
            if message.role in (Role.USER, Role.ASSISTANT) and message.content
        ]

    async def _loop(self, session_id: str, channel: Channel, executed: list[ToolResult]) -> Reply:
        definitions = self._tools.definitions()
        for _ in range(self._max_tool_rounds):
            reply = await self._llm.chat(self._context(session_id, channel), definitions)
            if not reply.tool_calls:
                if not reply.content:
                    log.warning("LLM devolveu resposta vazia (sessão %s).", session_id)
                    return self._say(session_id, "Hmm, me perdi aqui. Pode repetir?", emotion=Emotion.CONFUSED)
                return self._say(session_id, reply.content, emotion=_emotion(executed))

            self._append(session_id, ChatMessage(Role.ASSISTANT, reply.content, reply.tool_calls))
            waiting: list[ToolCall] = []
            # As chamadas de uma mesma rodada são independentes (o LLM pediu todas de uma vez),
            # então rodam juntas: um aparelho lento não atrasa os outros.
            results = await asyncio.gather(*(self._run(call) for call in reply.tool_calls))
            for call, result in zip(reply.tool_calls, results):
                if result is None:
                    waiting.append(call)
                    result = ToolResult(False, AWAITING_RESULT)
                else:
                    executed.append(result)
                self._append_result(session_id, call, result)

            if waiting:
                self._pending[session_id] = PendingConfirmation(session_id, waiting)
                actions = " e ".join(self._tools.get(call.name).describe(call.arguments) for call in waiting)
                return self._say(session_id, f"Vou {actions}. Confirma?", awaiting=True, emotion=Emotion.DOUBT)

        log.warning("Limite de %d rodadas de ferramentas atingido (sessão %s).", self._max_tool_rounds, session_id)
        return self._say(
            session_id, "Me enrolei tentando fazer isso. Pode pedir de novo de outro jeito?", emotion=Emotion.CONFUSED
        )

    async def _run(self, call: ToolCall, confirmed: bool = False) -> ToolResult | None:
        """Executa uma chamada; devolve None se ela precisar de confirmação."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(False, f"Ferramenta desconhecida: {call.name}.")
        if call.arguments_error is not None:
            return ToolResult(False, f"Argumentos inválidos: {call.arguments_error}")

        decision = self._policy.decide(tool.definition, confirmed=confirmed)
        if decision is Decision.DENIED:
            log.info("Ferramenta bloqueada: %s %s", call.name, call.arguments)
            return ToolResult(False, "Ferramenta bloqueada pela política de permissões.")
        if decision is Decision.REQUIRES_CONFIRMATION:
            return None
        if not confirmed and tool.needs_confirmation(call.arguments):
            return None

        try:
            result = await tool.execute(call.arguments)
        except Exception as error:
            log.exception("Ferramenta %s falhou.", call.name)
            result = ToolResult(False, f"Erro ao executar: {error}")
        log.info("Ferramenta %s %s → ok=%s", call.name, call.arguments, result.ok)
        return result

    def _context(self, session_id: str, channel: Channel) -> list[ChatMessage]:
        history = self._store.recent(session_id, self._history_limit)
        # O corte por quantidade pode cair no meio de um turno; começamos sempre
        # em uma mensagem do usuário para não deixar resultados de ferramenta órfãos.
        while history and history[0].role is not Role.USER:
            history.pop(0)
        prompt = system_prompt(self._user_name, self._clock(self._timezone), channel)
        if self._extra_context is not None:
            prompt += "\n\n" + self._extra_context()
        return [ChatMessage(Role.SYSTEM, prompt), *history]

    def _append(self, session_id: str, message: ChatMessage) -> None:
        self._store.append(session_id, message)

    def _append_result(self, session_id: str, call: ToolCall, result: ToolResult) -> None:
        self._append(session_id, ChatMessage(Role.TOOL, result.content, tool_call_id=call.id))

    def _say(
        self, session_id: str, text: str, awaiting: bool = False, emotion: Emotion = Emotion.NEUTRAL
    ) -> Reply:
        self._append(session_id, ChatMessage(Role.ASSISTANT, text))
        return Reply(session_id, text, awaiting_confirmation=awaiting, emotion=emotion)


def _emotion(executed: list[ToolResult]) -> Emotion:
    if not executed:
        return Emotion.NEUTRAL
    return Emotion.HAPPY if all(result.ok for result in executed) else Emotion.SAD
