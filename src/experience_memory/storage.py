"""The storage interface behind the core (ADR-0004: SQLite today, a server database possibly later).

Implementations only persist and retrieve; the rules of the GQM plan and of Data Packages are
enforced above this line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from experience_memory.data_packages import Characterization, DataPackageRecord
    from experience_memory.gqm import Goal, Judge, Metric, MetricKind, Question


class GqmStore(Protocol):
    def add_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal: ...

    def add_question(self, goal_id: str, *, text: str) -> Question: ...

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None,
        judge: Judge | None,
    ) -> Metric: ...

    def get_metric(self, metric_id: str, version: int | None = None) -> Metric:
        """The given version of the Metric, or its latest version."""
        ...

    def add_metric_version(
        self,
        metric_id: str,
        *,
        definition: str,
        kind: MetricKind,
        rubric: str | None,
        judge: Judge | None,
    ) -> Metric:
        """Store the next version of the Metric, keeping its name and Question."""
        ...

    def list_organization_goals(self) -> list[Goal]:
        """Organization Goals with their Questions and Metrics (latest versions), in order added."""
        ...

    def close(self) -> None: ...


class DataPackageStore(Protocol):
    def get_goal(self, goal_id: str) -> Goal:
        """The latest version of the Goal, without its Questions."""
        ...

    def add_task(
        self,
        task_id: str,
        *,
        characterization: Characterization,
        goals: Sequence[Goal],
        holdout: bool,
    ) -> None: ...

    def get_metric(self, metric_id: str, version: int | None = None) -> Metric:
        """The given version of the Metric, or its latest version."""
        ...

    def add_metric_value(
        self,
        task_id: str,
        *,
        metric_id: str,
        metric_version: int,
        value: float,
        judged_by_model: str | None,
    ) -> None: ...

    def list_data_package_records(self) -> list[DataPackageRecord]:
        """Every recorded Metric value with its context, in the order recorded."""
        ...


class Store(GqmStore, DataPackageStore, Protocol):
    """Everything the core persists."""
