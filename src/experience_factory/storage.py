"""The storage interface behind the core (ADR-0004: SQLite today, a server database possibly later).

Implementations only persist and retrieve; the rules of the GQM plan and of Data Packages are
enforced above this line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    from experience_factory.tasks import Task
    from experience_factory.traces import TraceSegment


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
    def join_or_open_task(
        self, project: str, *, work_item: str | None, predecessor_ids: Sequence[str]
    ) -> tuple[Task, bool]:
        """The open Task in `project` bound to `work_item`, or else a new open Task stored bound
        to it (to no work item if None) with the given Predecessor Tasks; and whether the Task was
        opened by this call. Atomic: a work item has at most one open Task."""
        ...

    def end_task(self, task_id: str) -> bool:
        """End the Task with id `task_id` if it is open; say if it was."""
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
        """The Task's stored Trace segments, in the order they were added."""
        ...


class EvidencePackStore(Protocol):
    def put_evidence_pack(self, task_id: str, pack: EvidencePack) -> bool:
        """Store `pack` as the Evidence Pack of the Task with id `task_id` if that Task is open,
        replacing any pack stored for it before; say if it was. Atomic with ending the Task."""
        ...

    def evidence_pack(self, task_id: str) -> EvidencePack | None:
        """The Task's stored Evidence Pack, or None if none was submitted."""
        ...


class Store(
    GqmStore,
    DataPackageStore,
    TaskStore,
    HarnessAdapterStore,
    TraceStore,
    EvidencePackStore,
    Protocol,
):
    """Everything the core persists."""
