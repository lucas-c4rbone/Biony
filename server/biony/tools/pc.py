"""Ligar e desligar o PC do Lucas.

Ligar: liga o filtro de linha (a BIOS liga o PC ao receber energia) e avisa quando o
agente do PC responder. Desligar: pede ao agente para desligar o Windows e SÓ corta o
filtro depois que o PC parar de responder; se ele não desligar, o filtro fica ligado.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Protocol

from biony.core.ports import Notifier
from biony.core.tools import Tool, ToolDefinition, ToolResult
from biony.tools.home import HomeController

log = logging.getLogger(__name__)


class PcAgentError(RuntimeError):
    pass


class PcAgent(Protocol):
    async def status(self) -> Mapping[str, Any] | None:
        """Estado do PC, ou None se ele não responder."""

    async def shutdown(self, seconds: int) -> None:
        """Pede para o Windows desligar em `seconds` segundos."""


class PcController:
    def __init__(
        self,
        agent: PcAgent,
        home: HomeController | None,
        setup_device: str,
        notifier: Notifier | None,
        *,
        warn_seconds: int = 30,
        poll_interval: float = 5.0,
        timeout: float = 240.0,
        settle: float = 15.0,
        misses_to_off: int = 3,
    ) -> None:
        self._agent = agent
        self._home = home
        self._setup = setup_device
        self._notifier = notifier
        self.warn_seconds = warn_seconds
        self._poll = poll_interval
        self._timeout = timeout
        self._settle = settle
        self._misses = misses_to_off
        self._watcher: asyncio.Task | None = None

    async def turn_on(self) -> ToolResult:
        if await self._agent.status() is not None:
            return ToolResult(True, "O PC já está ligado.")
        if self._home is None or self._setup not in self._home.config.devices:
            return ToolResult(False, f"Não sei ligar o PC: falta o aparelho '{self._setup}' no casa.toml.")
        result = await self._home.control(self._setup, "ligar")
        if not result.ok:
            return result
        self._watch(self._wait_online())
        return ToolResult(True, "Liguei o filtro; o PC deve ligar sozinho. Aviso no Telegram quando ele estiver online.")

    async def turn_off(self, already_off_ok: bool = False) -> ToolResult:
        """`already_off_ok`: numa rotina ("boa noite"), PC já desligado não é erro."""
        try:
            if await self._agent.status() is None:
                if already_off_ok:
                    return ToolResult(True, "O PC já estava desligado.")
                return ToolResult(
                    False,
                    "O PC não respondeu: ele provavelmente já está desligado (ou o agente não está rodando). "
                    "Não cortei a energia. Se quiser cortar mesmo assim, desligue o setup pelo casa_controlar.",
                )
            await self._agent.shutdown(self.warn_seconds)
        except PcAgentError as error:
            return ToolResult(False, f"Não consegui desligar o PC: {error}.")
        self._watch(self._wait_off_then_cut())
        return ToolResult(
            True,
            f"Mandei o Windows desligar (aviso de {self.warn_seconds} s na tela). "
            "Corto a energia do filtro só depois que ele apagar, e aviso no Telegram.",
        )

    async def status(self) -> ToolResult:
        try:
            state = await self._agent.status()
        except PcAgentError as error:
            return ToolResult(False, str(error))
        if state is None:
            return ToolResult(True, "PC desligado (ou o agente não está respondendo).")
        logged = "com alguém logado" if state.get("usuario_logado") else "na tela de bloqueio (ninguém logado)"
        return ToolResult(True, f"PC ligado, {logged}.")

    # ------------------------------------------------------------- vigias

    def _watch(self, job) -> None:
        if self._watcher is not None and not self._watcher.done():
            self._watcher.cancel()
        self._watcher = asyncio.create_task(job)

    async def _wait_online(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while loop.time() < deadline:
            await asyncio.sleep(self._poll)
            if await self._safe_status() is not None:
                await self._notify("💻 Seu PC está online. Pode conectar pelo Moonlight.")
                return
        await self._notify("⚠️ Liguei o filtro, mas o PC não respondeu em 4 minutos. A BIOS está em \"Power On\"?")

    async def _wait_off_then_cut(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.warn_seconds + self._timeout
        misses = 0
        while loop.time() < deadline:
            await asyncio.sleep(self._poll)
            misses = misses + 1 if await self._safe_status() is None else 0
            if misses >= self._misses:
                # Margem para o Windows terminar de gravar tudo depois que a rede caiu.
                await asyncio.sleep(self._settle)
                result = await self._home.control(self._setup, "desligar") if self._home else None
                if result is not None and result.ok:
                    await self._notify("🔌 PC desligado e filtro cortado.")
                else:
                    await self._notify(f"🔌 PC desligado, mas não consegui cortar o filtro: {result.content if result else 'sem HA'}")
                return
        await self._notify("⚠️ O PC não desligou (algum programa pode ter travado o desligamento). Deixei o filtro ligado.")

    async def _safe_status(self) -> Mapping[str, Any] | None:
        try:
            return await self._agent.status()
        except PcAgentError:
            log.exception("Agente do PC recusou a consulta.")
            return {}  # respondeu (mesmo recusando): o PC está ligado

    async def _notify(self, text: str) -> None:
        log.info("PC: %s", text)
        if self._notifier is None:
            return
        try:
            await self._notifier.send(text)
        except Exception:
            log.exception("Falha ao avisar sobre o PC.")


class PcOnTool(Tool):
    def __init__(self, pc: PcController) -> None:
        self._pc = pc
        self.definition = ToolDefinition(
            name="pc_ligar",
            description="Liga o PC do Lucas (liga o filtro do setup; a BIOS liga o PC) e avisa no Telegram quando ele estiver online.",
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        return await self._pc.turn_on()


class PcOffTool(Tool):
    def __init__(self, pc: PcController) -> None:
        self._pc = pc
        self.definition = ToolDefinition(
            name="pc_desligar",
            description=(
                "Desliga o PC do Lucas do jeito certo: desliga o Windows e só depois corta o filtro do setup. "
                "Use sempre esta ferramenta para desligar o PC (não desligue o setup direto)."
            ),
            requires_confirmation=True,
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        return "desligar o Windows do PC e depois cortar a energia do setup"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        return await self._pc.turn_off()


class PcStatusTool(Tool):
    def __init__(self, pc: PcController) -> None:
        self._pc = pc
        self.definition = ToolDefinition(
            name="pc_status",
            description="Diz se o PC do Lucas está ligado e se tem alguém logado.",
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        return await self._pc.status()


def pc_tools(pc: PcController) -> list[Tool]:
    return [PcOnTool(pc), PcOffTool(pc), PcStatusTool(pc)]
