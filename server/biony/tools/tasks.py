"""Ferramentas de tarefas (com prazo) e lembretes (com horário)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from biony.core.reminder_service import ReminderService
from biony.core.reminders import Due, Reminder
from biony.core.tools import Tool, ToolDefinition, ToolResult

_ID = {"type": "integer", "description": "id mostrado por tarefas_listar"}


def _when(service: ReminderService, reminders: list[Reminder]) -> str:
    if not reminders:
        return "nenhum aviso agendado"
    return ", ".join(f"{service.local(r.fire_at):%d/%m %H:%M}" for r in reminders)


class TaskCreateTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        policy = service.policy
        days = ", ".join(str(d) for d in policy.days_before)
        self.definition = ToolDefinition(
            name="tarefa_criar",
            description=(
                "Salva uma tarefa/compromisso com prazo (trabalho, prova, conta para pagar...) e agenda "
                f"avisos no Telegram. Por padrão avisa {days} dia(s) antes do prazo, às {policy.at:%H:%M}, "
                f"e nunca entre {policy.quiet.start:%H:%M} e {policy.quiet.end:%H:%M}. "
                "Use para coisas com data; para um lembrete num horário exato use lembrete_criar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Curto, ex.: 'Trabalho de Cálculo 2'"},
                    "prazo": {
                        "type": "string",
                        "description": (
                            "AAAA-MM-DD, ou AAAA-MM-DDTHH:MM se tiver horário (horário local). "
                            "Calcule a partir da data de hoje do prompt. Omita se não houver prazo."
                        ),
                    },
                    "observacoes": {"type": "string", "description": "Detalhes úteis (matéria, professor, formato...)"},
                    "avisar_dias_antes": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 60},
                        "description": "Só se o Lucas pedir avisos diferentes do padrão. 0 = no dia.",
                    },
                },
                "required": ["titulo"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        title = str(arguments.get("titulo", "")).strip()
        if not title:
            return ToolResult(False, "Faltou o título da tarefa.")
        due = None
        if arguments.get("prazo"):
            try:
                due = Due.parse(str(arguments["prazo"]))
            except ValueError:
                return ToolResult(False, f"Prazo inválido: {arguments['prazo']!r}. Use AAAA-MM-DD ou AAAA-MM-DDTHH:MM.")
            if due.deadline(self._service.now().tzinfo) < self._service.now():
                return ToolResult(False, f"O prazo {due.human()} já passou. Confirme a data com o Lucas.")
        days = arguments.get("avisar_dias_antes")
        if days is not None and (not isinstance(days, list) or not all(isinstance(d, int) and 0 <= d <= 60 for d in days)):
            return ToolResult(False, "avisar_dias_antes precisa ser uma lista de inteiros de 0 a 60.")
        task, reminders = self._service.create_task(title, due, str(arguments.get("observacoes", "")).strip(), days)
        when = f"prazo {due.human()}; avisos: {_when(self._service, reminders)}" if due else "sem prazo, sem avisos"
        return ToolResult(True, f"Tarefa {task.id} salva: {task.title} ({when}).")


class ReminderCreateTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        self.definition = ToolDefinition(
            name="lembrete_criar",
            description="Agenda um lembrete no Telegram num horário exato (ex.: 'me lembra às 18h de tirar a roupa do varal').",
            parameters={
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "O que lembrar, ex.: 'tirar a roupa do varal'"},
                    "quando": {"type": "string", "description": "AAAA-MM-DDTHH:MM (horário local). Calcule a partir de agora."},
                },
                "required": ["texto", "quando"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        text = str(arguments.get("texto", "")).strip()
        if not text:
            return ToolResult(False, "Faltou o texto do lembrete.")
        try:
            when = datetime.fromisoformat(str(arguments.get("quando", "")))
        except ValueError:
            return ToolResult(False, f"Horário inválido: {arguments.get('quando')!r}. Use AAAA-MM-DDTHH:MM.")
        if when.tzinfo is None:
            when = when.replace(tzinfo=self._service.now().tzinfo)
        try:
            reminder = self._service.create_reminder(text, when)
        except ValueError as error:
            return ToolResult(False, f"Não agendei: {error}.")
        quiet = " (cai no horário de silêncio, mas foi um horário pedido, então vale)" if self._service.policy.quiet.contains(when) else ""
        return ToolResult(True, f"Lembrete {reminder.id} agendado para {self._service.local(when):%d/%m às %H:%M}{quiet}.")


class TaskListTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        self.definition = ToolDefinition(
            name="tarefas_listar",
            description="Lista as tarefas em aberto (com prazos e avisos) e os lembretes agendados.",
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        lines = []
        for task, reminders in self._service.open_tasks():
            due = f"prazo {task.due.human()}" if task.due else "sem prazo"
            notes = f" — {task.notes}" if task.notes else ""
            lines.append(f"tarefa {task.id}: {task.title} ({due}; avisos: {_when(self._service, reminders)}){notes}")
        for reminder in self._service.standalone_reminders():
            lines.append(f"lembrete {reminder.id}: {reminder.text} ({self._service.local(reminder.fire_at):%d/%m às %H:%M})")
        return ToolResult(True, "\n".join(lines) or "Nenhuma tarefa em aberto e nenhum lembrete agendado.")


class TaskCompleteTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        self.definition = ToolDefinition(
            name="tarefa_concluir",
            description="Marca uma tarefa como feita e cancela os avisos que faltavam.",
            parameters={"type": "object", "properties": {"id": _ID}, "required": ["id"]},
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        task = self._service.complete_task(int(arguments.get("id", -1)))
        if task is None:
            return ToolResult(False, "Não achei essa tarefa em aberto. Use tarefas_listar para ver os ids.")
        return ToolResult(True, f"Tarefa '{task.title}' concluída; avisos restantes cancelados.")


class TaskDeleteTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        self.definition = ToolDefinition(
            name="tarefa_apagar",
            description="Apaga uma tarefa (ex.: foi cancelada ou criada por engano) e os avisos dela. Para tarefa feita, use tarefa_concluir.",
            parameters={"type": "object", "properties": {"id": _ID}, "required": ["id"]},
            requires_confirmation=True,
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        task = self._service.get_task(int(arguments.get("id", -1)))
        return f"apagar a tarefa '{task.title}'" if task else "apagar uma tarefa que não encontrei"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        task = self._service.delete_task(int(arguments.get("id", -1)))
        if task is None:
            return ToolResult(False, "Não achei essa tarefa.")
        return ToolResult(True, f"Tarefa '{task.title}' apagada.")


class ReminderCancelTool(Tool):
    def __init__(self, service: ReminderService) -> None:
        self._service = service
        self.definition = ToolDefinition(
            name="lembrete_cancelar",
            description="Cancela um lembrete agendado (o id aparece em tarefas_listar).",
            parameters={"type": "object", "properties": {"id": _ID}, "required": ["id"]},
            requires_confirmation=True,
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        reminder = self._service.get_reminder(int(arguments.get("id", -1)))
        if reminder is None:
            return "cancelar um lembrete que não encontrei"
        what = reminder.text or "um aviso de tarefa"
        return f"cancelar o lembrete '{what}' de {self._service.local(reminder.fire_at):%d/%m às %H:%M}"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        if not self._service.cancel_reminder(int(arguments.get("id", -1))):
            return ToolResult(False, "Não achei esse lembrete pendente.")
        return ToolResult(True, "Lembrete cancelado.")


def task_tools(service: ReminderService) -> list[Tool]:
    return [
        TaskCreateTool(service),
        ReminderCreateTool(service),
        TaskListTool(service),
        TaskCompleteTool(service),
        TaskDeleteTool(service),
        ReminderCancelTool(service),
    ]
