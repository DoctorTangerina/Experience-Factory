"""Test support shared across the suite: an Experience Base that tests can arrange Packages in, the
Goal those Packages link to, and a fake Harness Adapter.

Only the Packager writes the Experience Base (ADR-0001), so the core public API cannot put a Package
into it. Tests that need Packages in some state before a Packager run arrange them through
`ArrangeableExperienceBase`, which exists only here.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

from experience_factory import (
    ApplicabilityScope,
    Clock,
    EvidencePack,
    ExperienceBase,
    Goal,
    HarnessCapability,
    Package,
    PackageState,
    PackageType,
    Provenance,
    Task,
    TraceSegment,
)
from experience_factory.clock import utc_now
from experience_factory.packages import ExperienceBasePackages
from experience_factory.sqlite_store import SqliteStore

PROJECT = "experience-factory"


class ArrangeableExperienceBase(ExperienceBase):
    """The Experience Base the core opens, plus a way to put Packages straight into it in any state,
    with the same checks a Package written by the Packager gets."""

    def __init__(self, store: SqliteStore, *, clock: Clock = utc_now) -> None:
        super().__init__(store, clock=clock)
        self._arranged_packages = ExperienceBasePackages(store)

    def arrange_package(
        self,
        state: PackageState = PackageState.LESSON_LEARNED,
        *,
        goal_ids: Iterable[str],
        type: PackageType = PackageType.PROCESS,
        title: str = "Run the failing test alone first",
        summary: str = "Rerun only the failing test before rerunning the suite.",
        content: str = "When a test fails, rerun it alone to see whether it is flaky.",
        scope: ApplicabilityScope | None = None,
        evidence: Iterable[str] = ("task-1#span-3",),
        provenance: Provenance | None = None,
        reason: str = "arranged by the test",
        superseded_by: str | None = None,
    ) -> Package:
        """Put a Package into the Experience Base in `state`, entered for `reason`, and return it.

        Each linked Goal must exist. A Superseded Package must name the existing Package that
        replaced it as `superseded_by`, and no other Package may name one.
        """
        return self._arranged_packages.add(
            type=type,
            state=state,
            title=title,
            summary=summary,
            content=content,
            scope=scope or ApplicabilityScope(project=PROJECT, attributes={}),
            goal_ids=goal_ids,
            evidence=evidence,
            provenance=provenance or Provenance(project=PROJECT, task_ids=("task-1",)),
            reason=reason,
            superseded_by=superseded_by,
        )

    def arrange_state_change(
        self,
        package_id: str,
        state: PackageState,
        *,
        reason: str = "arranged by the test",
        superseded_by: str | None = None,
    ) -> Package:
        """Move the Package with id `package_id` into `state`, entered for `reason`, and return it,
        with the same checks as a Package arranged in that state."""
        return self._arranged_packages.change_state(
            package_id, state, reason=reason, superseded_by=superseded_by
        )


def open_arrangeable_experience_base(
    path: Path | str, *, clock: Clock = utc_now
) -> ArrangeableExperienceBase:
    """Open (creating if needed) the Experience Base at `path`, as `open_experience_base` does."""
    return ArrangeableExperienceBase(SqliteStore(Path(path)), clock=clock)


def define_goal(experience_base: ExperienceBase) -> Goal:
    """Define an Organization Goal for Packages to link to."""
    return experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )


class FakeHarnessAdapter:
    """Drives the core the way a Harness Adapter does, using only the core public API: reports
    Task boundaries in its Project, hands over Traces, submits Evidence Packs and declares the
    capabilities of the adapter called `name`."""

    def __init__(
        self, experience_base: ExperienceBase, *, project: str = PROJECT, name: str = "fake-harness"
    ) -> None:
        self._experience_base = experience_base
        self._project = project
        self.name = name

    def start_session(
        self,
        *,
        work_item: str | None = None,
        continues: Task | None = None,
        depends_on: Sequence[Task] = (),
    ) -> Task:
        return self._experience_base.start_session(
            self._project,
            work_item=work_item,
            continues_task=None if continues is None else continues.id,
            depends_on=[task.id for task in depends_on],
        )

    def end_task(self, task: Task) -> None:
        self._experience_base.end_task(task.id)

    def hand_over(self, task: Task, segment: TraceSegment) -> None:
        """Hand over a segment already converted into the harness-neutral schema."""
        self._experience_base.hand_over_trace_segment(task.id, segment)

    def submit(self, task: Task, pack: EvidencePack) -> None:
        self._experience_base.submit_evidence_pack(task.id, pack)

    def declare(self, capabilities: Iterable[HarnessCapability]) -> None:
        self._experience_base.declare_harness_adapter(self.name, capabilities=capabilities)
