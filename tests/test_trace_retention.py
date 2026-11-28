"""BS-003 and Trace retention: each Project sets a Trace retention window, and applying retention
reduces Traces past it to the spans cited by live Lessons Learned or Packages. Driven through the
core public API, the way a Harness Adapter and the scheduled timer would."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from experience_factory import (
    ApplicabilityScope,
    Characterization,
    Claim,
    EvidenceItem,
    EvidencePack,
    ExperienceBase,
    Goal,
    InvalidRetentionWindowError,
    Manifest,
    MetricKind,
    Package,
    PackageState,
    PackageType,
    PlanLedger,
    Prompt,
    Provenance,
    Rationale,
    RisksAndAssumptions,
    Task,
    ToolCall,
    TraceError,
    TraceSegment,
    open_experience_base,
)

PROJECT = "experience-factory"
WINDOW = timedelta(days=30)

SEGMENT = TraceSegment(
    events=(
        Prompt("Fix the flaky test in tests/test_io.py"),
        ToolCall(tool="bash", arguments={"command": "pytest tests/test_io.py"}, result="1 failed"),
        TraceError("pytest exited with status 1"),
    ),
    end_state="completed",
)

PACK = EvidencePack(
    claims=(
        Claim(
            id="CLM-001",
            requirement="The flaky test passes",
            status="PASS",
            evidence_ids=("EVD-001",),
            source="issue #1",
            verification="pytest tests/test_io.py",
        ),
    ),
    plan=PlanLedger(
        conceptual_plan="Rerun the test alone, then fix the race",
        executed_approach="Reran the test alone, then fixed the race",
        deviations=(),
    ),
    rationale=Rationale(approach_taken="Fix the race", rejected_alternatives=(), trade_offs=()),
    exploration_archive=(),
    risks=RisksAndAssumptions(risks=(), assumptions=()),
    manifest=Manifest(
        overall_status="PASS",
        producer="claude-code",
        evidence=(
            EvidenceItem(
                id="EVD-001",
                category="test",
                status="PASS",
                claim_ids=("CLM-001",),
                command="uv run pytest tests/test_io.py",
                exit_code=0,
            ),
        ),
    ),
)


class FakeClock:
    """The time the core reads, moved forward by the test."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def experience_base(db_path: Path, clock: FakeClock) -> Iterator[ExperienceBase]:
    with open_experience_base(db_path, clock=clock) as opened:
        yield opened


class FakeHarnessAdapter:
    """Runs a Task the way a Harness Adapter does, using only the core public API."""

    def __init__(self, experience_base: ExperienceBase) -> None:
        self._experience_base = experience_base

    def run_task(
        self, project: str = PROJECT, segments: tuple[TraceSegment, ...] = (SEGMENT,)
    ) -> Task:
        """Start a session, hand over its Trace segments and Evidence Pack, and end the Task."""
        task = self.start_task(project, segments)
        self._experience_base.end_task(task.id)
        return task

    def start_task(
        self, project: str = PROJECT, segments: tuple[TraceSegment, ...] = (SEGMENT,)
    ) -> Task:
        """Start a session and hand over its Trace segments and Evidence Pack, leaving the Task
        open."""
        task = self._experience_base.start_session(project)
        for segment in segments:
            self._experience_base.hand_over_trace_segment(task.id, segment)
        self._experience_base.submit_evidence_pack(task.id, PACK)
        return task


@pytest.fixture
def adapter(experience_base: ExperienceBase) -> FakeHarnessAdapter:
    return FakeHarnessAdapter(experience_base)


@pytest.fixture
def goal(experience_base: ExperienceBase) -> Goal:
    return experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )


