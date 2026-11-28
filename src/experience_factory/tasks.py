"""Task boundaries: which Task a harness session belongs to, and when a Task ends.

A Harness Adapter reports each session it starts. The session joins the Task it declares it
continues if it declares one, otherwise the Task bound to its work item if there is one, otherwise
a new Task. Ending a Task is not final: a session that joins an ended Task reopens it, keeping its
id, work item and Predecessor Tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from experience_factory.clock import Clock
    from experience_factory.storage import TaskStore


class UnknownTaskError(LookupError):
    """The operation names a Task that does not exist (or, for a session's continuation or
    dependencies, not in the session's Project).

    A Task exists once a Harness Adapter's session opens it (ADR-0008), and every operation that
    names a Task raises this for one that does not.
    """


class TaskBoundaryError(Exception):
    """The core refused a Task boundary a Harness Adapter reported."""


class TaskNotOpenError(TaskBoundaryError, ValueError):
    """The operation needs an open Task, but the Task named has ended: ending it again, or handing
    over a Trace segment for it before a session reopens it."""


class ConflictingContinuationError(TaskBoundaryError, ValueError):
    """The session names a work item and declares it continues a Task, and the two disagree: the
    Task is bound to a different work item, or the work item already has a different Task (open or
    ended).

    Which of the two should win is not decided yet, so the session is refused. A session naming a
    work item with no Task may continue a Task with no work item: it joins that Task and binds the
    work item to it.
    """


class PredecessorsFixedError(TaskBoundaryError, ValueError):
    """The session joins or reopens an existing Task but declares dependencies. A Task's
    Predecessor Tasks are fixed when it first opens, so such a session cannot declare any
    (ADR-0007)."""


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

    def __init__(self, store: TaskStore, clock: Clock) -> None:
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
            return self._continue(self._task_in(project, continues_task), work_item, depends_on)
        if work_item is not None and (task := self._store.find_task_bound_to(project, work_item)):
            return self._join(task, depends_on)
        # A dependency declared twice is one Predecessor Task.
        predecessor_ids = [self._task_in(project, pid).id for pid in dict.fromkeys(depends_on)]
        task, opened = self._store.open_task(
            project, work_item=work_item, predecessor_ids=predecessor_ids
        )
        return task if opened else self._join(task, depends_on)

    def _continue(self, task: Task, work_item: str | None, depends_on: Sequence[str]) -> Task:
        """Join `task`, which the session declares it continues, binding `work_item` to it if the
        Task has no work item yet."""
        bind = None
        if work_item is not None and task.work_item != work_item:
            if task.work_item is not None:
                raise ConflictingContinuationError(
                    f"session names work item {work_item!r} but continues Task {task.id!r},"
                    f" which is bound to {task.work_item!r}"
                )
            if (bound := self._store.find_task_bound_to(task.project, work_item)) is not None:
                raise ConflictingContinuationError(
                    f"session names work item {work_item!r}, which is bound to Task"
                    f" {bound.id!r}, but continues Task {task.id!r}"
                )
            bind = work_item
        self._refuse_dependencies(task, depends_on)
        if task.is_open and bind is None:
            return task
        reopened = self._store.reopen_task(task.id, bind_work_item=bind)
        if reopened is None:
            raise ConflictingContinuationError(
                f"session names work item {work_item!r}, which another session has just bound to"
                f" a different Task, but continues Task {task.id!r}"
            )
        return reopened

    def _task_in(self, project: str, task_id: str) -> Task:
        task = self._store.find_task(task_id)
        if task is None or task.project != project:
            raise UnknownTaskError(f"no Task with id {task_id!r} in Project {project!r}")
        return task

    def _join(self, task: Task, depends_on: Sequence[str]) -> Task:
        """Join the existing `task`, reopening it if it has ended."""
        self._refuse_dependencies(task, depends_on)
        if task.is_open:
            return task
        reopened = self._store.reopen_task(task.id)
        assert reopened is not None, "reopening without binding a work item cannot conflict"
        return reopened

    def _refuse_dependencies(self, task: Task, depends_on: Sequence[str]) -> None:
        if depends_on:
            raise PredecessorsFixedError(
                f"session joins existing Task {task.id!r}, whose Predecessor Tasks were fixed"
                " when it first opened, but declares dependencies"
            )

    def end_task(self, task_id: str) -> None:
        written = self._store.end_task(task_id, ended_at=self._clock())
        require_written_to_open_task(
            self._store, task_id, written, ended=f"Task {task_id!r} has already ended"
        )

    def get_task(self, task_id: str) -> Task:
        return require_task(self._store, task_id)


def require_task(tasks: TaskStore, task_id: str) -> Task:
    """The Task with id `task_id`, or UnknownTaskError if there is none."""
    task = tasks.find_task(task_id)
    if task is None:
        raise UnknownTaskError(f"no Task with id {task_id!r}")
    return task


def require_written_to_open_task(
    tasks: TaskStore, task_id: str, written: bool, *, ended: str
) -> None:
    """Refuse a write the store makes only while the Task is open, unless it was `written`:
    UnknownTaskError if the Task does not exist, otherwise TaskNotOpenError saying `ended`.

    The store checks the Task is open atomically with the write, so the Task is looked up only to
    explain a refusal.
    """
    if not written:
        require_task(tasks, task_id)
        raise TaskNotOpenError(ended)
