from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from biony.adapters.sqlite_store import Database, SqliteReminderStore
from biony.core.reminder_service import MAX_ATTEMPTS, ReminderService
from biony.core.reminders import Due, NoticePolicy, QuietHours, days_left_text, deadline_notices

from conftest import TZ

pytestmark = pytest.mark.anyio

POLICY = NoticePolicy((3, 1, 0), time(9, 0), QuietHours(time(22, 30), time(7, 0)))


def at(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


# ------------------------------------------------------------------ cálculo puro


def test_due_parse_and_format():
    assert Due.parse("2026-11-15") == Due(date(2026, 11, 15))
    assert Due.parse("2026-11-15T14:30") == Due(date(2026, 11, 15), time(14, 30))
    assert Due.parse("2026-11-15 14:30").iso() == "2026-11-15T14:30"
    assert Due(date(2026, 11, 15), time(14, 30)).human() == "domingo, 15/11 às 14:30"
    with pytest.raises(ValueError):
        Due.parse("dia 15")


def test_quiet_hours_cross_midnight():
    quiet = POLICY.quiet
    assert quiet.contains(at(1, 23)) and quiet.contains(at(1, 3)) and quiet.contains(at(1, 22, 30))
    assert not quiet.contains(at(1, 7)) and not quiet.contains(at(1, 22, 29))
    assert quiet.shift(at(1, 23)) == at(2, 7)
    assert quiet.shift(at(2, 3)) == at(2, 7)
    assert quiet.shift(at(1, 12)) == at(1, 12)


def test_default_notices_three_one_and_same_day():
    notices = deadline_notices(Due(date(2026, 11, 15)), at(1, 12), POLICY)

    assert notices == [at(12, 9), at(14, 9), at(15, 9)]


def test_past_notices_are_dropped():
    # Prazo depois de amanhã: o aviso de 3 dias antes já passou.
    assert deadline_notices(Due(date(2026, 11, 3)), at(1, 12), POLICY) == [at(2, 9), at(3, 9)]


def test_early_deadline_warns_one_hour_before_and_respects_quiet_hours():
    assert deadline_notices(Due(date(2026, 11, 15), time(8, 30)), at(1, 12), POLICY)[-1] == at(15, 7, 30)
    # Prazo às 7h: uma hora antes cairia no silêncio e o fim do silêncio já é o prazo → sem aviso no dia.
    assert deadline_notices(Due(date(2026, 11, 15), time(7, 0)), at(1, 12), POLICY) == [at(12, 9), at(14, 9)]


def test_custom_days_and_quiet_default_time():
    late = NoticePolicy((1,), time(23, 0), POLICY.quiet)

    assert deadline_notices(Due(date(2026, 11, 15)), at(1, 12), late) == [at(15, 7)]
    assert deadline_notices(Due(date(2026, 11, 15)), at(1, 12), POLICY, days_before=[7]) == [at(8, 9)]


def test_days_left_text():
    due = Due(date(2026, 11, 15))
    assert days_left_text(due, date(2026, 11, 15)) == "é hoje"
    assert days_left_text(due, date(2026, 11, 14)) == "é amanhã"
    assert days_left_text(due, date(2026, 11, 12)) == "faltam 3 dias"


# ------------------------------------------------------------------ serviço


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[int, datetime] = {}

    def schedule(self, reminder_id: int, when: datetime) -> None:
        self.jobs[reminder_id] = when

    def cancel(self, reminder_id: int) -> None:
        self.jobs.pop(reminder_id, None)


class FakeNotifier:
    def __init__(self, fail: int = 0) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send(self, text: str) -> None:
        if self.fail:
            self.fail -= 1
            raise RuntimeError("sem internet")
        self.sent.append(text)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self, tz) -> datetime:
        return self.now.astimezone(tz)


@pytest.fixture
def parts():
    store = SqliteReminderStore(Database(":memory:"))
    scheduler, notifier, clock = FakeScheduler(), FakeNotifier(), Clock(at(1, 12))
    service = ReminderService(store, scheduler, notifier, timezone=TZ, policy=POLICY, clock=clock)
    return service, store, scheduler, notifier, clock


