"""Evidence Packs: the Project Agent's structured, checkable account of its Task (DS-002).

The format is the `evidence` skill's template, generalized: the core sections are required, and the
coding-specific sections form an optional coding profile. A Harness Adapter submits the pack at Task
end, and the core only collects it; publishing it to an issue tracker is not the core's concern.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from experience_factory.tasks import NoSuchTaskError, TaskNotOpenError

if TYPE_CHECKING:
    from experience_factory.storage import EvidencePackStore, TaskStore


class EvidencePackError(ValueError):
    """The core refused an Evidence Pack a Harness Adapter submitted."""


class InvalidClaimStatusError(EvidencePackError):
    """A status in the Evidence Pack is not one of the six claim statuses."""


class EvidencePackSchemaError(EvidencePackError, TypeError):
    """The Harness Adapter submitted something other than the core's Evidence Pack format, such as
    a pack missing a core section."""


class ClaimStatus(StrEnum):
    """The six claim statuses, the full vocabulary for every status in an Evidence Pack.

    Never round `NOT_RUN` or `UNKNOWN` up to `PASS`: a status reflects what was actually checked,
    not what is likely true.
    """

    PASS = "PASS"
    """A specific command, diff or check ran and confirms the claim."""

    FAIL = "FAIL"
    """A specific command, diff or check ran and shows the claim does not hold."""

    PARTIAL = "PARTIAL"
    """Verified for some, but not all, of the claim's scope."""

    NOT_RUN = "NOT_RUN"
    """A check exists for the claim but was not executed this time."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    """No relevant check exists for the claim."""

    UNKNOWN = "UNKNOWN"
    """A check was attempted but produced no clear pass or fail signal."""


@dataclass(frozen=True)
class Claim:
    """One row of the scope-to-proof map: a requirement or property the Project Agent claims, its
    status, and the ids of the evidence items behind it."""

    id: str
    requirement: str
    status: str
    evidence_ids: tuple[str, ...] = ()
    source: str | None = None
    verification: str | None = None


@dataclass(frozen=True)
class PlanLedger:
    """What the Project Agent planned, what it actually did, and each deviation between the two."""

    conceptual_plan: str
    executed_approach: str
    deviations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RejectedAlternative:
    alternative: str
    why_rejected: str


@dataclass(frozen=True)
class Rationale:
    """Why the Project Agent took its approach: the alternatives it rejected and the trade-offs."""

    approach_taken: str
    rejected_alternatives: tuple[RejectedAlternative, ...] = ()
    trade_offs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RisksAndAssumptions:
    """What could still be wrong with the work, and what it rests on."""

    risks: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    incomplete_work: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    follow_up_work: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence (an `EVD-###` artifact): what kind it is, its status, the claims it
    supports, and where to find it. `command` and `exit_code` apply when a command produced it."""

    id: str
    category: str
    status: str
    claim_ids: tuple[str, ...] = ()
    pointer: str | None = None
    command: str | None = None
    exit_code: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Manifest:
    """The machine-readable index of the pack: its overall status, who produced it and when, and
    every evidence item its claims cite."""

    overall_status: str
    producer: str
    generated_at: str | None = None
    evidence: tuple[EvidenceItem, ...] = ()


@dataclass(frozen=True)
class ChangeInventory:
    """What the Task changed in the repository, and what it deliberately left alone."""

    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    config_or_schema_changes: tuple[str, ...] = ()
    externally_visible_changes: tuple[str, ...] = ()
    intentionally_untouched: tuple[str, ...] = ()


@dataclass(frozen=True)
class HygieneCheck:
    """One engineering hygiene category (linting, type checking, build and so on) and its status.
    A category that was not checked is `NOT_RUN`, never left out in a way that implies a pass."""

    category: str
    status: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryRevisions:
    """Where in the repository the work happened: the branch, the revisions it started from and
    ended at, and whether the working tree was clean."""

    repository: str
    branch: str | None = None
    base_revision: str | None = None
    current_revision: str | None = None
    working_tree_state: str | None = None


