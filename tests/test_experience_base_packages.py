"""#11: Packages in every state can be arranged in the Experience Base (through the test-only seam,
since only the Packager writes it) and inspected through the core public API."""

from pathlib import Path

import pytest

from experience_factory import (
    ApplicabilityScope,
    Goal,
    MissingReasonError,
    PackageState,
    PackageType,
    Provenance,
    ReplacementError,
    StateChange,
    UnknownElementError,
    UnknownPackageError,
)
from tests.support import PROJECT, ArrangeableExperienceBase, define_goal
from tests.support import open_arrangeable_experience_base as open_experience_base


def test_an_arranged_package_is_inspected_with_its_whole_record(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    arranged = experience_base.arrange_package(
        PackageState.CANDIDATE,
        goal_ids=[goal.id],
        title="Run the failing test alone first",
        scope=ApplicabilityScope(project=PROJECT, attributes={"languages": frozenset({"python"})}),
        evidence=["task-1#span-3"],
        provenance=Provenance(project=PROJECT, task_ids=("task-1",)),
        reason="recurred in 3 Tasks",
    )

    inspected = experience_base.package(arranged.id)

    assert inspected == arranged
    assert inspected.type is PackageType.PROCESS
    assert inspected.state is PackageState.CANDIDATE
    assert inspected.title == "Run the failing test alone first"
    assert inspected.scope == ApplicabilityScope(
        project=PROJECT, attributes={"languages": frozenset({"python"})}
    )
    assert inspected.goal_ids == (goal.id,)
    assert inspected.evidence == ("task-1#span-3",)
    assert inspected.provenance == Provenance(project=PROJECT, task_ids=("task-1",))
    assert inspected.history == (StateChange(PackageState.CANDIDATE, "recurred in 3 Tasks"),)
    assert inspected.superseded_by is None


@pytest.mark.parametrize(
    "state",
    [
        PackageState.LESSON_LEARNED,
        PackageState.CANDIDATE,
        PackageState.VALIDATED,
        PackageState.RETIRED,
    ],
)
def test_a_package_can_be_arranged_in_each_state(
    experience_base: ArrangeableExperienceBase, goal: Goal, state: PackageState
) -> None:
    arranged = experience_base.arrange_package(state, goal_ids=[goal.id])

    assert experience_base.package(arranged.id).state is state


@pytest.mark.parametrize(
    ("state", "is_live"),
    [
        (PackageState.LESSON_LEARNED, True),
        (PackageState.CANDIDATE, True),
        (PackageState.VALIDATED, True),
        (PackageState.RETIRED, False),
        (PackageState.SUPERSEDED, False),
    ],
)
def test_a_package_is_live_unless_retired_or_superseded(
    experience_base: ArrangeableExperienceBase, goal: Goal, state: PackageState, is_live: bool
) -> None:
    replacement = experience_base.arrange_package(PackageState.VALIDATED, goal_ids=[goal.id])
    arranged = experience_base.arrange_package(
        state,
        goal_ids=[goal.id],
        superseded_by=replacement.id if state is PackageState.SUPERSEDED else None,
    )

    assert experience_base.package(arranged.id).is_live is is_live


def test_a_superseded_package_links_to_its_replacement(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    replacement = experience_base.arrange_package(PackageState.VALIDATED, goal_ids=[goal.id])

    superseded = experience_base.arrange_package(
        PackageState.SUPERSEDED,
        goal_ids=[goal.id],
        reason="replaced by a broader Package",
        superseded_by=replacement.id,
    )

    inspected = experience_base.package(superseded.id)
    assert inspected.state is PackageState.SUPERSEDED
    assert inspected.superseded_by == replacement.id
    assert inspected.history == (
        StateChange(PackageState.SUPERSEDED, "replaced by a broader Package"),
    )


def test_an_organization_scoped_package_has_no_project_in_its_scope(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    arranged = experience_base.arrange_package(
        PackageState.VALIDATED,
        type=PackageType.TOOL,
        title="pytest -p no:cacheprovider in read-only checkouts",
        summary="Disable the cache provider when the checkout is read-only.",
        content="pytest fails writing .pytest_cache in a read-only checkout.",
        scope=ApplicabilityScope(project=None, attributes={}),
        goal_ids=[goal.id],
        evidence=[],
        provenance=Provenance(project=PROJECT, task_ids=()),
        reason="validated in 5 Projects",
    )

    assert experience_base.package(arranged.id).scope == ApplicabilityScope(
        project=None, attributes={}
    )


def test_packages_are_listed_in_the_order_arranged_and_can_be_filtered_by_state(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    lesson = experience_base.arrange_package(
        PackageState.LESSON_LEARNED, goal_ids=[goal.id], title="first"
    )
    validated = experience_base.arrange_package(
        PackageState.VALIDATED, goal_ids=[goal.id], title="second"
    )
    retired = experience_base.arrange_package(
        PackageState.RETIRED, goal_ids=[goal.id], title="third"
    )

    assert experience_base.packages() == [lesson, validated, retired]
    assert experience_base.packages(state=PackageState.VALIDATED) == [validated]
    assert experience_base.packages(state=PackageState.CANDIDATE) == []


def test_arranged_packages_survive_reopening_the_experience_base(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = define_goal(experience_base)
        replacement = experience_base.arrange_package(PackageState.VALIDATED, goal_ids=[goal.id])
        superseded = experience_base.arrange_package(
            PackageState.SUPERSEDED, goal_ids=[goal.id], superseded_by=replacement.id
        )

    with open_experience_base(db_path) as reopened:
        assert reopened.packages() == [replacement, superseded]


def test_inspecting_an_unknown_package_is_refused(
    experience_base: ArrangeableExperienceBase,
) -> None:
    with pytest.raises(UnknownPackageError):
        experience_base.package("no-such-package")


def test_a_package_linked_to_an_unknown_goal_is_refused(
    experience_base: ArrangeableExperienceBase,
) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.arrange_package(goal_ids=["no-such-goal"])

    assert experience_base.packages() == []


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_package_without_a_reason_for_its_state_is_refused(
    experience_base: ArrangeableExperienceBase, goal: Goal, reason: str
) -> None:
    with pytest.raises(MissingReasonError):
        experience_base.arrange_package(PackageState.RETIRED, goal_ids=[goal.id], reason=reason)

    assert experience_base.packages() == []


def test_a_superseded_package_without_a_replacement_is_refused(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    with pytest.raises(ReplacementError):
        experience_base.arrange_package(PackageState.SUPERSEDED, goal_ids=[goal.id])

    assert experience_base.packages() == []


def test_a_superseded_package_whose_replacement_does_not_exist_is_refused(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    with pytest.raises(UnknownPackageError):
        experience_base.arrange_package(
            PackageState.SUPERSEDED, goal_ids=[goal.id], superseded_by="no-such-package"
        )

    assert experience_base.packages() == []


def test_a_replacement_on_a_package_that_is_not_superseded_is_refused(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    other = experience_base.arrange_package(PackageState.VALIDATED, goal_ids=[goal.id])

    with pytest.raises(ReplacementError):
        experience_base.arrange_package(
            PackageState.VALIDATED, goal_ids=[goal.id], superseded_by=other.id
        )

    assert experience_base.packages() == [other]
