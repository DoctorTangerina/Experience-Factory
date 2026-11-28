"""DS-001: per-Task Metric values recorded as Data Packages, through the core public API.

A Task is opened by its Harness Adapter and its start (Characterization, Goals, Holdout) is recorded
against that Task by the Advisor (ADR-0008); the tests stand in for both."""

from pathlib import Path

import pytest

from experience_factory import (
    Characterization,
    ClaimStatus,
    DuplicateValueError,
    EvidencePack,
    ExperienceBase,
    Goal,
    GoalOutsideProjectError,
    Judge,
    Manifest,
    Metric,
    MetricKind,
    MissingJudgeModelError,
    PlanLedger,
    Prompt,
    Rationale,
    RisksAndAssumptions,
    Task,
    TaskStartAfterEndError,
    TaskStartAlreadyRecordedError,
    TaskStartNotRecordedError,
    TraceSegment,
    UnapprovedMetricError,
    UnknownElementError,
    UnknownTaskError,
    open_experience_base,
)
from tests.support import PROJECT, define_project_goal, open_started_task

PYTHON_BUGFIX = Characterization(
    schema_version="1",
    attributes={
        "languages": frozenset({"python"}),
        "task_type": "bugfix",
        "harness": "claude-code",
    },
)


@pytest.fixture
def goal(experience_base: ExperienceBase) -> Goal:
    return define_project_goal(experience_base, issue="wasted tool calls")


@pytest.fixture
def task(experience_base: ExperienceBase) -> Task:
    """A Task its Harness Adapter has opened, with no start recorded yet."""
    return experience_base.start_session(PROJECT)


def record_start(
    experience_base: ExperienceBase, task: Task, goal: Goal, *, holdout: bool = False
) -> None:
    experience_base.record_task_start(
        task.id, characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=holdout
    )


@pytest.fixture
def tool_calls(experience_base: ExperienceBase, goal: Goal) -> Metric:
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    return experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )


@pytest.fixture
def plan_adherence(experience_base: ExperienceBase, goal: Goal) -> Metric:
    question = experience_base.add_question(goal.id, text="Did the Task follow its plan?")
    return experience_base.add_metric(
        question.id,
        name="plan adherence",
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric="5: every step followed ... 1: plan ignored",
        judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
    )


def test_a_metric_value_recorded_for_a_task_is_in_its_data_package(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric
) -> None:
    record_start(experience_base, task, goal)

    experience_base.record_metric_value(
        task.id, metric_id=tool_calls.id, metric_version=tool_calls.version, value=17
    )

    [record] = experience_base.data_package_records()
    assert record.task_id == task.id
    assert record.metric.name == "tool calls per Task"
    assert record.value == 17
    assert record.characterization == PYTHON_BUGFIX
    assert [g.id for g in record.goals] == [goal.id]
    assert record.holdout is False


def test_a_judged_value_stores_the_model_that_produced_it(
    experience_base: ExperienceBase, task: Task, goal: Goal, plan_adherence: Metric
) -> None:
    record_start(experience_base, task, goal, holdout=True)

    experience_base.record_metric_value(
        task.id,
        metric_id=plan_adherence.id,
        metric_version=plan_adherence.version,
        value=4,
        judged_by_model="claude-haiku-5-5-20261001",
    )

    [record] = experience_base.data_package_records()
    assert record.judged_by_model == "claude-haiku-5-5-20261001"