def cite(
    experience_base: ExperienceBase,
    goal: Goal,
    task: Task,
    evidence: list[str],
    state: PackageState = PackageState.LESSON_LEARNED,
) -> Package:
    """Put a Package in `state` citing `evidence` into the Experience Base."""
    return experience_base.arrange_package(
        type=PackageType.PROCESS,
        state=state,
        title="Run the failing test alone first",
        summary="Rerun only the failing test before rerunning the suite.",
        content="When a test fails, rerun it alone to see whether it is flaky.",
        scope=ApplicabilityScope(project=PROJECT, attributes={}),
        goal_ids=[goal.id],
        evidence=evidence,
        provenance=Provenance(project=PROJECT, task_ids=(task.id,)),
        reason="arranged by the test",
    )


def record_extracted_metric(experience_base: ExperienceBase, goal: Goal, task: Task) -> None:
    """Record a Metric value for `task`, as the Analyst does after extracting it."""
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    metric = experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )
    experience_base.record_task(
        task.id,
        characterization=Characterization(schema_version="1", attributes={"task_type": "bugfix"}),
        goal_ids=[goal.id],
        holdout=False,
    )
    experience_base.record_metric_value(
        task.id, metric_id=metric.id, metric_version=metric.version, value=1.0
    )


# BS-003: Trace retention keeps only what is cited


