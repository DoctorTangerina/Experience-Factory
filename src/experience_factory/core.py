"""The core public API. Harness Adapters, the CLI and the tests all go through this object."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

from experience_factory.data_packages import Characterization, DataPackageRecord, DataPackages
from experience_factory.gqm import (
    ApprovalState,
    Goal,
    GoalStatement,
    GqmElement,
    GqmPlan,
    Judge,
    Metric,
    MetricDefinition,
    MetricKind,
    Question,
)
from experience_factory.harness_adapters import (
    HarnessAdapters,
    HarnessCapabilities,
    HarnessCapability,
)
from experience_factory.sqlite_store import SqliteStore
from experience_factory.storage import Store
from experience_factory.tasks import Task, TaskBoundaries


class ExperienceBase:
    """One open Experience Base: the GQM plan, Data Packages and, later, everything else."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._plan = GqmPlan(store)
        self._data_packages = DataPackages(store)
        self._task_boundaries = TaskBoundaries(store)
        self._harness_adapters = HarnessAdapters(store)

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
            GoalStatement(purpose=purpose, issue=issue, object=object, viewpoint=viewpoint)
        )

    def propose_project_goal(
        self, project: str, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        """Propose a Project Goal for `project` from the GQM template (the Experience Factory's
        operation). It waits for a human to approve or reject it, and is not selectable until
        approved."""
        return self._plan.propose_project_goal(
            project,
            GoalStatement(purpose=purpose, issue=issue, object=object, viewpoint=viewpoint),
        )

    def approve_goal(self, goal_id: str) -> None:
        """Approve the proposed Goal with id `goal_id`, putting it in force."""
        self._plan.change_approval_state(GqmElement.GOAL, goal_id, ApprovalState.APPROVED)

    def reject_goal(self, goal_id: str) -> None:
        """Reject the proposed Goal with id `goal_id`. A rejected Goal is never in force."""
        self._plan.change_approval_state(GqmElement.GOAL, goal_id, ApprovalState.REJECTED)

    def retire_goal(self, goal_id: str) -> None:
        """Retire the approved Goal with id `goal_id`, taking it out of force for good.

        Tasks stop selecting it. Data already recorded under it stays in the Data Packages.
        """
        self._plan.change_approval_state(GqmElement.GOAL, goal_id, ApprovalState.RETIRED)

    def redefine_goal(
        self, goal_id: str, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        """Change what the Goal with id `goal_id` states, creating its next version (a human's
        operation).

        The new version keeps the Goal's approval state and its Questions. A Task recorded before
        keeps the version it selected. A rejected or retired Goal cannot be redefined.
        """
        return self._plan.redefine_goal(
            goal_id,
            GoalStatement(purpose=purpose, issue=issue, object=object, viewpoint=viewpoint),
        )

    def selectable_project_goals(self, project: str) -> list[Goal]:
        """The Project Goals in force for `project`, in the order proposed: approved and not
        retired, each with its Questions and Metrics in force."""
        return self._plan.selectable_project_goals(project)

    def add_question(self, goal_id: str, *, text: str) -> Question:
        """Refine the Goal with id `goal_id` by a Question, in force at once (a human added it)."""
        return self._plan.add_question(goal_id, text=text)

    def propose_question(self, goal_id: str, *, text: str) -> Question:
        """Propose a Question refining the Goal with id `goal_id` (the Analyst's operation).

        It is not in force until a human approves it.
        """
        return self._plan.add_question(goal_id, text=text, state=ApprovalState.PROPOSED)

    def approve_question(self, question_id: str) -> None:
        """Approve the proposed Question with id `question_id`, putting it in force."""
        self._plan.change_approval_state(GqmElement.QUESTION, question_id, ApprovalState.APPROVED)

    def reject_question(self, question_id: str) -> None:
        """Reject the proposed Question with id `question_id`. It is never in force."""
        self._plan.change_approval_state(GqmElement.QUESTION, question_id, ApprovalState.REJECTED)

    def redefine_question(self, question_id: str, *, text: str) -> Question:
        """Change the text of the Question with id `question_id`, creating its next version (a
        human's operation).

        The new version keeps the Question's approval state and its Metrics. A rejected Question
        cannot be redefined.
        """
        return self._plan.redefine_question(question_id, text)

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
        """Answer the Question with id `question_id` by a Metric of the given kind, in force at
        once (a human added it).

        A Judged Metric must carry the rubric it is assessed against and the judge that assesses it.
        """
        return self._plan.add_metric(
            question_id,
            name=name,
            definition=MetricDefinition(text=definition, kind=kind, rubric=rubric, judge=judge),
        )

    def propose_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
        judge: Judge | None = None,
    ) -> Metric:
        """Propose a Metric answering the Question with id `question_id` (the Analyst's
        operation). It is checked like an added Metric, and not in force until a human approves
        it."""
        return self._plan.add_metric(
            question_id,
            name=name,
            definition=MetricDefinition(text=definition, kind=kind, rubric=rubric, judge=judge),
            state=ApprovalState.PROPOSED,
        )

    def approve_metric(self, metric_id: str) -> None:
        """Approve the proposed Metric with id `metric_id`, putting it in force."""
        self._plan.change_approval_state(GqmElement.METRIC, metric_id, ApprovalState.APPROVED)

    def reject_metric(self, metric_id: str) -> None:
        """Reject the proposed Metric with id `metric_id`. It is never in force."""
        self._plan.change_approval_state(GqmElement.METRIC, metric_id, ApprovalState.REJECTED)

    def metrics_in_force(self, question_id: str) -> list[Metric]:
        """The Metrics in force for the Question with id `question_id`, at their latest versions
        in the order added: the approved ones, and none unless the Question and its Goal are in
        force too. These are the Metrics the Analyst extracts."""
        return self._plan.metrics_in_force(question_id)

    def redefine_metric(
        self,
        metric_id: str,
        *,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
        judge: Judge | None = None,
    ) -> Metric:
        """Change the definition of the Metric with id `metric_id`, creating its next version (a
        human's operation).

        The new definition is stated in full and checked like a new Metric; the name, Question and
        approval state carry over. Values already recorded stay attached to the version that
        measured them, and the GQM plan holds only the new version from now on. A rejected Metric
        cannot be redefined.
        """
        return self._plan.redefine_metric(
            metric_id, MetricDefinition(text=definition, kind=kind, rubric=rubric, judge=judge)
        )

    def list_organization_goals(self) -> list[Goal]:
        """The Organization Goals in force with their Questions and Metrics in force, each in the
        order added.

        Each Metric appears at its latest version only.
        """
        return self._plan.list_organization_goals()

    # Task boundaries (the Harness Adapter's operations)

    def start_session(
        self,
        project: str,
        *,
        work_item: str | None = None,
        continues_task: str | None = None,
        depends_on: Sequence[str] = (),
    ) -> Task:
        """Assign a harness session starting in `project` to its Task, and return that Task.

        The session continues `continues_task` if it declares one (which must be open in
        `project`), otherwise the open Task bound to `work_item`, otherwise it opens a new Task
        bound to `work_item` (to none if None). A session naming a work item may only continue the
        Task bound to that work item.

        `depends_on` names the Predecessor Tasks of a new Task, earlier Tasks in `project`. They are
        fixed when the Task opens, so a session that joins an open Task cannot declare any.
        """
        return self._task_boundaries.start_session(
            project, work_item=work_item, continues_task=continues_task, depends_on=depends_on
        )

    def end_task(self, task_id: str) -> None:
        """End the open Task with id `task_id`. A later session on its work item starts a new
        Task."""
        self._task_boundaries.end_task(task_id)

    def get_task(self, task_id: str) -> Task:
        """The Task with id `task_id`."""
        return self._task_boundaries.get_task(task_id)

    # Harness Adapter capabilities

    def declare_harness_adapter(
        self, adapter: str, *, capabilities: Iterable[HarnessCapability]
    ) -> None:
        """Record which optional capabilities the Harness Adapter named `adapter` supports (the
        Harness Adapter's operation). Every capability left out is unsupported.

        A later declaration replaces the earlier one, so an adapter can gain or drop capabilities.
        """
        self._harness_adapters.declare(adapter, capabilities)

    def harness_adapter_capabilities(self, adapter: str) -> HarnessCapabilities:
        """The optional capabilities the Harness Adapter named `adapter` last declared (what the
        Advisor reads to adapt delivery). An adapter that never declared supports none."""
        return self._harness_adapters.capabilities(adapter)

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

        The Metric must be approved; any of its versions may be recorded, since the Task may have
        run before a redefinition. A Judged Metric's value must name `judged_by_model`, the model
        that actually produced it.
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
        from experience_factory.data_package_export import write_parquet

        write_parquet(self._data_packages.records(), Path(path))


def open_experience_base(path: Path | str) -> ExperienceBase:
    """Open (creating if needed) the Experience Base stored in the SQLite database at `path`."""
    return ExperienceBase(SqliteStore(Path(path)))