@dataclass(frozen=True)
class CodingProfile:
    """The optional sections of an Evidence Pack for a coding Task."""

    change_inventory: ChangeInventory
    hygiene: tuple[HygieneCheck, ...]
    revisions: RepositoryRevisions


@dataclass(frozen=True)
class EvidencePack:
    """A Project Agent's Evidence Pack for one Task: the core sections, all required, and the
    optional coding profile."""

    claims: tuple[Claim, ...]
    plan: PlanLedger
    rationale: Rationale
    exploration_archive: tuple[str, ...]
    risks: RisksAndAssumptions
    manifest: Manifest
    coding_profile: CodingProfile | None = None


class EvidencePacks:
    """Accepts Evidence Packs from Harness Adapters and stores one per Task."""

    def __init__(self, store: EvidencePackStore, tasks: TaskStore) -> None:
        self._store = store
        self._tasks = tasks

    def submit(self, task_id: str, pack: EvidencePack) -> None:
        _check_format(pack)
        _check_statuses(pack)
        if not self._store.put_evidence_pack(task_id, pack):
            self._require_task(task_id)
            raise TaskNotOpenError(
                f"Task {task_id!r} has ended; it no longer takes an Evidence Pack"
            )

    def evidence_pack(self, task_id: str) -> EvidencePack | None:
        self._require_task(task_id)
        return self._store.evidence_pack(task_id)

    def _require_task(self, task_id: str) -> None:
        if self._tasks.find_task(task_id) is None:
            raise NoSuchTaskError(f"no Task with id {task_id!r}")


def _check_format(pack: object) -> None:
    """Refuse `pack` unless it is an Evidence Pack with every core section, and the coding profile
    only if it is one. The static types say the same, but nothing makes a Harness Adapter heed
    them."""
    if not isinstance(pack, EvidencePack):
        raise EvidencePackSchemaError(f"expected an EvidencePack, got {type(pack).__name__}")
    _check_section(pack.claims, "claims", tuple, Claim)
    _check_section(pack.plan, "plan", PlanLedger)
    _check_section(pack.rationale, "rationale", Rationale)
    _check_section(pack.exploration_archive, "exploration_archive", tuple, str)
    _check_section(pack.risks, "risks", RisksAndAssumptions)
    _check_section(pack.manifest, "manifest", Manifest)
    _check_section(pack.manifest.evidence, "manifest evidence", tuple, EvidenceItem)
    if pack.coding_profile is not None:
        _check_section(pack.coding_profile, "coding_profile", CodingProfile)
        _check_section(pack.coding_profile.hygiene, "coding_profile hygiene", tuple, HygieneCheck)


def _check_section(value: object, section: str, kind: type, item_kind: type | None = None) -> None:
    if not isinstance(value, kind):
        raise EvidencePackSchemaError(
            f"the Evidence Pack's {section} section must be a {kind.__name__},"
            f" got {type(value).__name__}"
        )
    if item_kind is not None:
        for item in cast(tuple[object, ...], value):
            if not isinstance(item, item_kind):
                raise EvidencePackSchemaError(
                    f"the Evidence Pack's {section} section holds a {type(item).__name__},"
                    f" not a {item_kind.__name__}"
                )


def _check_statuses(pack: EvidencePack) -> None:
    for claim in pack.claims:
        _check_status(claim.status, f"claim {claim.id!r}")
    _check_status(pack.manifest.overall_status, "the manifest's overall status")
    for item in pack.manifest.evidence:
        _check_status(item.status, f"evidence item {item.id!r}")
    if pack.coding_profile is not None:
        for check in pack.coding_profile.hygiene:
            _check_status(check.status, f"engineering hygiene category {check.category!r}")


_STATUSES = frozenset(ClaimStatus)


