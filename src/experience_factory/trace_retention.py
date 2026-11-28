"""Trace retention: a Project keeps its Traces whole only for its retention window (#16, BS-003).

A Trace's age counts from the end of its Task, since a Task's Trace grows until then. Applying
retention reduces every Trace older than its Project's window to the spans cited by live Lessons
Learned or Packages, and removes the rest. The Task's extracted Metrics and Evidence Pack are not
part of the Trace, so retention keeps them.

The default window is deferred (docs/pending-decisions.md, Numeric parameters): until a Project
sets one, its Traces are kept whole.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from experience_factory.packages import PackageState
from experience_factory.traces import parse_span_reference

if TYPE_CHECKING:
    from datetime import datetime

    from experience_factory.storage import PackageStore, TraceRetentionStore
    from experience_factory.traces import Traces, TraceSpan

LIVE_STATES = frozenset(
    {PackageState.LESSON_LEARNED, PackageState.CANDIDATE, PackageState.VALIDATED}
)
"""The states of a live Lesson Learned or Package: those not Retired or Superseded."""


class InvalidRetentionWindowError(ValueError):
    """A Project's Trace retention window was set to a negative duration."""


@dataclass(frozen=True)
class TaskEnd:
    """An ended Task: its Project and when it ended."""

    task_id: str
    project: str
    ended_at: datetime


class TraceRetention:
    """Holds each Project's retention window and applies it to the stored Traces."""

    def __init__(self, store: TraceRetentionStore, packages: PackageStore, traces: Traces) -> None:
        self._store = store
        self._packages = packages
        self._traces = traces

    def set_window(self, project: str, window: timedelta) -> None:
        if window < timedelta(0):
            raise InvalidRetentionWindowError(
                f"a Trace retention window cannot be negative, got {window}"
            )
        self._store.put_trace_retention_window(project, window)

    def window(self, project: str) -> timedelta | None:
        return self._store.trace_retention_windows().get(project)

    def apply(self, now: datetime) -> None:
        windows = self._store.trace_retention_windows()
        cited = self._live_citations()
        for end in self._store.ended_tasks():
            window = windows.get(end.project)
            if window is None or now - end.ended_at <= window:
                continue
            numbers = cited[end.task_id]
            kept = {
                number: span.event
                for number, span in _numbered(self._traces.trace(end.task_id).spans)
                if number in numbers
            }
            self._store.reduce_trace(end.task_id, kept)

    def _live_citations(self) -> defaultdict[str, set[int]]:
        """The span numbers that live Lessons Learned and Packages cite, by Task id."""
        cited: defaultdict[str, set[int]] = defaultdict(set)
        for package in self._packages.list_packages(None):
            if package.state not in LIVE_STATES:
                continue
            for reference in package.evidence:
                if (span := parse_span_reference(reference)) is not None:
                    task_id, number = span
                    cited[task_id].add(number)
        return cited


def _numbered(spans: tuple[TraceSpan, ...]) -> list[tuple[int, TraceSpan]]:
    numbered: list[tuple[int, TraceSpan]] = []
    for span in spans:
        parsed = parse_span_reference(span.reference)
        assert parsed is not None
        numbered.append((parsed[1], span))
    return numbered