async def test_task_with_due_schedules_and_fires(parts):
    service, store, scheduler, notifier, clock = parts

    task, reminders = service.create_task("Trabalho de Cálculo", Due(date(2026, 11, 15)), "em dupla")

    assert sorted(scheduler.jobs.values()) == [at(12, 9), at(14, 9), at(15, 9)]
    clock.now = at(14, 9)
    await service.fire(reminders[1].id)
    assert notifier.sent == ["📌 Trabalho de Cálculo: o prazo é amanhã (domingo, 15/11).\nem dupla"]
    assert not store.get_reminder(reminders[1].id).pending

    await service.fire(reminders[1].id)  # disparo duplicado não reenvia
    assert len(notifier.sent) == 1


async def test_completing_task_cancels_remaining_notices(parts):
    service, store, scheduler, notifier, clock = parts
    task, reminders = service.create_task("Prova", Due(date(2026, 11, 15)))

    assert service.complete_task(task.id).title == "Prova"

    assert scheduler.jobs == {}
    assert store.pending_reminders() == []
    assert service.open_tasks() == []
    await service.fire(reminders[0].id)
    assert notifier.sent == []
    assert service.complete_task(task.id) is None


async def test_delete_task_and_cancel_reminder(parts):
    service, store, scheduler, _, _ = parts
    task, _ = service.create_task("Errada", Due(date(2026, 11, 15)))
    reminder = service.create_reminder("varal", at(1, 18))

    assert service.delete_task(task.id) is not None
    assert service.get_task(task.id) is None
    assert service.cancel_reminder(reminder.id)
    assert not service.cancel_reminder(reminder.id)
    assert scheduler.jobs == {}


async def test_explicit_reminder_keeps_quiet_time_and_rejects_past(parts):
    service, _, scheduler, notifier, clock = parts

    reminder = service.create_reminder("tomar remédio", at(1, 23))

    assert scheduler.jobs[reminder.id] == at(1, 23)
    with pytest.raises(ValueError):
        service.create_reminder("ontem", at(1, 11))
    clock.now = at(1, 23)
    await service.fire(reminder.id)
    assert notifier.sent == ["⏰ Lembrete: tomar remédio"]


async def test_failed_send_retries_then_gives_up(parts):
    service, store, scheduler, notifier, clock = parts
    notifier.fail = MAX_ATTEMPTS
    reminder = service.create_reminder("x", at(1, 13))
    clock.now = at(1, 13)

    for _ in range(MAX_ATTEMPTS):
        await service.fire(reminder.id)

    assert notifier.sent == []
    assert store.get_reminder(reminder.id).attempts == MAX_ATTEMPTS
    assert scheduler.jobs[reminder.id] == at(1, 13) + timedelta(minutes=5)  # do penúltimo retry
    assert store.get_reminder(reminder.id).pending  # continua salvo, não some


async def test_restore_reschedules_pending_and_marks_late(parts):
    service, store, _, notifier, clock = parts
    store.add_reminder(at(1, 8), text="atrasado")
    store.add_reminder(at(2, 8), text="futuro")
    fresh = FakeScheduler()
    service = ReminderService(store, fresh, notifier, timezone=TZ, policy=POLICY, clock=clock)

    assert service.restore() == 2

    assert sorted(fresh.jobs.values()) == [at(1, 12) + timedelta(seconds=5), at(2, 8)]
    await service.fire(1)
    assert "atrasado: o Biony estava fora do ar" in notifier.sent[0]


async def test_without_notifier_reminder_stays_pending(parts):
    _, store, scheduler, _, clock = parts
    service = ReminderService(store, scheduler, None, timezone=TZ, policy=POLICY, clock=clock)
    reminder = service.create_reminder("x", at(1, 13))

    await service.fire(reminder.id)

    assert store.get_reminder(reminder.id).pending


def test_open_tasks_sorted_by_due(parts):
    service = parts[0]
    service.create_task("sem prazo", None)
    service.create_task("depois", Due(date(2026, 11, 20)))
    service.create_task("antes", Due(date(2026, 11, 5)))

    assert [task.title for task, _ in service.open_tasks()] == ["antes", "depois", "sem prazo"]
