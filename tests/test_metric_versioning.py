"""BS-001: Changing a Metric definition creates a new Metric version."""

import pytest

from experience_factory import (
    Characterization,
    ExperienceBase,
    Goal,
    Judge,
    Metric,
    MetricKind,
    MissingJudgeError,
    MissingRubricError,
    UnknownElementError,
)

CHARACTERIZATION = Characterization(schema_version="1", attributes={"task_type": "feature"})


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


def metrics_in_plan(experience_base: ExperienceBase) -> list[Metric]:
    [goal] = experience_base.list_organization_goals()
    return [metric for question in goal.questions for metric in question.metrics]


def test_redefining_a_metric_leaves_recorded_values_on_the_old_version(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    for task_id, value in [("task-1", 12), ("task-2", 30)]:
        experience_base.record_task(
            task_id, characterization=CHARACTERIZATION, goal_ids=[goal.id], holdout=False
        )
        experience_base.record_metric_value(
            task_id, metric_id=tool_calls.id, metric_version=1, value=value
        )

    experience_base.redefine_metric(
        tool_calls.id,
        definition="Number of tool calls in the Task's Trace, excluding retries.",
        kind=MetricKind.OBJECTIVE,
    )

    [held] = metrics_in_plan(experience_base)
    assert (held.name, held.version) == ("tool calls per Task", 2)
    assert held.definition.text == "Number of tool calls in the Task's Trace, excluding retries."
    assert [
        (r.task_id, r.metric.version, r.value) for r in experience_base.data_package_records()
    ] == [
        ("task-1", 1, 12),
        ("task-2", 1, 30),
    ]
    assert {r.metric.definition.text for r in experience_base.data_package_records()} == {
        "Number of tool calls in the Task's Trace."
    }


def test_changing_the_judge_creates_a_new_metric_version(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    question = experience_base.add_question(goal.id, text="Did the Task follow its plan?")
    rubric = "5: every step followed ... 1: plan ignored"
    adherence = experience_base.add_metric(
        question.id,
        name="plan adherence",
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric=rubric,
        judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
    )

    experience_base.redefine_metric(
        adherence.id,
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric=rubric,
        judge=Judge(provider="anthropic", model="claude-sonnet-5-5", effort="low"),
    )

    [held] = metrics_in_plan(experience_base)
    assert held.version == 2
    assert held.definition.judge == Judge(
        provider="anthropic", model="claude-sonnet-5-5", effort="low"
    )


def test_a_redefinition_to_a_judged_metric_without_a_rubric_is_rejected(
    experience_base: ExperienceBase, tool_calls: Metric
) -> None:
    with pytest.raises(MissingRubricError):
        experience_base.redefine_metric(
            tool_calls.id,
            definition="How wasteful the Task's tool calls were.",
            kind=MetricKind.JUDGED,
            judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
        )

    [held] = metrics_in_plan(experience_base)
    assert (held.version, held.definition.kind) == (1, MetricKind.OBJECTIVE)


def test_a_redefinition_to_a_judged_metric_without_a_judge_is_rejected(
    experience_base: ExperienceBase, tool_calls: Metric
) -> None:
    with pytest.raises(MissingJudgeError):
        experience_base.redefine_metric(
            tool_calls.id,
            definition="How wasteful the Task's tool calls were.",
            kind=MetricKind.JUDGED,
            rubric="5: no wasted call ... 1: mostly wasted",
        )

    [held] = metrics_in_plan(experience_base)
    assert held.version == 1


def test_redefining_an_unknown_metric_is_rejected(experience_base: ExperienceBase) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.redefine_metric(
            "no-such-metric", definition="anything", kind=MetricKind.OBJECTIVE
        )


def test_redefining_a_metric_with_an_unchanged_definition_still_creates_a_new_version(
    experience_base: ExperienceBase, tool_calls: Metric
) -> None:
    experience_base.redefine_metric(
        tool_calls.id,
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )

    [held] = metrics_in_plan(experience_base)
    assert held.version == 2


def test_a_value_may_still_be_recorded_against_a_superseded_metric_version(
    experience_base: ExperienceBase, goal: Goal, tool_calls: Metric
) -> None:
    experience_base.redefine_metric(
        tool_calls.id,
        definition="Number of tool calls in the Task's Trace, excluding retries.",
        kind=MetricKind.OBJECTIVE,
    )
    experience_base.record_task(
        "task-1", characterization=CHARACTERIZATION, goal_ids=[goal.id], holdout=False
    )

    experience_base.record_metric_value(
        "task-1", metric_id=tool_calls.id, metric_version=1, value=8
    )

    [record] = experience_base.data_package_records()
    assert (record.metric.version, record.value) == (1, 8)
