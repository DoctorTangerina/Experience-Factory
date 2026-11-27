"""Goals and Questions are versioned the same way as Metrics (spec #1, Implementation Decisions).

Only a human redefines a GQM plan element. The new version keeps the element's approval state,
and Questions and Metrics stay attached to their Goal or Question across versions.
"""

from collections.abc import Callable
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from experience_factory import (
    ApprovalStateError,
    Characterization,
    ExperienceBase,
    Goal,
    MetricKind,
    UnknownElementError,
)

PROJECT = "experience-factory"
CHARACTERIZATION = Characterization(schema_version="1", attributes={"task_type": "feature"})


@pytest.fixture
def goal(experience_base: ExperienceBase) -> Goal:
    return experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )


def propose_project_goal(experience_base: ExperienceBase) -> Goal:
    return experience_base.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )


def redefine_goal(experience_base: ExperienceBase, goal_id: str) -> Goal:
    return experience_base.redefine_goal(
        goal_id,
        purpose="reduce",
        issue="wasted tool calls and retries",
        object="agent Tasks",
        viewpoint="the Organization",
    )


def test_redefining_an_approved_goal_creates_its_next_version_with_its_questions(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")

    redefined = redefine_goal(experience_base, goal.id)

    assert (redefined.id, redefined.version) == (goal.id, 2)
    [listed] = experience_base.list_organization_goals()
    assert (listed.id, listed.version) == (goal.id, 2)
    assert listed.statement.issue == "wasted tool calls and retries"
    assert [q.id for q in listed.questions] == [question.id]


def test_a_redefined_approved_project_goal_is_selectable_at_its_new_version(
    experience_base: ExperienceBase,
) -> None:
    goal = propose_project_goal(experience_base)
    experience_base.approve_goal(goal.id)

    experience_base.redefine_goal(
        goal.id,
        purpose="reduce",
        issue="flaky test reruns in CI",
        object="agent Tasks",
        viewpoint="the Project",
    )

    [selectable] = experience_base.selectable_project_goals(PROJECT)
    assert (selectable.id, selectable.version) == (goal.id, 2)
    assert selectable.statement.issue == "flaky test reruns in CI"


def test_a_redefined_proposed_project_goal_stays_proposed_until_approved(
    experience_base: ExperienceBase,
) -> None:
    goal = propose_project_goal(experience_base)

    experience_base.redefine_goal(
        goal.id,
        purpose="reduce",
        issue="flaky test reruns in CI",
        object="agent Tasks",
        viewpoint="the Project",
    )

    assert experience_base.selectable_project_goals(PROJECT) == []
    experience_base.approve_goal(goal.id)
    [selectable] = experience_base.selectable_project_goals(PROJECT)
    assert (selectable.id, selectable.version) == (goal.id, 2)


def test_redefining_an_approved_question_keeps_its_metrics_in_force(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    metric = experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )

    redefined = experience_base.redefine_question(
        question.id, text="How many tool calls does a Task make, excluding retries?"
    )

    assert (redefined.id, redefined.version) == (question.id, 2)
    assert [m.id for m in experience_base.metrics_in_force(question.id)] == [metric.id]
    [listed_goal] = experience_base.list_organization_goals()
    [listed] = listed_goal.questions
    assert (listed.version, listed.text) == (
        2,
        "How many tool calls does a Task make, excluding retries?",
    )
    assert [m.id for m in listed.metrics] == [metric.id]


def test_a_redefined_proposed_question_stays_proposed_until_approved(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    question = experience_base.propose_question(goal.id, text="How often are tools retried?")

    experience_base.redefine_question(question.id, text="How often is a tool call retried?")

    [listed_goal] = experience_base.list_organization_goals()
    assert listed_goal.questions == ()
    experience_base.approve_question(question.id)
    [listed_goal] = experience_base.list_organization_goals()
    assert [(q.id, q.version) for q in listed_goal.questions] == [(question.id, 2)]


def _rejected_goal(experience_base: ExperienceBase, goal: Goal) -> Callable[[], object]:
    proposed = propose_project_goal(experience_base)
    experience_base.reject_goal(proposed.id)
    return lambda: redefine_goal(experience_base, proposed.id)


def _retired_goal(experience_base: ExperienceBase, goal: Goal) -> Callable[[], object]:
    experience_base.retire_goal(goal.id)
    return lambda: redefine_goal(experience_base, goal.id)


def _rejected_question(experience_base: ExperienceBase, goal: Goal) -> Callable[[], object]:
    question = experience_base.propose_question(goal.id, text="How often are tools retried?")
    experience_base.reject_question(question.id)
    return lambda: experience_base.redefine_question(question.id, text="anything")


def _rejected_metric(experience_base: ExperienceBase, goal: Goal) -> Callable[[], object]:
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    metric = experience_base.propose_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )
    experience_base.reject_metric(metric.id)
    return lambda: experience_base.redefine_metric(
        metric.id, definition="anything", kind=MetricKind.OBJECTIVE
    )


@pytest.mark.parametrize(
    "arrange",
    [_rejected_goal, _retired_goal, _rejected_question, _rejected_metric],
    ids=["rejected Goal", "retired Goal", "rejected Question", "rejected Metric"],
)
def test_a_rejected_or_retired_element_cannot_be_redefined(
    experience_base: ExperienceBase,
    goal: Goal,
    arrange: Callable[[ExperienceBase, Goal], Callable[[], object]],
) -> None:
    redefine = arrange(experience_base, goal)

    with pytest.raises(ApprovalStateError):
        redefine()


def test_redefining_an_unknown_goal_or_question_is_rejected(
    experience_base: ExperienceBase,
) -> None:
    with pytest.raises(UnknownElementError):
        redefine_goal(experience_base, "no-such-goal")
    with pytest.raises(UnknownElementError):
        experience_base.redefine_question("no-such-question", text="anything")


def test_a_recorded_task_keeps_the_goal_version_it_selected_after_a_redefinition(
    experience_base: ExperienceBase, goal: Goal, tmp_path: Path
) -> None:
    question = experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    metric = experience_base.add_metric(
        question.id,
        name="tool calls per Task",
        definition="Number of tool calls in the Task's Trace.",
        kind=MetricKind.OBJECTIVE,
    )
    experience_base.record_task(
        "task-1", characterization=CHARACTERIZATION, goal_ids=[goal.id], holdout=False
    )
    experience_base.record_metric_value(
        "task-1", metric_id=metric.id, metric_version=metric.version, value=12
    )

    redefine_goal(experience_base, goal.id)

    [record] = experience_base.data_package_records()
    assert [(g.id, g.version, g.statement.issue) for g in record.goals] == [
        (goal.id, 1, "wasted tool calls")
    ]
    output = tmp_path / "data-packages.parquet"
    experience_base.export_data_packages(output)
    [row] = pq.read_table(output).to_pylist()  # pyright: ignore[reportUnknownMemberType]
    assert [(g["id"], g["version"], g["issue"]) for g in row["goals"]] == [
        (goal.id, 1, "wasted tool calls")
    ]
