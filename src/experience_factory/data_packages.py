"""Data Packages: per-Task Metric values with the Task's measurement context (CONTEXT.md, DS-001).

Each record is one value of one Metric version for one Task, together with what is needed to
interpret it: the Metric's definition and kind, the Task's Characterization, the Goals selected
for the Task and whether the Task was a Holdout. Data Packages are never given to Project Agents.

The Task is the one its Harness Adapter's session opened. Its measurement context is its start
record, which the Advisor records against it while it is open for the first time (ADR-0008); only
Metric values need one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from experience_factory.gqm import (
    ApprovalState,
    Goal,
    GqmElement,
    Metric,
    MetricKind,
    is_blank,
)
from experience_factory.tasks import require_task

if TYPE_CHECKING:
    from experience_factory.storage import DataPackageStore, TaskStore


class DataPackageError(Exception):
    """The Data Package store refused an operation."""


class TaskStartAlreadyRecordedError(DataPackageError, ValueError):
    """The Task's start is already recorded. Its Characterization, Goals and Holdout assignment
    are fixed at start, so a start is recorded once."""


class TaskStartAfterEndError(DataPackageError, ValueError):
    """The Task's start was recorded after the Task had ended, even if it was reopened since. A
    start recorded then could leak the Task's Outcome into its condition (ADR-0006, ADR-0008)."""


class GoalOutsideProjectError(DataPackageError, ValueError):
    """A Task's start selects a Goal that is not a Project Goal of the Task's Project: an
    Organization Goal or another Project's Goal."""


class TaskStartNotRecordedError(DataPackageError, ValueError):
    """A Metric value was recorded for a Task whose start (its measurement context) was never
    recorded, so the value could not be interpreted."""


class DuplicateValueError(DataPackageError, ValueError):
    """The Task already has a value for this Metric version (one record per Task and version)."""


class UnapprovedMetricError(DataPackageError, ValueError):
    """A value was recorded for a Metric that is proposed or rejected, so was never in force."""


class MissingJudgeModelError(DataPackageError, ValueError):
    """A Judged Metric value was recorded without the model that actually produced it.

    A blank model (empty or whitespace only) counts as no model.
    """


type AttributeValue = str | frozenset[str]
"""A Characterization attribute holds a single value or a set of values."""


@dataclass(frozen=True)
class Characterization:
    """A Task's Characterization as fixed at Task start: attributes and their schema version."""

    schema_version: str
    attributes: Mapping[str, AttributeValue]

    def __post_init__(self) -> None:
        # Keep a private copy so a caller's later edits cannot reinterpret a recorded Task.
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True)
class DataPackageRecord:
    """One recorded value of one Metric version for one Task, with its measurement context.

    `goals` are the Goals selected for the Task, at the versions in force when it was recorded,
    without their Questions. `judged_by_model` is the model that actually produced a judged value.
    """

    task_id: str
    metric: Metric
    value: float
    judged_by_model: str | None
    characterization: Characterization
    goals: tuple[Goal, ...]
    holdout: bool


class DataPackages:
    """Records Task starts and Metric values, enforcing the Data Package rules before storing."""

    def __init__(self, store: DataPackageStore, tasks: TaskStore) -> None:
        self._store = store
        self._tasks = tasks

    def record_task_start(
        self,
        task_id: str,
        *,
        characterization: Characterization,
        goal_ids: Iterable[str],
        holdout: bool,
    ) -> None:
        task = require_task(self._tasks, task_id)
        goals = [self._project_goal(task.project, goal_id) for goal_id in goal_ids]
        # The store records the start only if the Task has never ended and has no start yet,
        # atomically with ending it; the Task is looked up again only to explain a refusal.
        if not self._store.add_task_start(
            task_id, characterization=characterization, goals=goals, holdout=holdout
        ):
            if self._store.has_task_start(task_id):
                raise TaskStartAlreadyRecordedError(f"Task {task_id!r} already has its start")
            raise TaskStartAfterEndError(
                f"Task {task_id!r} has ended, so its start can no longer be recorded"
            )

    def _project_goal(self, project: str, goal_id: str) -> Goal:
        goal = self._store.get_goal(goal_id)
        if self._store.goal_project(goal_id) != project:
            raise GoalOutsideProjectError(
                f"Goal {goal_id!r} is not a Project Goal of Project {project!r}"
            )
        return goal

    def record_metric_value(
        self,
        task_id: str,
        *,
        metric_id: str,
        metric_version: int,
        value: float,
        judged_by_model: str | None,
    ) -> None:
        require_task(self._tasks, task_id)
        if not self._store.has_task_start(task_id):
            raise TaskStartNotRecordedError(
                f"Task {task_id!r} has no recorded start, so its Metric values cannot be recorded"
            )
        metric = self._store.get_metric(metric_id, metric_version)
        # Only the Metric's own state counts: a Goal retired since the Task ran does not void it.
        state = self._store.approval_state(GqmElement.METRIC, metric_id)
        if state is not ApprovalState.APPROVED:
            raise UnapprovedMetricError(
                f"Metric {metric.name!r} is {state}; only an approved Metric's values are recorded"
            )
        if metric.definition.kind is MetricKind.JUDGED and is_blank(judged_by_model):
            raise MissingJudgeModelError(
                f"value of Judged Metric {metric.name!r} has no model that produced it"
            )
        self._store.add_metric_value(
            task_id,
            metric_id=metric_id,
            metric_version=metric_version,
            value=value,
            judged_by_model=judged_by_model,
        )

    def records(self) -> list[DataPackageRecord]:
        return self._store.list_data_package_records()
