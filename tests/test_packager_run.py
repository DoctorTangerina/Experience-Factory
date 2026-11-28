"""#11: A Packager run can be triggered through the core public API. It changes nothing yet, and
Retired and Superseded Packages are never deleted."""

from experience_factory import Goal, PackageState
from tests.support import ArrangeableExperienceBase


def test_a_packager_run_changes_no_package(
    experience_base: ArrangeableExperienceBase, goal: Goal
) -> None:
    arranged = [
        experience_base.arrange_package(state, goal_ids=[goal.id])
        for state in (
            PackageState.LESSON_LEARNED,
            PackageState.CANDIDATE,
            PackageState.VALIDATED,
            PackageState.RETIRED,
        )
    ]
    validated = arranged[2]
    arranged.append(
        experience_base.arrange_package(
            PackageState.SUPERSEDED, goal_ids=[goal.id], superseded_by=validated.id
        )
    )

    experience_base.run_packager()

    assert experience_base.packages() == arranged
