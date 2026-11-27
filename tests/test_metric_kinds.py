"""BS-002: A Judged Metric needs a rubric, and its judge (ADR-0005, #1 Implementation Decisions)."""

import pytest

from experience_factory import (
    ExperienceBase,
    IncompleteJudgeError,
    Judge,
    Metric,
    MetricKind,
    MissingJudgeError,
    MissingRubricError,
    Question,
)

JUDGE = Judge(provider="anthropic", model="claude-haiku-5-5", effort="low")
RUBRIC = "5: every step followed ... 1: plan ignored"


@pytest.fixture
def question(experience_base: ExperienceBase) -> Question:
    goal = experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )
    return experience_base.add_question(goal.id, text="How many tool calls does a Task make?")


def metrics_held_for(experience_base: ExperienceBase, question: Question) -> tuple[Metric, ...]:
    [goal] = experience_base.list_organization_goals()
    [held] = [q for q in goal.questions if q.id == question.id]
    return held.metrics


def test_an_objective_metric_is_accepted_without_a_rubric(
    experience_base: ExperienceBase, question: Question
) -> None:
    experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )

    [metric] = metrics_held_for(experience_base, question)
    assert metric.name == "tool calls per Task"
    assert metric.definition.kind is MetricKind.OBJECTIVE


def test_a_judged_metric_without_a_rubric_is_rejected(
    experience_base: ExperienceBase, question: Question
) -> None:
    with pytest.raises(MissingRubricError):
        experience_base.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
            judge=JUDGE,
        )

    assert metrics_held_for(experience_base, question) == ()


def test_a_judged_metric_with_a_rubric_is_held_as_a_judged_metric(
    experience_base: ExperienceBase, question: Question
) -> None:
    experience_base.add_metric(
        question.id,
        name="plan adherence",
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric=RUBRIC,
        judge=JUDGE,
    )

    [metric] = metrics_held_for(experience_base, question)
    assert metric.definition.kind is MetricKind.JUDGED
    assert metric.definition.rubric == RUBRIC
    assert metric.definition.judge == Judge(
        provider="anthropic", model="claude-haiku-5-5", effort="low"
    )


def test_a_judged_metric_without_a_judge_is_rejected(
    experience_base: ExperienceBase, question: Question
) -> None:
    with pytest.raises(MissingJudgeError):
        experience_base.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
            rubric=RUBRIC,
        )

    assert metrics_held_for(experience_base, question) == ()


@pytest.mark.parametrize("blank_rubric", ["", "   \n\t"])
def test_a_judged_metric_with_a_blank_rubric_is_rejected(
    experience_base: ExperienceBase, question: Question, blank_rubric: str
) -> None:
    with pytest.raises(MissingRubricError):
        experience_base.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
            rubric=blank_rubric,
            judge=JUDGE,
        )

    assert metrics_held_for(experience_base, question) == ()


@pytest.mark.parametrize("blank", ["", "  \t"])
@pytest.mark.parametrize("field", ["provider", "model", "effort"])
def test_a_judge_with_a_blank_provider_model_or_effort_is_rejected(field: str, blank: str) -> None:
    parts = {"provider": "anthropic", "model": "claude-haiku-5-5", "effort": "low"}
    parts[field] = blank

    with pytest.raises(IncompleteJudgeError, match=field):
        Judge(**parts)


def test_an_objective_metric_may_carry_a_judge(
    experience_base: ExperienceBase, question: Question
) -> None:
    experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
        judge=JUDGE,
    )

    [metric] = metrics_held_for(experience_base, question)
    assert metric.definition.kind is MetricKind.OBJECTIVE
    assert metric.definition.judge == Judge(
        provider="anthropic", model="claude-haiku-5-5", effort="low"
    )


def test_an_objective_metric_keeps_a_rubric_it_is_given(
    experience_base: ExperienceBase, question: Question
) -> None:
    experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
        rubric="Count every tool call, retries included.",
    )

    [metric] = metrics_held_for(experience_base, question)
    assert metric.definition.kind is MetricKind.OBJECTIVE
    assert metric.definition.rubric == "Count every tool call, retries included."
