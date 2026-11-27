"""BS-002: A Judged Metric needs a rubric."""

import pytest

from experience_memory import ExperienceMemory, Metric, MetricKind, MissingRubricError, Question


@pytest.fixture
def question(memory: ExperienceMemory) -> Question:
    goal = memory.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )
    return memory.add_question(goal.id, text="How many tool calls does a Task make?")


def metrics_held_for(memory: ExperienceMemory, question: Question) -> tuple[Metric, ...]:
    [goal] = memory.list_organization_goals()
    [held] = [q for q in goal.questions if q.id == question.id]
    return held.metrics


def test_an_objective_metric_is_accepted_without_a_rubric(
    memory: ExperienceMemory, question: Question
) -> None:
    memory.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )

    [metric] = metrics_held_for(memory, question)
    assert metric.name == "tool calls per Task"
    assert metric.kind is MetricKind.OBJECTIVE


def test_a_judged_metric_without_a_rubric_is_rejected(
    memory: ExperienceMemory, question: Question
) -> None:
    with pytest.raises(MissingRubricError):
        memory.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
        )

    assert metrics_held_for(memory, question) == ()
