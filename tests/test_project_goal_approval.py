"""BS-003: Only approved Project Goals can be selected by Tasks, through the core public API."""

from pathlib import Path

import pytest

from experience_memory import (
    ApprovalStateError,
    ExperienceBase,
    Goal,
    UnknownElementError,
    open_experience_base,
)

PROJECT = "experience-memory"


@pytest.fixture
def proposed(experience_base: ExperienceBase) -> Goal:
    """A Project Goal the Experience Factory proposed from the Project's Characterization."""
    return experience_base.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )


def selectable_ids(experience_base: ExperienceBase, project: str = PROJECT) -> list[str]:
    return [goal.id for goal in experience_base.selectable_project_goals(project)]


def test_a_proposed_project_goal_is_not_selectable(
    experience_base: ExperienceBase, proposed: Goal
) -> None:
    assert proposed.id not in selectable_ids(experience_base)


def test_an_approved_project_goal_becomes_selectable(
    experience_base: ExperienceBase, proposed: Goal
) -> None:
    experience_base.approve_goal(proposed.id)

    [selectable] = experience_base.selectable_project_goals(PROJECT)
    assert selectable.id == proposed.id
    assert selectable.statement.issue == "flaky test reruns"


def test_a_rejected_project_goal_is_not_selectable(
    experience_base: ExperienceBase, proposed: Goal
) -> None:
    experience_base.reject_goal(proposed.id)

    assert proposed.id not in selectable_ids(experience_base)


def test_a_rejected_project_goal_cannot_be_approved_afterwards(
    experience_base: ExperienceBase, proposed: Goal
) -> None:
    experience_base.reject_goal(proposed.id)

    with pytest.raises(ApprovalStateError):
        experience_base.approve_goal(proposed.id)

    assert proposed.id not in selectable_ids(experience_base)


def test_an_approved_project_goal_is_selectable_only_in_its_own_project(
    experience_base: ExperienceBase, proposed: Goal
) -> None:
    experience_base.approve_goal(proposed.id)

    assert selectable_ids(experience_base, "another-project") == []


def test_organization_goals_are_not_listed_as_project_goals(
    experience_base: ExperienceBase,
) -> None:
    experience_base.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    assert selectable_ids(experience_base) == []


def test_approving_an_unknown_goal_is_rejected(experience_base: ExperienceBase) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.approve_goal("no-such-goal")


def test_an_approval_persists_across_reopening(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = experience_base.propose_project_goal(
            PROJECT,
            purpose="reduce",
            issue="flaky test reruns",
            object="agent Tasks",
            viewpoint="the Project",
        )
        experience_base.approve_goal(goal.id)

    with open_experience_base(db_path) as reopened:
        assert selectable_ids(reopened) == [goal.id]
