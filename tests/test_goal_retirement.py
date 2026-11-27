"""BS-005: Retiring a Goal keeps its data, through the core public API."""

import pytest

from experience_memory import (
    ApprovalStateError,
    Characterization,
    ExperienceMemory,
    Goal,
    MetricKind,
)

PROJECT = "experience-memory"
CHARACTERIZATION = Characterization(schema_version="1", attributes={"task_type": "bugfix"})


@pytest.fixture
def approved(memory: ExperienceMemory) -> Goal:
    goal = memory.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )
    memory.approve_goal(goal.id)
    return goal


def selectable_ids(memory: ExperienceMemory) -> list[str]:
    return [goal.id for goal in memory.selectable_project_goals(PROJECT)]


def test_a_retired_project_goal_is_no_longer_selectable_and_keeps_its_recorded_values(
    memory: ExperienceMemory, approved: Goal
) -> None:
    question = memory.add_question(approved.id, text="How often are tests rerun?")
    reruns = memory.add_metric(
        question.id,
        name="test reruns per Task",
        definition="Number of times the Task reran a test suite it had already run.",
        kind=MetricKind.OBJECTIVE,
    )
    for task_id, value in [("task-1", 2), ("task-2", 0)]:
        memory.record_task(
            task_id, characterization=CHARACTERIZATION, goal_ids=[approved.id], holdout=False
        )
        memory.record_metric_value(
            task_id, metric_id=reruns.id, metric_version=reruns.version, value=value
        )
    before = memory.data_package_records()

    memory.retire_goal(approved.id)

    assert approved.id not in selectable_ids(memory)
    assert memory.data_package_records() == before
    assert [(r.task_id, r.value, [g.id for g in r.goals]) for r in before] == [
        ("task-1", 2, [approved.id]),
        ("task-2", 0, [approved.id]),
    ]


def test_a_retired_goal_cannot_be_approved_again(memory: ExperienceMemory, approved: Goal) -> None:
    memory.retire_goal(approved.id)

    with pytest.raises(ApprovalStateError):
        memory.approve_goal(approved.id)

    assert approved.id not in selectable_ids(memory)


def test_a_proposed_goal_cannot_be_retired(memory: ExperienceMemory) -> None:
    proposed = memory.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )

    with pytest.raises(ApprovalStateError):
        memory.retire_goal(proposed.id)

    memory.approve_goal(proposed.id)
    assert selectable_ids(memory) == [proposed.id]


def test_retiring_one_project_goal_leaves_the_others_selectable(
    memory: ExperienceMemory, approved: Goal
) -> None:
    other = memory.propose_project_goal(
        PROJECT,
        purpose="understand",
        issue="why migrations fail",
        object="agent Tasks",
        viewpoint="the Project",
    )
    memory.approve_goal(other.id)

    memory.retire_goal(approved.id)

    assert selectable_ids(memory) == [other.id]


def test_a_retired_organization_goal_leaves_the_gqm_plan_in_force(
    memory: ExperienceMemory,
) -> None:
    goal = memory.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    memory.retire_goal(goal.id)

    assert memory.list_organization_goals() == []