def _check_status(status: object, where: str) -> None:
    if not isinstance(status, str) or status not in _STATUSES:
        shown = json.dumps(status) if isinstance(status, str) else repr(status)
        raise InvalidClaimStatusError(
            f"{where} has status {shown}, which is not a claim status;"
            f" use one of {', '.join(ClaimStatus)}"
        )


# The stored form of a pack. Bump the version when the format changes, and keep reading the old.
_ENCODING_VERSION = 1


def encode_pack(pack: EvidencePack) -> str:
    """`pack` as JSON, the form it is stored in."""
    return json.dumps({"version": _ENCODING_VERSION, **asdict(pack)}, ensure_ascii=False)


def decode_pack(text: str) -> EvidencePack:
    """The pack `encode_pack` turned into `text`."""
    document: dict[str, Any] = json.loads(text)
    plan = document["plan"]
    rationale = document["rationale"]
    risks = document["risks"]
    manifest = document["manifest"]
    return EvidencePack(
        claims=tuple(
            Claim(
                id=claim["id"],
                requirement=claim["requirement"],
                status=claim["status"],
                evidence_ids=tuple(claim["evidence_ids"]),
                source=claim["source"],
                verification=claim["verification"],
            )
            for claim in document["claims"]
        ),
        plan=PlanLedger(
            conceptual_plan=plan["conceptual_plan"],
            executed_approach=plan["executed_approach"],
            deviations=tuple(plan["deviations"]),
        ),
        rationale=Rationale(
            approach_taken=rationale["approach_taken"],
            rejected_alternatives=tuple(
                RejectedAlternative(
                    alternative=alternative["alternative"],
                    why_rejected=alternative["why_rejected"],
                )
                for alternative in rationale["rejected_alternatives"]
            ),
            trade_offs=tuple(rationale["trade_offs"]),
        ),
        exploration_archive=tuple(document["exploration_archive"]),
        risks=RisksAndAssumptions(
            risks=tuple(risks["risks"]),
            assumptions=tuple(risks["assumptions"]),
            limitations=tuple(risks["limitations"]),
            incomplete_work=tuple(risks["incomplete_work"]),
            missing_evidence=tuple(risks["missing_evidence"]),
            follow_up_work=tuple(risks["follow_up_work"]),
        ),
        manifest=Manifest(
            overall_status=manifest["overall_status"],
            producer=manifest["producer"],
            generated_at=manifest["generated_at"],
            evidence=tuple(
                EvidenceItem(
                    id=item["id"],
                    category=item["category"],
                    status=item["status"],
                    claim_ids=tuple(item["claim_ids"]),
                    pointer=item["pointer"],
                    command=item["command"],
                    exit_code=item["exit_code"],
                    sha256=item["sha256"],
                )
                for item in manifest["evidence"]
            ),
        ),
        coding_profile=_decode_coding_profile(document["coding_profile"]),
    )


def _decode_coding_profile(profile: dict[str, Any] | None) -> CodingProfile | None:
    if profile is None:
        return None
    changes = profile["change_inventory"]
    revisions = profile["revisions"]
    return CodingProfile(
        change_inventory=ChangeInventory(
            added=tuple(changes["added"]),
            modified=tuple(changes["modified"]),
            deleted=tuple(changes["deleted"]),
            config_or_schema_changes=tuple(changes["config_or_schema_changes"]),
            externally_visible_changes=tuple(changes["externally_visible_changes"]),
            intentionally_untouched=tuple(changes["intentionally_untouched"]),
        ),
        hygiene=tuple(
            HygieneCheck(
                category=check["category"],
                status=check["status"],
                evidence_ids=tuple(check["evidence_ids"]),
            )
            for check in profile["hygiene"]
        ),
        revisions=RepositoryRevisions(
            repository=revisions["repository"],
            branch=revisions["branch"],
            base_revision=revisions["base_revision"],
            current_revision=revisions["current_revision"],
            working_tree_state=revisions["working_tree_state"],
        ),
    )
