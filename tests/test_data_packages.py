"""DS-001: per-Task Metric values recorded as Data Packages, through the core public API."""

from pathlib import Path

import pytest

from experience_memory import (
    Characterization,
    DuplicateTaskError,
    DuplicateValueError,
    ExperienceBase,
    Goal,
    Judge,
    Metric,
    MetricKind,
    MissingJudgeModelError,
    UnapprovedMetricError,
    UnknownElementError,
    UnknownTaskError,
    open_experience_base,
)

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
    return experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
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
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )

    experience_base.record_metric_value(
        "task-1", metric_id=tool_calls.id, metric_version=tool_calls.version, value=17
    )

    [record] = experience_base.data_package_records()
    assert record.task_id == "task-1"
    assert record.metric.name == "tool calls per Task"
    assert record.value == 17
    assert record.characterization == PYTHON_BUGFIX
    assert [g.id for g in record.goals] == [goal.id]
    assert record.holdout is False


def test_a_judged_value_stores_the_model_that_produced_it(
    experience_base: ExperienceBase, goal: Goal, plan_adherence: Metric
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True
    )

    experience_base.record_metric_value(
        "task-1",
        metric_id=plan_adherence.id,
        metric_version=plan_adherence.version,
        value=4,
        judged_by_model="claude-haiku-5-5-20261001",
    )

    [record] = experience_base.data_package_records()
    assert record.judged_by_model == "claude-haiku-5-5-20261001"


@pytest.mark.parametrize("missing_model", [None, "", "  "])
def test_a_judged_value_without_the_model_that_produced_it_is_rejected(
    experience_base: ExperienceBase, goal: Goal, plan_adherence: Metric, missing_model: str | None
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True
    )

    with pytest.raises(MissingJudgeModelError):
        experience_base.record_metric_value(
            "task-1",
            metric_id=plan_adherence.id,
            metric_version=plan_adherence.version,
            value=4,
            judged_by_model=missing_model,
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_an_unrecorded_task_is_rejected(
    experience_base: ExperienceBase, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownTaskError):
        experience_base.record_metric_value(
            "no-such-task", metric_id=tool_calls.id, metric_version=1, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_an_unknown_metric_version_is_rejected(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )

    with pytest.raises(UnknownElementError):
        experience_base.record_metric_value(
            "task-1", metric_id=tool_calls.id, metric_version=2, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_second_value_for_the_same_task_and_metric_version_is_rejected(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )
    experience_base.record_metric_value(
        "task-1", metric_id=tool_calls.id, metric_version=1, value=3
    )

    with pytest.raises(DuplicateValueError):
        experience_base.record_metric_value(
            "task-1", metric_id=tool_calls.id, metric_version=1, value=5
        )

    assert [r.value for r in experience_base.data_package_records()] == [3]


def test_a_task_is_recorded_only_once(experience_base: ExperienceBase, goal: Goal) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )

    with pytest.raises(DuplicateTaskError):
        experience_base.record_task(
            "task-1", characterization=PYTHON_BUGFIX, goal_ids=[], holdout=True
        )


def test_a_task_selecting_an_unknown_goal_is_rejected(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.record_task(
            "task-1",
            characterization=PYTHON_BUGFIX,
            goal_ids=[goal.id, "no-such-goal"],
            holdout=False,
        )

    with pytest.raises(UnknownTaskError):
        experience_base.record_metric_value(
            "task-1", metric_id=tool_calls.id, metric_version=1, value=3
        )


def test_data_packages_persist_across_reopening(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = experience_base.define_organization_goal(
            purpose="reduce",
            issue="wasted tool calls",
            object="agent Tasks",
            viewpoint="the Organization",
        )
        question = experience_base.add_question(
            goal.id, text="How many tool calls does a Task make?"
        )
        metric = experience_base.add_metric(
            question.id,
            name="tool calls per Task",
            definition="Number of tool calls in the Task's Trace.",
            kind=MetricKind.OBJECTIVE,
        )
        experience_base.record_task(
            "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True
        )
        experience_base.record_metric_value(
            "task-1", metric_id=metric.id, metric_version=1, value=9
        )

    with open_experience_base(db_path) as reopened:
        [record] = reopened.data_package_records()

    assert (record.task_id, record.metric.name, record.value) == (
        "task-1",
        "tool calls per Task",
        9,
    )
    assert record.characterization == PYTHON_BUGFIX
    assert [g.statement.issue for g in record.goals] == ["wasted tool calls"]
    assert record.holdout is True


def test_an_objective_value_may_carry_the_model_that_produced_it(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )

    experience_base.record_metric_value(
        "task-1",
        metric_id=tool_calls.id,
        metric_version=tool_calls.version,
        value=17,
        judged_by_model="claude-haiku-5-5-20261001",
    )

    [record] = experience_base.data_package_records()
    assert record.judged_by_model == "claude-haiku-5-5-20261001"


@pytest.mark.parametrize("decision", ["proposed", "rejected"])
def test_a_value_for_a_metric_never_in_force_is_rejected(
    experience_base: ExperienceBase, goal: Goal, decision: str
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
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )

    with pytest.raises(UnapprovedMetricError):
        experience_base.record_metric_value(
            "task-1", metric_id=proposed.id, metric_version=proposed.version, value=3
        )

    assert experience_base.data_package_records() == []


def test_a_value_for_an_approved_metric_under_a_retired_goal_is_recorded(
    experience_base: ExperienceBase,
) -> None:
    goal = experience_base.propose_project_goal(
        "experience-memory",
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )
    experience_base.approve_goal(goal.id)
    question = experience_base.add_question(goal.id, text="How often are tests rerun?")
    reruns = experience_base.add_metric(
        question.id,
        name="test reruns per Task",
        definition="Number of times the Task reran a test suite it had already run.",
        kind=MetricKind.OBJECTIVE,
    )
    experience_base.record_task(
        "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False
    )
    experience_base.retire_goal(goal.id)

    experience_base.record_metric_value(
        "task-1", metric_id=reruns.id, metric_version=reruns.version, value=2
    )

    [record] = experience_base.data_package_records()
    assert (record.metric.id, record.value) == (reruns.id, 2)
