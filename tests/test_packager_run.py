"""#11: A Packager run can be triggered through the core public API. It changes nothing yet, and
Retired and Superseded Packages are never deleted."""

from pathlib import Path

from experience_factory import (
    ApplicabilityScope,
    ExperienceBase,
    Goal,
    Package,
    PackageState,
    PackageType,
    Provenance,
    open_experience_base,
)

PROJECT = "experience-factory"


def define_goal(experience_base: ExperienceBase) -> Goal:
    return experience_base.define_organization_goal(
        purpose="understand", issue="why Tasks fail", object="agent Tasks", viewpoint="the Org"
    )


def arrange(
    experience_base: ExperienceBase,
    goal: Goal,
    state: PackageState,
    superseded_by: str | None = None,
) -> Package:
    return experience_base.arrange_package(
        type=PackageType.PROCESS,
        state=state,
        title=f"a {state} Package",
        summary="summary",
        content="content",
        scope=ApplicabilityScope(project=PROJECT, attributes={"task_type": frozenset({"bugfix"})}),
        goal_ids=[goal.id],
        evidence=["task-1"],
        provenance=Provenance(project=PROJECT, task_ids=("task-1",)),
        reason=f"arranged as {state}",
        superseded_by=superseded_by,
    )


def arrange_every_state(experience_base: ExperienceBase) -> list[Package]:
    goal = define_goal(experience_base)
    arranged = [
        arrange(experience_base, goal, state)
        for state in (
            PackageState.LESSON_LEARNED,
            PackageState.CANDIDATE,
            PackageState.VALIDATED,
            PackageState.RETIRED,
        )
    ]
    validated = arranged[2]
    arranged.append(arrange(experience_base, goal, PackageState.SUPERSEDED, validated.id))
    return arranged


def test_a_packager_run_on_an_empty_experience_base_completes(
    experience_base: ExperienceBase,
) -> None:
    experience_base.run_packager()

    assert experience_base.packages() == []


def test_a_packager_run_changes_no_package(experience_base: ExperienceBase) -> None:
    arranged = arrange_every_state(experience_base)

    experience_base.run_packager()

    assert experience_base.packages() == arranged


def test_retired_and_superseded_packages_are_kept_across_runs_and_reopening(
    db_path: Path,
) -> None:
    with open_experience_base(db_path) as experience_base:
        arranged = arrange_every_state(experience_base)
        experience_base.run_packager()
        experience_base.run_packager()

    with open_experience_base(db_path) as reopened:
        reopened.run_packager()
        assert reopened.packages(state=PackageState.RETIRED) == [arranged[3]]
        assert reopened.packages(state=PackageState.SUPERSEDED) == [arranged[4]]
        assert reopened.package(arranged[4].id).superseded_by == arranged[2].id
