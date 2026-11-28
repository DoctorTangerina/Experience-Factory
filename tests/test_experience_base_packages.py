"""#11: Packages in every state can be arranged and inspected through the core public API."""

from pathlib import Path

import pytest

from experience_factory import (
    ApplicabilityScope,
    ExperienceBase,
    Goal,
    MissingReasonError,
    Package,
    PackageState,
    PackageType,
    Provenance,
    ReplacementError,
    StateChange,
    UnknownElementError,
    UnknownPackageError,
    open_experience_base,
)

PROJECT = "experience-factory"


@pytest.fixture
def goal(experience_base: ExperienceBase) -> Goal:
    goal = experience_base.propose_project_goal(
        PROJECT,
        purpose="reduce",
        issue="flaky test reruns",
        object="agent Tasks",
        viewpoint="the Project",
    )
    experience_base.approve_goal(goal.id)
    return goal


def arrange(
    experience_base: ExperienceBase,
    goal: Goal,
    state: PackageState = PackageState.LESSON_LEARNED,
    *,
    title: str = "Run the failing test alone first",
    reason: str = "arranged by the test",
    superseded_by: str | None = None,
) -> Package:
    return experience_base.arrange_package(
        type=PackageType.PROCESS,
        state=state,
        title=title,
        summary="Rerun only the failing test before rerunning the suite.",
        content="When a test fails, rerun it alone to see whether it is flaky.",
        scope=ApplicabilityScope(project=PROJECT, attributes={"languages": frozenset({"python"})}),
        goal_ids=[goal.id],
        evidence=["task-1#span-3"],
        provenance=Provenance(project=PROJECT, task_ids=("task-1",)),
        reason=reason,
        superseded_by=superseded_by,
    )


def test_an_arranged_package_is_inspected_with_its_whole_record(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    arranged = arrange(experience_base, goal, PackageState.CANDIDATE, reason="recurred in 3 Tasks")

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
    experience_base: ExperienceBase, goal: Goal, state: PackageState
) -> None:
    arranged = arrange(experience_base, goal, state)

    assert experience_base.package(arranged.id).state is state


def test_a_superseded_package_links_to_its_replacement(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    replacement = arrange(experience_base, goal, PackageState.VALIDATED)

    superseded = arrange(
        experience_base,
        goal,
        PackageState.SUPERSEDED,
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
    experience_base: ExperienceBase, goal: Goal
) -> None:
    arranged = experience_base.arrange_package(
        type=PackageType.TOOL,
        state=PackageState.VALIDATED,
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
    experience_base: ExperienceBase, goal: Goal
) -> None:
    lesson = arrange(experience_base, goal, PackageState.LESSON_LEARNED, title="first")
    validated = arrange(experience_base, goal, PackageState.VALIDATED, title="second")
    retired = arrange(experience_base, goal, PackageState.RETIRED, title="third")

    assert experience_base.packages() == [lesson, validated, retired]
    assert experience_base.packages(state=PackageState.VALIDATED) == [validated]
    assert experience_base.packages(state=PackageState.CANDIDATE) == []


def test_arranged_packages_survive_reopening_the_experience_base(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = experience_base.define_organization_goal(
            purpose="understand",
            issue="why Tasks fail",
            object="agent Tasks",
            viewpoint="the Organization",
        )
        replacement = arrange(experience_base, goal, PackageState.VALIDATED)
        superseded = arrange(
            experience_base, goal, PackageState.SUPERSEDED, superseded_by=replacement.id
        )

    with open_experience_base(db_path) as reopened:
        assert reopened.packages() == [replacement, superseded]


def test_inspecting_an_unknown_package_is_refused(experience_base: ExperienceBase) -> None:
    with pytest.raises(UnknownPackageError):
        experience_base.package("no-such-package")


def test_a_package_linked_to_an_unknown_goal_is_refused(experience_base: ExperienceBase) -> None:
    with pytest.raises(UnknownElementError):
        experience_base.arrange_package(
            type=PackageType.PROCESS,
            state=PackageState.LESSON_LEARNED,
            title="t",
            summary="s",
            content="c",
            scope=ApplicabilityScope(project=PROJECT, attributes={}),
            goal_ids=["no-such-goal"],
            evidence=[],
            provenance=Provenance(project=PROJECT, task_ids=()),
            reason="arranged by the test",
        )

    assert experience_base.packages() == []


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_package_without_a_reason_for_its_state_is_refused(
    experience_base: ExperienceBase, goal: Goal, reason: str
) -> None:
    with pytest.raises(MissingReasonError):
        arrange(experience_base, goal, PackageState.RETIRED, reason=reason)

    assert experience_base.packages() == []


def test_a_superseded_package_without_a_replacement_is_refused(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    with pytest.raises(ReplacementError):
        arrange(experience_base, goal, PackageState.SUPERSEDED)

    assert experience_base.packages() == []


def test_a_superseded_package_whose_replacement_does_not_exist_is_refused(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    with pytest.raises(UnknownPackageError):
        arrange(experience_base, goal, PackageState.SUPERSEDED, superseded_by="no-such-package")

    assert experience_base.packages() == []


def test_a_replacement_on_a_package_that_is_not_superseded_is_refused(
    experience_base: ExperienceBase, goal: Goal
) -> None:
    other = arrange(experience_base, goal, PackageState.VALIDATED)

    with pytest.raises(ReplacementError):
        arrange(experience_base, goal, PackageState.VALIDATED, superseded_by=other.id)

    assert experience_base.packages() == [other]
