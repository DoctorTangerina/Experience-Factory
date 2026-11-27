"""The core public API. Harness Adapters, the CLI and the tests all go through this object."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Self

from experience_memory.data_packages import Characterization, DataPackageRecord, DataPackages
from experience_memory.gqm import Goal, GqmPlan, Judge, Metric, MetricKind, Question
from experience_memory.sqlite_store import SqliteStore
from experience_memory.storage import Store


class ExperienceMemory:
    """One open Experience Base: the GQM plan, Data Packages and, later, everything else."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._plan = GqmPlan(store)
        self._data_packages = DataPackages(store)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # GQM plan

    def define_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        """Define a standing Organization Goal from the GQM template."""
        return self._plan.define_organization_goal(
            purpose=purpose, issue=issue, object=object, viewpoint=viewpoint
        )

    def add_question(self, goal_id: str, *, text: str) -> Question:
        """Refine the Goal with id `goal_id` by a Question."""
        return self._plan.add_question(goal_id, text=text)

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
        judge: Judge | None = None,
    ) -> Metric:
        """Answer the Question with id `question_id` by a Metric of the given kind.

        A Judged Metric must carry the rubric it is assessed against and the judge that assesses it.
        """
        return self._plan.add_metric(
            question_id, name=name, definition=definition, kind=kind, rubric=rubric, judge=judge
        )

    def redefine_metric(
        self,
        metric_id: str,
        *,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
        judge: Judge | None = None,
    ) -> Metric:
        """Change the definition of the Metric with id `metric_id`, creating its next version.

        The new definition is stated in full and checked like a new Metric; the name and Question
        carry over. Values already recorded stay attached to the version that measured them, and
        the GQM plan holds only the new version from now on.
        """
        return self._plan.redefine_metric(
            metric_id, definition=definition, kind=kind, rubric=rubric, judge=judge
        )

    def list_organization_goals(self) -> list[Goal]:
        """The Organization Goals with their Questions and Metrics, each in the order added.

        Each Metric appears at its latest version only.
        """
        return self._plan.list_organization_goals()

    # Data Packages

    def record_task(
        self,
        task_id: str,
        *,
        characterization: Characterization,
        goal_ids: Iterable[str],
        holdout: bool,
    ) -> None:
        """Record a Task's measurement context: its Characterization, Goals and Holdout assignment.

        All three are fixed at Task start, so a Task is recorded once. Each Goal is recorded at the
        version in force now.
        """
        self._data_packages.record_task(
            task_id, characterization=characterization, goal_ids=goal_ids, holdout=holdout
        )

    def record_metric_value(
        self,
        task_id: str,
        *,
        metric_id: str,
        metric_version: int,
        value: float,
        judged_by_model: str | None = None,
    ) -> None:
        """Record the value a Metric version measured for a recorded Task.

        A Judged Metric's value must name `judged_by_model`, the model that actually produced it.
        """
        self._data_packages.record_metric_value(
            task_id,
            metric_id=metric_id,
            metric_version=metric_version,
            value=value,
            judged_by_model=judged_by_model,
        )

    def data_package_records(self) -> list[DataPackageRecord]:
        """Every recorded Metric value with its measurement context, in the order recorded."""
        return self._data_packages.records()

    def export_data_packages(self, path: Path | str) -> None:
        """Write every Data Package record to a Parquet file at `path`, one row per value.

        Each row names the Metric version and kind and carries the Task's Characterization and
        schema version, its selected Goals and its Holdout assignment.
        """
        from experience_memory.data_package_export import write_parquet

        write_parquet(self._data_packages.records(), Path(path))


def open_memory(path: Path | str) -> ExperienceMemory:
    """Open (creating if needed) the Experience Base stored in the SQLite database at `path`."""
    return ExperienceMemory(SqliteStore(Path(path)))
