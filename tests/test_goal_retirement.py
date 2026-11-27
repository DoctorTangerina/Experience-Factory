"""BS-005: Retiring a Goal keeps its data, through the core public API."""

import pytest

from experience_memory import (
    ApprovalStateError,
    Characterization,
    ExperienceBase,
    Goal,
    MetricKind,
)

PROJECT = "experience-memory"
CHARACTERIZATION = Characterization(schema_version="1", attributes={"task_type": "bugfix"})


@pytest.fixture
def approved(experience_base: ExperienceBase) -> Goal:
    goal = experience_base.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )
    experience_base.approve_goal(goal.id)
    return goal


def selectable_ids(experience_base: ExperienceBase) -> list[str]:
    return [goal.id for goal in experience_base.selectable_project_goals(PROJECT)]


def test_a_retired_project_goal_is_no_longer_selectable_and_keeps_its_recorded_values(
    experience_base: ExperienceBase, approved: Goal
) -> None:
    question = experience_base.add_question(approved.id, text="How often are tests rerun?")
    reruns = experience_base.add_metric(
        question.id,
        name="test reruns per Task",
        definition="Number of times the Task reran a test suite it had already run.",
        kind=MetricKind.OBJECTIVE,
    )
    for task_id, value in [("task-1", 2), ("task-2", 0)]:
        experience_base.record_task(
            task_id, characterization=CHARACTERIZATION, goal_ids=[approved.id], holdout=False
        )
        experience_base.record_metric_value(
            task_id, metric_id=reruns.id, metric_version=reruns.version, value=value
        )
    before = experience_base.data_package_records()

    experience_base.retire_goal(approved.id)

    assert approved.id not in selectable_ids(experience_base)
    assert experience_base.data_package_records() == before
    assert [(r.task_id, r.value, [g.id for g in r.goals]) for r in before] == [
        ("task-1", 2, [approved.id]),
        ("task-2", 0, [approved.id]),
    ]


def test_a_retired_goal_cannot_be_approved_again(
    experience_base: ExperienceBase, approved: Goal
) -> None:
    experience_base.retire_goal(approved.id)

    with pytest.raises(ApprovalStateError):
        experience_base.approve_goal(approved.id)

    assert approved.id not in selectable_ids(experience_base)


def test_a_proposed_goal_cannot_be_retired(experience_base: ExperienceBase) -> None:
    proposed = experience_base.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )

    with pytest.raises(ApprovalStateError):
        experience_base.retire_goal(proposed.id)

    experience_base.approve_goal(proposed.id)
    assert selectable_ids(experience_base) == [proposed.id]


def test_retiring_one_project_goal_leaves_the_others_selectable(
    experience_base: ExperienceBase, approved: Goal
) -> None:
    other = experience_base.propose_project_goal(
        PROJECT,
        purpose="understand",
        issue="why migrations fail",
        object="agent Tasks",
        viewpoint="the Project",
    )
    experience_base.approve_goal(other.id)

    experience_base.retire_goal(approved.id)

    assert selectable_ids(experience_base) == [other.id]


def test_a_retired_organization_goal_leaves_the_gqm_plan_in_force(
    experience_base: ExperienceBase,
) -> None:
    goal = experience_base.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    experience_base.retire_goal(goal.id)

    assert experience_base.list_organization_goals() == []
