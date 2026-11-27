"""BS-003: Only approved Project Goals can be selected by Tasks, through the core public API."""

from pathlib import Path

import pytest

from experience_memory import (
    ApprovalStateError,
    ExperienceMemory,
    Goal,
    UnknownElementError,
    open_memory,
)

PROJECT = "experience-memory"


@pytest.fixture
def proposed(memory: ExperienceMemory) -> Goal:
    """A Project Goal the Experience Factory proposed from the Project's Characterization."""
    return memory.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )


def selectable_ids(memory: ExperienceMemory, project: str = PROJECT) -> list[str]:
    return [goal.id for goal in memory.selectable_project_goals(project)]


def test_a_proposed_project_goal_is_not_selectable(
    memory: ExperienceMemory, proposed: Goal
) -> None:
    assert proposed.id not in selectable_ids(memory)


def test_an_approved_project_goal_becomes_selectable(
    memory: ExperienceMemory, proposed: Goal
) -> None:
    memory.approve_goal(proposed.id)

    [selectable] = memory.selectable_project_goals(PROJECT)
    assert selectable.id == proposed.id
    assert selectable.issue == "flaky test reruns"


def test_a_rejected_project_goal_is_not_selectable(
    memory: ExperienceMemory, proposed: Goal
) -> None:
    memory.reject_goal(proposed.id)

    assert proposed.id not in selectable_ids(memory)


def test_a_rejected_project_goal_cannot_be_approved_afterwards(
    memory: ExperienceMemory, proposed: Goal
) -> None:
    memory.reject_goal(proposed.id)

    with pytest.raises(ApprovalStateError):
        memory.approve_goal(proposed.id)

    assert proposed.id not in selectable_ids(memory)


def test_an_approved_project_goal_is_selectable_only_in_its_own_project(
    memory: ExperienceMemory, proposed: Goal
) -> None:
    memory.approve_goal(proposed.id)

    assert selectable_ids(memory, "another-project") == []


def test_organization_goals_are_not_listed_as_project_goals(memory: ExperienceMemory) -> None:
    memory.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    assert selectable_ids(memory) == []


def test_approving_an_unknown_goal_is_rejected(memory: ExperienceMemory) -> None:
    with pytest.raises(UnknownElementError):
        memory.approve_goal("no-such-goal")


def test_an_approval_persists_across_reopening(db_path: Path) -> None:
    with open_memory(db_path) as memory:
        goal = memory.propose_project_goal(
            PROJECT,
            purpose="reduce",
            issue="flaky test reruns",
            object="agent Tasks",
            viewpoint="the Project",
        )
        memory.approve_goal(goal.id)

    with open_memory(db_path) as reopened:
        assert selectable_ids(reopened) == [goal.id]
