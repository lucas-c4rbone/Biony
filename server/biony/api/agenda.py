"""Rotas da agenda (tarefas e lembretes) para a PWA; só traduzem ↔ ReminderService."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status

from biony.api.schemas import AgendaResponse, Aviso, LembreteOut, TarefaOut, TarefaRequest
from biony.core.reminder_service import ReminderService
from biony.core.reminders import Due, Reminder, Task

_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def agenda_router(service: ReminderService, require_token: Callable[..., str]) -> APIRouter:
    router = APIRouter(prefix="/agenda", dependencies=[Depends(require_token)])

    def when_text(reminder: Reminder) -> str:
        local = service.local(reminder.fire_at)
        return f"{_WEEKDAYS[local.weekday()]}, {local:%d/%m} às {local:%H:%M}"

    def notice(reminder: Reminder) -> Aviso:
        return Aviso(id=reminder.id, quando=service.local(reminder.fire_at).isoformat(), quando_texto=when_text(reminder))

    def task_out(task: Task, reminders: list[Reminder]) -> TarefaOut:
        return TarefaOut(
            id=task.id,
            titulo=task.title,
            prazo=task.due.iso() if task.due else None,
            prazo_texto=task.due.human() if task.due else None,
            observacoes=task.notes,
            avisos=[notice(r) for r in reminders],
        )

    @router.get("", response_model=AgendaResponse)
    async def agenda() -> AgendaResponse:
        return AgendaResponse(
            tarefas=[task_out(task, reminders) for task, reminders in service.open_tasks()],
            lembretes=[
                LembreteOut(id=r.id, texto=r.text or "", quando=service.local(r.fire_at).isoformat(), quando_texto=when_text(r))
                for r in sorted(service.standalone_reminders(), key=lambda r: r.fire_at)
            ],
        )

    @router.post("/tarefas", response_model=TarefaOut, status_code=status.HTTP_201_CREATED)
    async def criar_tarefa(request: TarefaRequest) -> TarefaOut:
        try:
            due = Due.parse(request.prazo) if request.prazo else None
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Prazo inválido: use 2026-11-15 ou 2026-11-15T14:00.") from error
        if due is not None and due.deadline(service.now().tzinfo) < service.now():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"O prazo {due.human()} já passou.")
        task, reminders = service.create_task(" ".join(request.titulo.split()), due, request.observacoes.strip())
        return task_out(task, reminders)

    @router.post("/tarefas/{task_id}/concluir", status_code=status.HTTP_204_NO_CONTENT)
    async def concluir_tarefa(task_id: int) -> None:
        if service.complete_task(task_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não encontrada.")

    return router
