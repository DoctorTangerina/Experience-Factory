"""BS-004: Questions and Metrics proposed by the Analyst wait for human approval."""

import pytest

from experience_memory import (
    ApprovalStateError,
    ExperienceMemory,
    Judge,
    MetricKind,
    MissingRubricError,
    Question,
    UnknownElementError,
)


@pytest.fixture
def question(memory: ExperienceMemory) -> Question:
    """An existing Question, in force, with one Metric a human added."""
    goal = memory.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )
    question = memory.add_question(goal.id, text="How many tool calls does a Task make?")
    memory.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )
    return question


def metric_names_in_force(memory: ExperienceMemory, question: Question) -> list[str]:
    return [metric.name for metric in memory.metrics_in_force(question.id)]


def propose_failed_calls(memory: ExperienceMemory, question: Question) -> str:
    return memory.propose_metric(
        question.id,
        name="failed tool calls per Task",
        definition="Number of tool calls in the Task's Trace that returned an error.",
        kind=MetricKind.OBJECTIVE,
    ).id


def test_a_metric_proposed_by_the_analyst_is_not_in_force(
    memory: ExperienceMemory, question: Question
) -> None:
    propose_failed_calls(memory, question)

    assert metric_names_in_force(memory, question) == ["tool calls per Task"]


def test_an_approved_proposed_metric_is_in_force(
    memory: ExperienceMemory, question: Question
) -> None:
    metric_id = propose_failed_calls(memory, question)

    memory.approve_metric(metric_id)

    assert metric_names_in_force(memory, question) == [
        "tool calls per Task",
        "failed tool calls per Task",
    ]


def test_a_rejected_proposed_metric_is_never_in_force(
    memory: ExperienceMemory, question: Question
) -> None:
    metric_id = propose_failed_calls(memory, question)
    memory.reject_metric(metric_id)

    with pytest.raises(ApprovalStateError):
        memory.approve_metric(metric_id)

    assert metric_names_in_force(memory, question) == ["tool calls per Task"]


def test_a_proposed_metric_is_not_listed_in_the_gqm_plan(
    memory: ExperienceMemory, question: Question
) -> None:
    propose_failed_calls(memory, question)

    [goal] = memory.list_organization_goals()
    [listed] = goal.questions
    assert [metric.name for metric in listed.metrics] == ["tool calls per Task"]


def test_a_proposed_judged_metric_without_a_rubric_is_rejected(
    memory: ExperienceMemory, question: Question
) -> None:
    with pytest.raises(MissingRubricError):
        memory.propose_metric(
            question.id,
            name="tool call waste",
            definition="How wasteful the Task's tool calls were.",
            kind=MetricKind.JUDGED,
            judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
        )


def test_a_question_proposed_by_the_analyst_is_not_in_force_until_approved(
    memory: ExperienceMemory, question: Question
) -> None:
    [goal] = memory.list_organization_goals()
    proposed = memory.propose_question(goal.id, text="How many tool calls fail?")
    memory.add_metric(
        proposed.id,
        name="failed tool calls per Task",
        definition="Number of tool calls in the Task's Trace that returned an error.",
        kind=MetricKind.OBJECTIVE,
    )

    assert memory.metrics_in_force(proposed.id) == []
    [listed_goal] = memory.list_organization_goals()
    assert [q.id for q in listed_goal.questions] == [question.id]

    memory.approve_question(proposed.id)

    assert [m.name for m in memory.metrics_in_force(proposed.id)] == ["failed tool calls per Task"]


def test_a_rejected_proposed_question_is_never_in_force(
    memory: ExperienceMemory, question: Question
) -> None:
    [goal] = memory.list_organization_goals()
    proposed = memory.propose_question(goal.id, text="How many tool calls fail?")

    memory.reject_question(proposed.id)

    [listed_goal] = memory.list_organization_goals()
    assert [q.id for q in listed_goal.questions] == [question.id]
    with pytest.raises(ApprovalStateError):
        memory.approve_question(proposed.id)


def test_no_metric_is_in_force_under_a_retired_goal(memory: ExperienceMemory) -> None:
    goal = memory.propose_project_goal(
        "experience-memory",
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )
    memory.approve_goal(goal.id)
    question = memory.add_question(goal.id, text="How often are tests rerun?")
    memory.add_metric(
        question.id,
        name="test reruns per Task",
        definition="Number of times the Task reran a test suite it had already run.",
        kind=MetricKind.OBJECTIVE,
    )

    memory.retire_goal(goal.id)

    assert memory.metrics_in_force(question.id) == []


def test_a_redefined_proposed_metric_stays_proposed(
    memory: ExperienceMemory, question: Question
) -> None:
    metric_id = propose_failed_calls(memory, question)

    memory.redefine_metric(
        metric_id,
        definition="Number of tool calls that returned an error, excluding retries.",
        kind=MetricKind.OBJECTIVE,
    )

    assert metric_names_in_force(memory, question) == ["tool calls per Task"]
    memory.approve_metric(metric_id)
    [_, approved] = memory.metrics_in_force(question.id)
    assert approved.version == 2


def test_listing_metrics_in_force_for_an_unknown_question_is_rejected(
    memory: ExperienceMemory,
) -> None:
    with pytest.raises(UnknownElementError):
        memory.metrics_in_force("no-such-question")
