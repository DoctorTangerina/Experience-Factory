"""Data Packages: per-Task Metric values with the Task's measurement context (CONTEXT.md, DS-001).

Each record is one value of one Metric version for one Task, together with what is needed to
interpret it: the Metric's definition and kind, the Task's Characterization, the Goals selected
for the Task and whether the Task was a Holdout. Data Packages are never given to Project Agents.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from experience_memory.gqm import Goal, Metric, MetricKind, is_blank

if TYPE_CHECKING:
    from experience_memory.storage import DataPackageStore


class DataPackageError(Exception):
    """The Data Package store refused an operation."""


class UnknownTaskError(DataPackageError, LookupError):
    """The operation names a Task that has not been recorded."""


class DuplicateTaskError(DataPackageError, ValueError):
    """The Task is already recorded. Its Characterization, Goals and Holdout are fixed at start."""


class DuplicateValueError(DataPackageError, ValueError):
    """The Task already has a value for this Metric version (one record per Task and version)."""


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
    """Records Task context and Metric values, enforcing the Data Package rules before storing."""

    def __init__(self, store: DataPackageStore) -> None:
        self._store = store

    def record_task(
        self,
        task_id: str,
        *,
        characterization: Characterization,
        goal_ids: Iterable[str],
        holdout: bool,
    ) -> None:
        goals = [self._store.get_goal(goal_id) for goal_id in goal_ids]
        self._store.add_task(
            task_id, characterization=characterization, goals=goals, holdout=holdout
        )

    def record_metric_value(
        self,
        task_id: str,
        *,
        metric_id: str,
        metric_version: int,
        value: float,
        judged_by_model: str | None,
    ) -> None:
        metric = self._store.get_metric(metric_id, metric_version)
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
