"""Agendador em memória com APScheduler. O banco é a fonte da verdade: ao ligar, tudo é reagendado."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger


class APSchedulerScheduler:
    def __init__(self, callback: Callable[[int], Awaitable[None]] | None = None) -> None:
        self._scheduler = AsyncIOScheduler()
        self.callback = callback

    def start(self) -> None:
        """Precisa rodar com o event loop já ativo (no lifespan do FastAPI)."""
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def schedule(self, reminder_id: int, at: datetime) -> None:
        if self.callback is None:
            raise RuntimeError("Defina o callback antes de agendar.")
        self._scheduler.add_job(
            self.callback,
            DateTrigger(run_date=at),
            args=(reminder_id,),
            id=_job_id(reminder_id),
            replace_existing=True,
            # Se o servidor engasgar, dispara atrasado em vez de pular o lembrete.
            misfire_grace_time=None,
        )

    def cancel(self, reminder_id: int) -> None:
        try:
            self._scheduler.remove_job(_job_id(reminder_id))
        except JobLookupError:
            pass

    def scheduled_ids(self) -> set[int]:
        return {int(job.id.removeprefix("lembrete-")) for job in self._scheduler.get_jobs()}


def _job_id(reminder_id: int) -> str:
    return f"lembrete-{reminder_id}"
