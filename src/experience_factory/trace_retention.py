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

from experience_factory.traces import SpanReference

if TYPE_CHECKING:
    from datetime import datetime

    from experience_factory.storage import PackageStore, TraceRetentionStore
    from experience_factory.traces import Traces


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
                span.number: span.event
                for span in self._traces.trace(end.task_id).spans
                if span.number in numbers
            }
            self._store.reduce_trace(end.task_id, kept)

    def _live_citations(self) -> defaultdict[str, set[int]]:
        """The span numbers that live Lessons Learned and Packages cite, by Task id."""
        cited: defaultdict[str, set[int]] = defaultdict(set)
        for package in self._packages.list_packages(None):
            if not package.is_live:
                continue
            for reference in package.evidence:
                if (span := SpanReference.parse(reference)) is not None:
                    cited[span.task_id].add(span.number)
        return cited
