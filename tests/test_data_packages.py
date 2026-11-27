"""DS-001: per-Task Metric values recorded as Data Packages, through the core public API."""

from pathlib import Path

import pytest

from experience_memory import (
    Characterization,
    DuplicateTaskError,
    DuplicateValueError,
    ExperienceMemory,
    Goal,
    Judge,
    Metric,
    MetricKind,
    MissingJudgeModelError,
    UnknownElementError,
    UnknownTaskError,
    open_memory,
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
def goal(memory: ExperienceMemory) -> Goal:
    return memory.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )


@pytest.fixture
def tool_calls(memory: ExperienceMemory, goal: Goal) -> Metric:
    question = memory.add_question(goal.id, text="How many tool calls does a Task make?")
    return memory.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )


@pytest.fixture
def plan_adherence(memory: ExperienceMemory, goal: Goal) -> Metric:
    question = memory.add_question(goal.id, text="Did the Task follow its plan?")
    return memory.add_metric(
        question.id,
        name="plan adherence",
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric="5: every step followed ... 1: plan ignored",
        judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
    )


def test_a_metric_value_recorded_for_a_task_is_in_its_data_package(
    memory: ExperienceMemory, goal: Goal, tool_calls: Metric
) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False)

    memory.record_metric_value(
        "task-1", metric_id=tool_calls.id, metric_version=tool_calls.version, value=17
    )

    [record] = memory.data_package_records()
    assert record.task_id == "task-1"
    assert record.metric.name == "tool calls per Task"
    assert record.value == 17
    assert record.characterization == PYTHON_BUGFIX
    assert [g.id for g in record.goals] == [goal.id]
    assert record.holdout is False


def test_a_judged_value_stores_the_model_that_produced_it(
    memory: ExperienceMemory, goal: Goal, plan_adherence: Metric
) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True)

    memory.record_metric_value(
        "task-1",
        metric_id=plan_adherence.id,
        metric_version=plan_adherence.version,
        value=4,
        judged_by_model="claude-haiku-5-5-20261001",
    )

    [record] = memory.data_package_records()
    assert record.judged_by_model == "claude-haiku-5-5-20261001"


@pytest.mark.parametrize("missing_model", [None, "", "  "])
def test_a_judged_value_without_the_model_that_produced_it_is_rejected(
    memory: ExperienceMemory, goal: Goal, plan_adherence: Metric, missing_model: str | None
) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True)

    with pytest.raises(MissingJudgeModelError):
        memory.record_metric_value(
            "task-1",
            metric_id=plan_adherence.id,
            metric_version=plan_adherence.version,
            value=4,
            judged_by_model=missing_model,
        )

    assert memory.data_package_records() == []


def test_a_value_for_an_unrecorded_task_is_rejected(
    memory: ExperienceMemory, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownTaskError):
        memory.record_metric_value(
            "no-such-task", metric_id=tool_calls.id, metric_version=1, value=3
        )

    assert memory.data_package_records() == []


def test_a_value_for_an_unknown_metric_version_is_rejected(
    memory: ExperienceMemory, goal: Goal, tool_calls: Metric
) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False)

    with pytest.raises(UnknownElementError):
        memory.record_metric_value("task-1", metric_id=tool_calls.id, metric_version=2, value=3)

    assert memory.data_package_records() == []


def test_a_second_value_for_the_same_task_and_metric_version_is_rejected(
    memory: ExperienceMemory, goal: Goal, tool_calls: Metric
) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False)
    memory.record_metric_value("task-1", metric_id=tool_calls.id, metric_version=1, value=3)

    with pytest.raises(DuplicateValueError):
        memory.record_metric_value("task-1", metric_id=tool_calls.id, metric_version=1, value=5)

    assert [r.value for r in memory.data_package_records()] == [3]


def test_a_task_is_recorded_only_once(memory: ExperienceMemory, goal: Goal) -> None:
    memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=False)

    with pytest.raises(DuplicateTaskError):
        memory.record_task("task-1", characterization=PYTHON_BUGFIX, goal_ids=[], holdout=True)


def test_a_task_selecting_an_unknown_goal_is_rejected(
    memory: ExperienceMemory, goal: Goal, tool_calls: Metric
) -> None:
    with pytest.raises(UnknownElementError):
        memory.record_task(
            "task-1",
            characterization=PYTHON_BUGFIX,
            goal_ids=[goal.id, "no-such-goal"],
            holdout=False,
        )

    with pytest.raises(UnknownTaskError):
        memory.record_metric_value("task-1", metric_id=tool_calls.id, metric_version=1, value=3)


def test_data_packages_persist_across_reopening(db_path: Path) -> None:
    with open_memory(db_path) as memory:
        goal = memory.define_organization_goal(
            purpose="reduce",
            issue="wasted tool calls",
            object="agent Tasks",
            viewpoint="the Organization",
        )
        question = memory.add_question(goal.id, text="How many tool calls does a Task make?")
        metric = memory.add_metric(
            question.id,
            name="tool calls per Task",
            definition="Number of tool calls in the Task's Trace.",
            kind=MetricKind.OBJECTIVE,
        )
        memory.record_task(
            "task-1", characterization=PYTHON_BUGFIX, goal_ids=[goal.id], holdout=True
        )
        memory.record_metric_value("task-1", metric_id=metric.id, metric_version=1, value=9)

    with open_memory(db_path) as reopened:
        [record] = reopened.data_package_records()

    assert (record.task_id, record.metric.name, record.value) == (
        "task-1",
        "tool calls per Task",
        9,
    )
    assert record.characterization == PYTHON_BUGFIX
    assert [g.issue for g in record.goals] == ["wasted tool calls"]
    assert record.holdout is True
