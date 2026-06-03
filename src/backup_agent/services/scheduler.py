"""Scheduler service for daily backup triggers."""

from __future__ import annotations

import time as time_module
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from threading import Event
from typing import Callable
from zoneinfo import ZoneInfo


class Scheduler(ABC):
    """Abstract scheduler contract."""

    @abstractmethod
    def schedule(self, callback: Callable[[], None]) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class DailyScheduler(Scheduler):
    """Internal daily scheduler driven by the configured backup time."""

    backup_time: time
    timezone: ZoneInfo
    clock: Callable[[], datetime] | None = None
    sleep: Callable[[float], None] = time_module.sleep
    _stop_event: Event = field(default_factory=Event, init=False, repr=False)

    def next_run_after(self, reference: datetime | None = None) -> datetime:
        """Compute the next execution time in the configured timezone."""

        current = reference if reference is not None else self._now()
        if current.tzinfo is None:
            raise ValueError("reference datetime must be timezone-aware")
        current = current.astimezone(self.timezone)
        scheduled_today = datetime.combine(current.date(), self.backup_time, self.timezone)
        if scheduled_today <= current:
            scheduled_today += timedelta(days=1)
        return scheduled_today

    def seconds_until_next_run(self, reference: datetime | None = None) -> float:
        """Return the delay in seconds until the next run."""

        current = reference if reference is not None else self._now()
        next_run = self.next_run_after(current)
        return max(0.0, (next_run - current.astimezone(self.timezone)).total_seconds())

    def schedule(self, callback: Callable[[], None]) -> None:
        """Run the callback every day at the configured time until stopped."""

        self._stop_event.clear()
        while not self._stop_event.is_set():
            current = self._now()
            delay = self.seconds_until_next_run(current)
            self.sleep(delay)
            if self._stop_event.is_set():
                break
            callback()

    def stop(self) -> None:
        """Stop the scheduler loop."""

        self._stop_event.set()

    def _now(self) -> datetime:
        if self.clock is not None:
            return self.clock()
        return datetime.now(self.timezone)
