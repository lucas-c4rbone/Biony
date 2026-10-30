"""Tarefas com prazo, lembretes e o cálculo de quando avisar (sem banco, sem relógio)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Sequence

_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass(frozen=True)
class Due:
    """Prazo: um dia inteiro ("2026-11-15") ou um horário ("2026-11-15T14:00")."""

    day: date
    at: time | None = None

    @classmethod
    def parse(cls, text: str) -> Due:
        text = text.strip()
        if "T" in text or " " in text:
            moment = datetime.fromisoformat(text.replace(" ", "T"))
            return cls(moment.date(), moment.time().replace(second=0, microsecond=0, tzinfo=None))
        return cls(date.fromisoformat(text))

    def iso(self) -> str:
        return self.day.isoformat() if self.at is None else f"{self.day.isoformat()}T{self.at:%H:%M}"

    def deadline(self, tz: tzinfo) -> datetime:
        """Último instante do prazo. Sem horário, vale o dia todo."""
        return datetime.combine(self.day, self.at or time(23, 59), tz)

    def human(self) -> str:
        text = f"{_WEEKDAYS[self.day.weekday()]}, {self.day:%d/%m}"
        return text if self.at is None else f"{text} às {self.at:%H:%M}"


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    due: Due | None
    notes: str = ""
    done: bool = False


@dataclass(frozen=True)
class Reminder:
    id: int
    fire_at: datetime  # sempre com fuso
    task_id: int | None = None
    text: str | None = None
    attempts: int = 0
    pending: bool = True  # False depois de enviado ou cancelado


@dataclass(frozen=True)
class QuietHours:
    """Janela sem notificações automáticas (ex.: 22:30 → 07:00, atravessando a meia-noite)."""

    start: time
    end: time

    def contains(self, moment: datetime) -> bool:
        clock = moment.time().replace(tzinfo=None)
        if self.start <= self.end:
            return self.start <= clock < self.end
        return clock >= self.start or clock < self.end

    def shift(self, moment: datetime) -> datetime:
        """Empurra para o fim do silêncio um aviso que cairia dentro dele."""
        if not self.contains(moment):
            return moment
        end = moment.replace(hour=self.end.hour, minute=self.end.minute, second=0, microsecond=0)
        return end if end > moment else end + timedelta(days=1)


@dataclass(frozen=True)
class NoticePolicy:
    days_before: tuple[int, ...] = (3, 1, 0)
    at: time = time(9, 0)
    quiet: QuietHours = QuietHours(time(22, 30), time(7, 0))


def deadline_notices(
    due: Due, now: datetime, policy: NoticePolicy, days_before: Sequence[int] | None = None
) -> list[datetime]:
    """Quando avisar sobre um prazo: N dias antes no horário padrão, sem cair no silêncio.

    Avisos que já passaram ou que cairiam depois do prazo são descartados.
    """
    tz = now.tzinfo
    deadline = due.deadline(tz)
    notices: list[datetime] = []
    for days in sorted(set(policy.days_before if days_before is None else days_before), reverse=True):
        moment = datetime.combine(due.day - timedelta(days=days), policy.at, tz)
        if days == 0 and due.at is not None and moment > deadline - timedelta(hours=1):
            # Prazo de manhã cedo: avisa uma hora antes em vez de depois do prazo.
            moment = deadline - timedelta(hours=1)
        moment = policy.quiet.shift(moment)
        if now < moment < deadline and moment not in notices:
            notices.append(moment)
    return notices


def days_left_text(due: Due, today: date) -> str:
    days = (due.day - today).days
    if days < 0:
        return "já passou"
    if days == 0:
        return "é hoje"
    if days == 1:
        return "é amanhã"
    return f"faltam {days} dias"
