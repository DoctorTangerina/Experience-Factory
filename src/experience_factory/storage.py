"""The storage interface behind the core (ADR-0004: SQLite today, a server database possibly later).

Implementations only persist and retrieve; the rules of the GQM plan and of Data Packages are
enforced above this line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime, timedelta

    from experience_factory.data_packages import Characterization, DataPackageRecord
    from experience_factory.evidence_packs import EvidencePack
    from experience_factory.gqm import (
        ApprovalState,
        Goal,
        GoalStatement,
        GqmElement,
        Metric,
        MetricDefinition,
        Question,
    )
    from experience_factory.harness_adapters import HarnessCapability
    from experience_factory.packages import Package, PackageState, StateChange
    from experience_factory.tasks import Task
    from experience_factory.trace_retention import TaskEnd
    from experience_factory.traces import RetainedSpans, TraceEvent, TraceSegment


class GqmStore(Protocol):
    def add_organization_goal(self, statement: GoalStatement) -> Goal:
        """Store a new Organization Goal, approved (a human defined it)."""
        ...

    def add_project_goal(self, project: str, statement: GoalStatement) -> Goal:
        """Store a new Project Goal for `project`, proposed."""
        ...

    def add_goal_version(self, goal_id: str, statement: GoalStatement) -> Goal:
        """Store the next version of the Goal, keeping its level, Project and approval state."""
        ...

    def add_question(self, goal_id: str, *, text: str, state: ApprovalState) -> Question: ...

    def add_question_version(self, question_id: str, text: str) -> Question:
        """Store the next version of the Question, keeping its Goal and approval state."""
        ...

    def add_metric(
        self, question_id: str, *, name: str, definition: MetricDefinition, state: ApprovalState
    ) -> Metric: ...

    def get_metric(self, metric_id: str, version: int | None = None) -> Metric:
        """The given version of the Metric, or its latest version."""
        ...

    def add_metric_version(self, metric_id: str, definition: MetricDefinition) -> Metric:
        """Store the next version of the Metric, keeping its name, Question and approval state."""
        ...

    def approval_state(self, element: GqmElement, element_id: str) -> ApprovalState: ...

    def replace_approval_state(
        self, element: GqmElement, element_id: str, expected: ApprovalState, new: ApprovalState
    ) -> bool:
        """Set the element's approval state to `new` if it is still `expected`; say if it was."""
        ...

    def list_organization_goals(self) -> list[Goal]:
        """Approved Organization Goals with their approved Questions and Metrics, each at its
        latest version and in the order added. Questions and Metrics belong to their Goal or
        Question across its versions."""
        ...

    def list_project_goals_in_force(self, project: str) -> list[Goal]:
        """The project's approved Project Goals with their approved Questions and Metrics, each at
        its latest version and in the order added."""
        ...

    def list_metrics_in_force(self, question_id: str) -> list[Metric]:
        """The Question's approved Metrics (latest versions) in the order added, or none unless
        the Question and its Goal are approved."""
        ...

    def close(self) -> None: ...


class DataPackageStore(Protocol):
    def approval_state(self, element: GqmElement, element_id: str) -> ApprovalState: ...

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


class TaskStore(Protocol):
    def open_task(
        self, project: str, *, work_item: str | None, predecessor_ids: Sequence[str]
    ) -> tuple[Task, bool]:
        """A new open Task stored in `project` bound to `work_item` (to no work item if None) with
        the given Predecessor Tasks, and True. If a concurrent session has meanwhile given
        `work_item` its Task, that Task instead, reopened if it had ended, and False. Atomic: a
        work item has at most one Task in its Project, ever."""
        ...

    def find_task_bound_to(self, project: str, work_item: str) -> Task | None:
        """The Task in `project` bound to `work_item`, open or ended, or None if there is none."""
        ...

    def reopen_task(self, task_id: str, *, bind_work_item: str | None = None) -> Task | None:
        """Open the Task with id `task_id` again if it has ended (an open Task stays open), and
        bind it to `bind_work_item` if given (the Task must have no work item), then return it.
        Return None, changing nothing, if `bind_work_item` already has a Task in the Project."""
        ...

    def end_task(self, task_id: str, *, ended_at: datetime) -> bool:
        """End the Task with id `task_id` at `ended_at` if it is open, replacing the time it last
        ended if it was reopened; say if it was open."""
        ...

    def find_task(self, task_id: str) -> Task | None:
        """The Task with id `task_id`, or None if there is none."""
        ...


