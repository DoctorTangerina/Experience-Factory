"""Task boundaries: which Task a harness session belongs to, and when a Task ends.

A Harness Adapter reports each session it starts. The session joins the open Task bound to its
work item if there is one, otherwise the open Task it declares it continues, otherwise a new Task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from experience_factory.storage import TaskStore


class TaskBoundaryError(Exception):
    """The core refused a Task boundary a Harness Adapter reported."""


class NoSuchTaskError(TaskBoundaryError, LookupError):
    """The operation names a Task that does not exist (in the session's Project)."""


class TaskNotOpenError(TaskBoundaryError, ValueError):
    """The operation needs an open Task, but the Task named has ended."""


class ConflictingContinuationError(TaskBoundaryError, ValueError):
    """The session names a work item but declares it continues a Task bound to something else.

    Which of the two should win was never decided, so the session is refused.
    """


class PredecessorsFixedError(TaskBoundaryError, ValueError):
    """The session joins an open Task but declares dependencies. A Task's Predecessor Tasks are
    fixed when it opens, so a joining session cannot declare any."""


@dataclass(frozen=True)
class Task:
    """One unit of agent work in a Project, possibly spanning several harness sessions.

    `work_item` is the external work item the Task is bound to, if any. `predecessor_ids` are the
    ids of its Predecessor Tasks, in the order declared; they are fixed when the Task opens.
    """

    id: str
    project: str
    work_item: str | None
    is_open: bool
    predecessor_ids: tuple[str, ...] = ()


class TaskBoundaries:
    """Assigns sessions to Tasks and ends Tasks, enforcing the boundary rules before storing."""

    def __init__(self, store: TaskStore, clock: Callable[[], datetime]) -> None:
        self._store = store
        self._clock = clock

    def start_session(
        self,
        project: str,
        *,
        work_item: str | None,
        continues_task: str | None,
        depends_on: Sequence[str],
    ) -> Task:
        if continues_task is not None:
            task = self._task_in(project, continues_task)
            if not task.is_open:
                raise TaskNotOpenError(f"Task {task.id!r} has ended and cannot be continued")
            if work_item is not None and task.work_item != work_item:
                raise ConflictingContinuationError(
                    f"session names work item {work_item!r} but continues Task {task.id!r},"
                    f" which is bound to {task.work_item!r}"
                )
            return self._join(task, depends_on)
        # A dependency declared twice is one Predecessor Task.
        predecessor_ids = [self._task_in(project, pid).id for pid in dict.fromkeys(depends_on)]
        task, opened = self._store.join_or_open_task(
            project, work_item=work_item, predecessor_ids=predecessor_ids
        )
        return task if opened else self._join(task, depends_on)

    def _task_in(self, project: str, task_id: str) -> Task:
        task = self._store.find_task(task_id)
        if task is None or task.project != project:
            raise NoSuchTaskError(f"no Task with id {task_id!r} in Project {project!r}")
        return task

    def _join(self, task: Task, depends_on: Sequence[str]) -> Task:
        if depends_on:
            raise PredecessorsFixedError(
                f"session joins open Task {task.id!r}, whose Predecessor Tasks were fixed when it"
                " opened, but declares dependencies"
            )
        return task

    def end_task(self, task_id: str) -> None:
        if not self._store.end_task(task_id, ended_at=self._clock()):
            self.get_task(task_id)
            raise TaskNotOpenError(f"Task {task_id!r} has already ended")

    def get_task(self, task_id: str) -> Task:
        task = self._store.find_task(task_id)
        if task is None:
            raise NoSuchTaskError(f"no Task with id {task_id!r}")
        return task
