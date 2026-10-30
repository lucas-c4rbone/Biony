"""Cria tarefas e lembretes, agenda os avisos e dispara as notificações."""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
import logging
from typing import Callable, Sequence

from biony.core.ports import Notifier, ReminderStore, Scheduler
from biony.core.reminders import Due, NoticePolicy, Reminder, Task, days_left_text, deadline_notices

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)
LATE_AFTER = timedelta(minutes=10)


class ReminderService:
    def __init__(
        self,
        store: ReminderStore,
        scheduler: Scheduler,
        notifier: Notifier | None,
        *,
        timezone: tzinfo,
        policy: NoticePolicy = NoticePolicy(),
        clock: Callable[[tzinfo], datetime] = datetime.now,
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._notifier = notifier
        self._tz = timezone
        self.policy = policy
        self._clock = clock

    def now(self) -> datetime:
        return self._clock(self._tz)

    # ------------------------------------------------------------- criação

    def create_task(
        self, title: str, due: Due | None, notes: str = "", days_before: Sequence[int] | None = None
    ) -> tuple[Task, list[Reminder]]:
        task = self._store.add_task(title, due, notes)
        reminders = []
        if due is not None:
            for moment in deadline_notices(due, self.now(), self.policy, days_before):
                reminders.append(self._add(moment, task_id=task.id))
        return task, reminders

    def create_reminder(self, text: str, when: datetime) -> Reminder:
        """Lembrete com horário explícito: respeita o horário pedido, mesmo no silêncio."""
        if when <= self.now():
            raise ValueError("esse horário já passou")
        return self._add(when, text=text)

    def _add(self, moment: datetime, task_id: int | None = None, text: str | None = None) -> Reminder:
        reminder = self._store.add_reminder(moment, task_id=task_id, text=text)
        self._scheduler.schedule(reminder.id, reminder.fire_at)
        return reminder

    # ------------------------------------------------------------- mudanças

    def complete_task(self, task_id: int) -> Task | None:
        task = self._store.get_task(task_id)
        if task is None or not self._store.complete_task(task_id):
            return None
        self._cancel_task_reminders(task_id)
        return task

    def delete_task(self, task_id: int) -> Task | None:
        task = self._store.get_task(task_id)
        if task is None or not self._store.delete_task(task_id):
            return None
        self._cancel_task_reminders(task_id)
        return task

    def cancel_reminder(self, reminder_id: int) -> bool:
        if not self._store.cancel_reminder(reminder_id):
            return False
        self._scheduler.cancel(reminder_id)
        return True

    def _cancel_task_reminders(self, task_id: int) -> None:
        for reminder in self._store.pending_reminders(task_id):
            self._scheduler.cancel(reminder.id)
        self._store.cancel_task_reminders(task_id)

    # ------------------------------------------------------------- consulta

    def open_tasks(self) -> list[tuple[Task, list[Reminder]]]:
        far = self.now().date().replace(year=9999)
        tasks = sorted(self._store.open_tasks(), key=lambda t: (t.due.day if t.due else far, t.id))
        return [(task, self._store.pending_reminders(task.id)) for task in tasks]

    def standalone_reminders(self) -> list[Reminder]:
        return [r for r in self._store.pending_reminders() if r.task_id is None]

    def get_task(self, task_id: int) -> Task | None:
        return self._store.get_task(task_id)

    def get_reminder(self, reminder_id: int) -> Reminder | None:
        return self._store.get_reminder(reminder_id)

    def local(self, moment: datetime) -> datetime:
        return moment.astimezone(self._tz)

    # ------------------------------------------------------------- disparo

    def restore(self) -> int:
        """Reagenda tudo o que está pendente no banco (chamado ao ligar o servidor)."""
        pending = self._store.pending_reminders()
        soon = self.now() + timedelta(seconds=5)
        for reminder in pending:
            # O que venceu com o servidor desligado sai logo, marcado como atrasado.
            self._scheduler.schedule(reminder.id, max(reminder.fire_at, soon))
        return len(pending)

    async def fire(self, reminder_id: int) -> None:
        reminder = self._store.get_reminder(reminder_id)
        if reminder is None or not reminder.pending:
            return  # já enviado ou cancelado
        text = self._message(reminder)
        if text is None:
            self._store.cancel_reminder(reminder.id)
            return
        if self._notifier is None:
            log.error("Lembrete %d venceu, mas não há notificador configurado (Telegram): %s", reminder.id, text)
            return
        try:
            await self._notifier.send(text)
        except Exception:
            attempts = self._store.record_failure(reminder.id)
            if attempts < MAX_ATTEMPTS:
                log.exception("Falha ao enviar o lembrete %d (tentativa %d); tento de novo em 5 min.", reminder.id, attempts)
                self._scheduler.schedule(reminder.id, self.now() + RETRY_AFTER)
            else:
                log.exception("Lembrete %d não foi enviado após %d tentativas.", reminder.id, attempts)
            return
        self._store.mark_sent(reminder.id)
        log.info("Lembrete %d enviado.", reminder.id)

    def _message(self, reminder: Reminder) -> str | None:
        now = self.now()
        late = " (atrasado: o Biony estava fora do ar)" if now - reminder.fire_at > LATE_AFTER else ""
        if reminder.task_id is None:
            return f"⏰ Lembrete: {reminder.text}{late}"
        task = self._store.get_task(reminder.task_id)
        if task is None or task.done or task.due is None:
            return None
        text = f"📌 {task.title}: o prazo {days_left_text(task.due, now.date())} ({task.due.human()}).{late}"
        return f"{text}\n{task.notes}" if task.notes else text