class HarnessAdapterStore(Protocol):
    def replace_harness_capabilities(
        self, adapter: str, capabilities: frozenset[HarnessCapability]
    ) -> None:
        """Store `capabilities` as the Harness Adapter's declaration, replacing any earlier one."""
        ...

    def harness_capabilities(self, adapter: str) -> frozenset[HarnessCapability]:
        """The capabilities the Harness Adapter last declared, or none if it never declared."""
        ...


class TraceStore(Protocol):
    def add_trace_segment(self, task_id: str, segment: TraceSegment) -> bool:
        """Store `segment`, already scrubbed, as the next segment of the Trace of the Task with id
        `task_id` if that Task is open; say if it was. Atomic with ending the Task. ADR-0004: the
        segment goes into a compressed file that the database references."""
        ...

    def trace_segments(self, task_id: str) -> list[TraceSegment]:
        """The Task's stored Trace segments, in the order they were added: since retention last
        reduced the Trace, if it has."""
        ...

    def retained_trace_spans(self, task_id: str) -> RetainedSpans | None:
        """What retention kept of the Task's Trace, or None if retention has not reduced it."""
        ...


class TraceRetentionStore(Protocol):
    def put_trace_retention_window(self, project: str, window: timedelta) -> None:
        """Store `window` as the Project's Trace retention window, replacing any earlier one."""
        ...

    def trace_retention_windows(self) -> dict[str, timedelta]:
        """Every Project's Trace retention window. A Project that never set one is missing."""
        ...

    def ended_tasks(self) -> list[TaskEnd]:
        """Every ended Task with its Project and the time it ended, in the order they opened."""
        ...

    def reduce_trace(self, task_id: str, kept: Mapping[int, TraceEvent], *, through: int) -> None:
        """Reduce the Task's Trace to the spans in `kept`, by span number: keep them in the
        database and delete the rest of the Trace, segment files included (ADR-0004). On a Trace
        already reduced, drop the retained spans missing from `kept`. `through` is the highest span
        number the Trace has had, which spans of later segments are numbered after."""
        ...


class EvidencePackStore(Protocol):
    def put_evidence_pack(self, task_id: str, pack: EvidencePack) -> None:
        """Store `pack` as the Evidence Pack of the existing Task with id `task_id`, open or ended,
        replacing any pack stored for it before."""
        ...

    def evidence_pack(self, task_id: str) -> EvidencePack | None:
        """The Task's stored Evidence Pack, or None if none was submitted."""
        ...


class PackageStore(Protocol):
    def get_goal(self, goal_id: str) -> Goal:
        """The latest version of the Goal, without its Questions."""
        ...

    def add_package(self, package: Package) -> None:
        """Store `package` with its state history. Nothing removes a stored Package."""
        ...

    def add_package_state(
        self, package_id: str, change: StateChange, superseded_by: str | None
    ) -> None:
        """Append `change` to the stored Package's state history and set the Package that
        replaced it (None unless it is now Superseded)."""
        ...

    def find_package(self, package_id: str) -> Package | None:
        """The Package with id `package_id`, or None if there is none."""
        ...

    def list_packages(self, state: PackageState | None) -> list[Package]:
        """The stored Packages in the given state (in any state if None), in the order stored."""
        ...


class Store(
    GqmStore,
    DataPackageStore,
    TaskStore,
    HarnessAdapterStore,
    TraceStore,
    TraceRetentionStore,
    EvidencePackStore,
    PackageStore,
    Protocol,
):
    """Everything the core persists."""