def test_an_expired_trace_keeps_only_the_span_cited_by_a_live_lesson_learned(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, goal: Goal, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task()
    record_extracted_metric(experience_base, goal, task)
    metrics_before = experience_base.data_package_records()
    cited = experience_base.trace(task.id).spans[1]
    cite(experience_base, goal, task, [cited.reference])
    clock.advance(WINDOW + timedelta(days=1))

    experience_base.apply_trace_retention()

    trace = experience_base.trace(task.id)
    assert trace.spans == (cited,)
    assert cited.event == SEGMENT.events[1]
    assert trace.segments == ()
    assert experience_base.data_package_records() == metrics_before
    assert experience_base.evidence_pack(task.id) == PACK


def test_spans_are_kept_across_segments_by_the_reference_each_one_is_cited_by(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, goal: Goal, clock: FakeClock
) -> None:
    second = TraceSegment(events=(Prompt("Now rerun the whole suite"),), end_state="interrupted")
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task(segments=(SEGMENT, second))
    spans = experience_base.trace(task.id).spans
    cite(experience_base, goal, task, [spans[0].reference, "issue #1", spans[3].reference])
    clock.advance(WINDOW + timedelta(seconds=1))

    experience_base.apply_trace_retention()

    assert [span.event for span in experience_base.trace(task.id).spans] == [
        SEGMENT.events[0],
        second.events[0],
    ]


# Which Lessons Learned and Packages count as live


@pytest.mark.parametrize("state", [PackageState.CANDIDATE, PackageState.VALIDATED])
def test_a_span_cited_by_a_live_package_is_kept(
    experience_base: ExperienceBase,
    adapter: FakeHarnessAdapter,
    goal: Goal,
    clock: FakeClock,
    state: PackageState,
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task()
    cited = experience_base.trace(task.id).spans[0]
    cite(experience_base, goal, task, [cited.reference], state)
    clock.advance(WINDOW + timedelta(days=1))

    experience_base.apply_trace_retention()

    assert experience_base.trace(task.id).spans == (cited,)


def test_a_span_cited_only_by_a_retired_package_is_removed(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, goal: Goal, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task()
    cite(
        experience_base,
        goal,
        task,
        [experience_base.trace(task.id).spans[0].reference],
        PackageState.RETIRED,
    )
    clock.advance(WINDOW + timedelta(days=1))

    experience_base.apply_trace_retention()

    trace = experience_base.trace(task.id)
    assert trace.spans == ()
    assert trace.segments == ()
    assert trace.is_reduced


def test_a_span_cited_only_by_a_superseded_package_is_removed(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, goal: Goal, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task()
    replacement = cite(experience_base, goal, task, [], PackageState.VALIDATED)
    experience_base.arrange_package(
        type=PackageType.PROCESS,
        state=PackageState.SUPERSEDED,
        title="Rerun the failing test",
        summary="Rerun the failing test.",
        content="Rerun the failing test.",
        scope=ApplicabilityScope(project=PROJECT, attributes={}),
        goal_ids=[goal.id],
        evidence=[experience_base.trace(task.id).spans[0].reference],
        provenance=Provenance(project=PROJECT, task_ids=(task.id,)),
        reason="replaced by a broader Package",
        superseded_by=replacement.id,
    )
    clock.advance(WINDOW + timedelta(days=1))

    experience_base.apply_trace_retention()

    assert experience_base.trace(task.id).spans == ()


# When a Trace has expired


def test_each_project_applies_its_own_window(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, timedelta(days=7))
    experience_base.set_trace_retention_window("other-project", timedelta(days=90))
    short = adapter.run_task(PROJECT)
    long = adapter.run_task("other-project")
    clock.advance(timedelta(days=30))

    experience_base.apply_trace_retention()

    assert experience_base.trace(short.id).segments == ()
    assert experience_base.trace(long.id).segments == (SEGMENT,)


@pytest.mark.parametrize("age", [timedelta(days=1), WINDOW])
def test_a_trace_not_older_than_its_window_is_kept_whole(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, clock: FakeClock, age: timedelta
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.run_task()
    clock.advance(age)

    experience_base.apply_trace_retention()

    trace = experience_base.trace(task.id)
    assert trace.segments == (SEGMENT,)
    assert not trace.is_reduced


def test_a_trace_ages_from_the_end_of_its_task(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.start_task()
    clock.advance(WINDOW + timedelta(days=1))
    experience_base.end_task(task.id)

    experience_base.apply_trace_retention()

    assert experience_base.trace(task.id).segments == (SEGMENT,)


def test_the_trace_of_an_open_task_is_kept_whole(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, clock: FakeClock
) -> None:
    experience_base.set_trace_retention_window(PROJECT, WINDOW)
    task = adapter.start_task()
    clock.advance(WINDOW + timedelta(days=1))

    experience_base.apply_trace_retention()

    assert experience_base.trace(task.id).segments == (SEGMENT,)


def test_a_project_that_never_set_a_window_keeps_its_traces_whole(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, clock: FakeClock
) -> None:
    task = adapter.run_task()
    clock.advance(timedelta(days=3650))

    experience_base.apply_trace_retention()

    assert experience_base.trace(task.id).segments == (SEGMENT,)


# Setting the window (US-003)


def test_a_project_s_window_is_what_it_last_set(experience_base: ExperienceBase) -> None:
    experience_base.set_trace_retention_window(PROJECT, timedelta(days=30))
    experience_base.set_trace_retention_window(PROJECT, timedelta(days=45, hours=6))

    assert experience_base.trace_retention_window(PROJECT) == timedelta(days=45, hours=6)
    assert experience_base.trace_retention_window("other-project") is None


def test_a_negative_window_is_refused(experience_base: ExperienceBase) -> None:
    with pytest.raises(InvalidRetentionWindowError):
        experience_base.set_trace_retention_window(PROJECT, timedelta(days=-1))

    assert experience_base.trace_retention_window(PROJECT) is None


def test_the_window_and_reduced_traces_survive_reopening(db_path: Path, clock: FakeClock) -> None:
    with open_experience_base(db_path, clock=clock) as experience_base:
        experience_base.set_trace_retention_window(PROJECT, WINDOW)
        task = FakeHarnessAdapter(experience_base).run_task()
        goal = experience_base.define_organization_goal(
            purpose="reduce", issue="wasted tool calls", object="agent Tasks", viewpoint="us"
        )
        cited = experience_base.trace(task.id).spans[2]
        cite(experience_base, goal, task, [cited.reference])
    clock.advance(WINDOW + timedelta(days=1))
    with open_experience_base(db_path, clock=clock) as experience_base:
        experience_base.apply_trace_retention()
    with open_experience_base(db_path, clock=clock) as experience_base:
        assert experience_base.trace_retention_window(PROJECT) == WINDOW
        assert experience_base.trace(task.id).spans == (cited,)
