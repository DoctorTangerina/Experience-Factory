"""Packages: the units of experience the Experience Base holds (CONTEXT.md, ADR-0003, #4).

A Package has a type from the adapted Basili taxonomy, a state in the package lifecycle, an
Applicability Scope, the Goals it serves, references to its evidence, its provenance and a history
of the states it has been in, each with the reason it entered that state. Retired and Superseded
Packages are kept with that history: the Experience Base never deletes a Package.

Only the Packager writes the Experience Base (ADR-0001), so the core public API offers no way to
write a Package. Tests put the Experience Base in any state through a test-only seam.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from experience_factory.gqm import is_blank

if TYPE_CHECKING:
    from experience_factory.storage import PackageStore


class PackageError(Exception):
    """The Experience Base refused a Package operation."""


class UnknownPackageError(PackageError, LookupError):
    """The operation names a Package that is not in the Experience Base."""


class MissingReasonError(PackageError, ValueError):
    """A Package was given a state without the reason it entered it. Every entry in a Package's
    state history carries a reason; a blank reason (empty or whitespace only) counts as none."""


class ReplacementError(PackageError, ValueError):
    """A Superseded Package names no replacement, or a Package that is not Superseded names one."""


class PackageType(StrEnum):
    """What a Package holds, after Basili's package taxonomy as adapted in ADR-0003."""

    PRODUCT = "product"
    PROCESS = "process"
    RELATIONSHIP = "relationship"
    TOOL = "tool"
    MANAGEMENT = "management"
    DATA = "data"


class PackageState(StrEnum):
    """Where a Package is in its lifecycle."""

    LESSON_LEARNED = "lesson_learned"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ApplicabilityScope:
    """Where a Package applies: the Project it is confined to, and the values it allows for each
    constrained Characterization attribute (docs/characterization-schema.md, Matching).

    `project` is None for an Organization-scoped Package. An attribute missing from `attributes`
    is not constrained.
    """

    project: str | None
    attributes: Mapping[str, frozenset[str]]

    def __post_init__(self) -> None:
        # Keep a private copy so a caller's later edits cannot change a stored scope.
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True)
class Provenance:
    """Where a Package came from: its origin Project and the Tasks it was learned from."""

    project: str
    task_ids: tuple[str, ...]


@dataclass(frozen=True)
class StateChange:
    """One entry of a Package's state history: the state it entered and why."""

    state: PackageState
    reason: str


@dataclass(frozen=True)
class Package:
    """One Package in the Experience Base.

    `title` and `summary` are what a Package Index lists; `content` is the experience itself.
    `goal_ids` are the Goals the Package is linked to, `evidence` references what supports it, and
    `history` lists the states it has been in, oldest first: its last entry is its current
    `state`. `superseded_by` is the id of the Package that replaced a Superseded Package.
    """

    id: str
    type: PackageType
    title: str
    summary: str
    content: str
    scope: ApplicabilityScope
    goal_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    provenance: Provenance
    history: tuple[StateChange, ...]
    superseded_by: str | None = None

    @property
    def state(self) -> PackageState:
        return self.history[-1].state

    @property
    def is_live(self) -> bool:
        """Whether the Package is live: not Retired or Superseded. Only live Lessons Learned and
        Packages keep the Trace spans they cite past retention."""
        return self.state in _LIVE_STATES


_LIVE_STATES = frozenset(
    {PackageState.LESSON_LEARNED, PackageState.CANDIDATE, PackageState.VALIDATED}
)


class ExperienceBasePackages:
    """Writes and inspects the Packages in the Experience Base, enforcing the record's rules."""

    def __init__(self, store: PackageStore) -> None:
        self._store = store

    def add(
        self,
        *,
        type: PackageType,
        state: PackageState,
        title: str,
        summary: str,
        content: str,
        scope: ApplicabilityScope,
        goal_ids: Iterable[str],
        evidence: Iterable[str],
        provenance: Provenance,
        reason: str,
        superseded_by: str | None,
    ) -> Package:
        """Write a Package into the Experience Base in `state`, entered for `reason`, and return
        it. Only the Packager may call this in operation (ADR-0001).

        Each linked Goal must exist. A Superseded Package must name the existing Package that
        replaced it as `superseded_by`, and no other Package may name one.
        """
        state = PackageState(state)
        if is_blank(reason):
            raise MissingReasonError(f"a Package entering state {state} needs a reason")
        if (state is PackageState.SUPERSEDED) != (superseded_by is not None):
            raise ReplacementError(
                "a Superseded Package must name its replacement, and only a Superseded one may"
            )
        if superseded_by is not None:
            self.package(superseded_by)
        # A Goal linked twice is one linked Goal.
        goal_ids = tuple(self._store.get_goal(goal_id).id for goal_id in dict.fromkeys(goal_ids))
        package = Package(
            id=uuid.uuid4().hex,
            type=PackageType(type),
            title=title,
            summary=summary,
            content=content,
            scope=scope,
            goal_ids=goal_ids,
            evidence=tuple(evidence),
            provenance=provenance,
            history=(StateChange(state, reason),),
            superseded_by=superseded_by,
        )
        self._store.add_package(package)
        return package

    def package(self, package_id: str) -> Package:
        package = self._store.find_package(package_id)
        if package is None:
            raise UnknownPackageError(f"no Package with id {package_id!r}")
        return package

    def packages(self, state: PackageState | None) -> list[Package]:
        return self._store.list_packages(None if state is None else PackageState(state))