@pytest.mark.parametrize("missing_model", [None, "", "  "])
def test_a_judged_value_without_the_model_that_produced_it_is_rejected(
    experience_base: ExperienceBase,
    task: Task,
    goal: Goal,
    plan_adherence: Metric,
    missing_model: str | None,
) -> None:
    record_start(experience_base, task, goal, holdout=True)

    with pytest.raises(MissingJudgeModelError):
        experience_base.record_metric_value(
            task.id,
            metric_id=plan_adherence.id,
            metric_version=plan_adherence.version,
            value=4,
            judged_by_model=missing_model,
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_a_task_that_does_not_exist_is_rejected(
    experience_base: ExperienceBase, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownTaskError):
        experience_base.record_metric_value(
            "no-such-task", metric_id=tool_calls.id, metric_version=1, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_a_task_with_no_start_record_is_rejected(
    experience_base: ExperienceBase, task: Task, tool_calls: Metric
) -> None:
    with pytest.raises(TaskStartNotRecordedError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=1, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_an_unknown_metric_version_is_rejected(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric
) -> None:
    record_start(experience_base, task, goal)

    with pytest.raises(UnknownElementError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=2, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_second_value_for_the_same_task_and_metric_version_is_rejected(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric
) -> None:
    record_start(experience_base, task, goal)
    experience_base.record_metric_value(task.id, metric_id=tool_calls.id, metric_version=1, value=3)

    with pytest.raises(DuplicateValueError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=1, value=5
        )

    assert [r.value for r in experience_base.data_package_records()] == [3]


# Recording a Task's start (ADR-0008)


def test_a_task_s_start_is_recorded_only_once(
    experience_base: ExperienceBase, task: Task, goal: Goal
) -> None:
    record_start(experience_base, task, goal)

    with pytest.raises(TaskStartAlreadyRecordedError):
        experience_base.record_task_start(
            task.id, characterization=PYTHON_BUGFIX, goal_ids=[], holdout=True
        )


def test_the_start_of_a_task_that_does_not_exist_is_refused(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    with pytest.raises(UnknownTaskError):
        experience_base.record_task_start(
            "no-such-task", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
        )


@pytest.mark.parametrize("reopened", [False, True], ids=["ended", "reopened after ending"])
def test_the_start_of_a_task_that_has_ended_is_refused(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric, reopened: bool
) -> None:
    experience_base.end_task(task.id)
    if reopened:
        experience_base.start_session(PROJECT, continues_task=task.id)

    with pytest.raises(TaskStartAfterEndError):
        record_start(experience_base, task, goal)

    with pytest.raises(TaskStartNotRecordedError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=1, value=3
        )


def test_a_task_selecting_an_unknown_goal_is_rejected(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.record_task_start(
            task.id,
            characterization=PYTHON_BUGFIX,
            goal_ids=[goal.id, "no-such-goal"],
            holdout=False,
        )

    with pytest.raises(TaskStartNotRecordedError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=1, value=3
        )


@pytest.mark.parametrize("outside", ["organization", "another project"])
def test_a_task_selecting_a_goal_outside_its_project_is_rejected_and_nothing_is_recorded(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric, outside: str
) -> None:
    if outside == "organization":
        foreign = experience_base.define_organization_goal(
            purpose="reduce", issue="cost", object="agent Tasks", viewpoint="the Organization"
        )
    else:
        foreign = define_project_goal(experience_base, "another-project")

    with pytest.raises(GoalOutsideProjectError, match=foreign.id):
        experience_base.record_task_start(
            task.id, characterization=PYTHON_BUGFIX, goal_ids=[goal.id, foreign.id], holdout=False
        )

    with pytest.raises(TaskStartNotRecordedError):
        experience_base.record_metric_value(
            task.id, metric_id=tool_calls.id, metric_version=1, value=3
        )
    record_start(experience_base, task, goal)


def test_a_task_with_no_start_record_can_still_run_its_course(
    experience_base: ExperienceBase, task: Task
) -> None:
    pack = EvidencePack(
        claims=(),
        plan=PlanLedger(conceptual_plan="fix it", executed_approach="fixed it"),
        rationale=Rationale(approach_taken="fix it"),
        exploration_archive=(),
        risks=RisksAndAssumptions(),
        manifest=Manifest(overall_status=ClaimStatus.NOT_RUN, producer="test"),
    )

    experience_base.hand_over_trace_segment(task.id, TraceSegment(events=(Prompt("Go"),)))
    experience_base.end_task(task.id)
    experience_base.submit_evidence_pack(task.id, pack)
    reopened = experience_base.start_session(PROJECT, continues_task=task.id)
    experience_base.hand_over_trace_segment(task.id, TraceSegment(events=(Prompt("Resume"),)))
    experience_base.end_task(task.id)

    assert reopened.id == task.id
    assert len(experience_base.trace(task.id).segments) == 2
    assert experience_base.evidence_pack(task.id) == pack


# Persistence and the Metric's state


def test_data_packages_persist_across_reopening(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = define_project_goal(experience_base, issue="wasted tool calls")
        question = experience_base.add_question(
            goal.id, text="How many tool calls does a Task make?"
        )
        metric = experience_base.add_metric(
            question.id,
            name="tool calls per Task",
            definition="Number of tool calls in the Task's Trace.",
            kind=MetricKind.OBJECTIVE,
        )
        task = open_started_task(
            experience_base, goal_ids=[goal.id], characterization=PYTHON_BUGFIX, holdout=True
        )
        experience_base.record_metric_value(task.id, metric_id=metric.id, metric_version=1, value=9)

    with open_experience_base(db_path) as reopened:
        [record] = reopened.data_package_records()

    assert (record.task_id, record.metric.name, record.value) == (
        task.id,
        "tool calls per Task",
        9,
    )
    assert record.characterization == PYTHON_BUGFIX
    assert [g.statement.issue for g in record.goals] == ["wasted tool calls"]
    assert record.holdout is True


def test_an_objective_value_may_carry_the_model_that_produced_it(
    experience_base: ExperienceBase, task: Task, goal: Goal, tool_calls: Metric
) -> None:
    record_start(experience_base, task, goal)

    experience_base.record_metric_value(
        task.id,
        metric_id=tool_calls.id,
        metric_version=tool_calls.version,
        value=17,
        judged_by_model="claude-haiku-5-5-20261001",
    )

    [record] = experience_base.data_package_records()
    assert record.judged_by_model == "claude-haiku-5-5-20261001"


@pytest.mark.parametrize("decision", ["proposed", "rejected"])
def test_a_value_for_a_metric_never_in_force_is_rejected(
    experience_base: ExperienceBase, task: Task, goal: Goal, decision: str
) -> None:
    question = experience_base.add_question(goal.id, text="How often are tools retried?")
    proposed = experience_base.propose_metric(
        question.id,
        name="tool retries per Task",
        definition="Number of repeated identical tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )
    if decision == "rejected":
        experience_base.reject_metric(proposed.id)
    record_start(experience_base, task, goal)

    with pytest.raises(UnapprovedMetricError):
        experience_base.record_metric_value(
            task.id, metric_id=proposed.id, metric_version=proposed.version, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_an_approved_metric_under_a_retired_goal_is_recorded(
    experience_base: ExperienceBase, task: Task
) -> None:
    goal = define_project_goal(experience_base)
    question = experience_base.add_question(goal.id, text="How often are tests rerun?")
    reruns = experience_base.add_metric(
        question.id,
        name="test reruns per Task",
        definition="Number of times the Task reran a test suite it had already run.",
        kind=MetricKind.OBJECTIVE,
    )
    record_start(experience_base, task, goal)
    experience_base.retire_goal(goal.id)

    experience_base.record_metric_value(
        task.id, metric_id=reruns.id, metric_version=reruns.version, value=2
    )

    [record] = experience_base.data_package_records()
    assert (record.metric.id, record.value) == (reruns.id, 2)
