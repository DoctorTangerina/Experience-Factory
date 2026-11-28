"""BS-002 and Evidence Pack collection: a Harness Adapter submits the Project Agent's Evidence Pack
for a Task through the core public API, and the core stores it only if its claim statuses use the
fixed vocabulary."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from experience_factory import (
    ChangeInventory,
    Claim,
    ClaimStatus,
    CodingProfile,
    EvidenceItem,
    EvidencePack,
    EvidencePackSchemaError,
    ExperienceBase,
    HygieneCheck,
    InvalidClaimStatusError,
    Manifest,
    NoSuchTaskError,
    PlanLedger,
    Rationale,
    RejectedAlternative,
    RepositoryRevisions,
    RisksAndAssumptions,
    open_experience_base,
)
from tests.support import FakeHarnessAdapter


def _sent(status: str) -> ClaimStatus:
    """`status` as a Harness Adapter sends it: the static type asks for a claim status, but nothing
    makes an adapter heed it, so the core checks every status it is given."""
    return cast(ClaimStatus, status)


def _core_pack(*, claim_status: str = "PASS") -> EvidencePack:
    """An Evidence Pack with every core section filled in and no coding profile."""
    return EvidencePack(
        claims=(
            Claim(
                id="CLM-001",
                requirement="A pack with an unknown claim status is rejected",
                status=_sent(claim_status),
                evidence_ids=("EVD-001",),
                source="BS-002 (DS-002, US-001)",
                verification="pytest tests/test_evidence_pack_collection.py",
            ),
        ),
        plan=PlanLedger(
            conceptual_plan="Validate claim statuses at submission, then store the pack",
            executed_approach="Validated every status field before storing",
            deviations=("Also checked the overall status",),
        ),
        rationale=Rationale(
            approach_taken="Reject the whole pack on the first invalid status",
            rejected_alternatives=(
                RejectedAlternative(
                    alternative="Store the pack and flag the invalid claim",
                    why_rejected="The Analyst would have to interpret free text",
                ),
            ),
            trade_offs=("An adapter must fix the pack before resubmitting",),
        ),
        exploration_archive=("Tried a free-text status column; dropped it",),
        risks=RisksAndAssumptions(
            risks=("Adapters that lower-case statuses will be rejected",),
            assumptions=("The Project Agent writes statuses in upper case",),
        ),
        manifest=Manifest(
            overall_status=ClaimStatus.PASS,
            producer="claude-code",
            evidence=(
                EvidenceItem(
                    id="EVD-001",
                    category="test",
                    status=ClaimStatus.PASS,
                    claim_ids=("CLM-001",),
                    command="uv run pytest",
                    exit_code=0,
                ),
            ),
        ),
    )


def _coding_profile(*, hygiene_status: str = "PASS") -> CodingProfile:
    return CodingProfile(
        change_inventory=ChangeInventory(
            added=("src/experience_factory/evidence_packs.py",),
            modified=("src/experience_factory/core.py",),
            config_or_schema_changes=("evidence_packs table",),
            externally_visible_changes=("ExperienceBase.submit_evidence_pack",),
            intentionally_untouched=("Task ending",),
        ),
        hygiene=(
            HygieneCheck(
                category="Type checking", status=_sent(hygiene_status), evidence_ids=("EVD-002",)
            ),
            HygieneCheck(category="Build", status=ClaimStatus.NOT_RUN),
        ),
        revisions=RepositoryRevisions(
            repository="DoctorTangerina/Experience-Factory",
            branch="15-evidence-pack-collection",
            base_revision="9aaccdd",
            current_revision="1a2b3c4",
            working_tree_state="clean",
        ),
    )


# BS-002: Evidence Pack claim statuses use the fixed vocabulary


def _with_overall_status(pack: EvidencePack, status: str) -> EvidencePack:
    return replace(pack, manifest=replace(pack.manifest, overall_status=_sent(status)))


def _with_evidence_status(pack: EvidencePack, status: str) -> EvidencePack:
    item = replace(pack.manifest.evidence[0], status=_sent(status))
    return replace(pack, manifest=replace(pack.manifest, evidence=(item,)))


@pytest.mark.parametrize(
    ("pack", "shown"),
    [
        pytest.param(_core_pack(claim_status="DONE"), '"DONE"', id="claim status"),
        pytest.param(_with_overall_status(_core_pack(), "Done"), '"Done"', id="overall status"),
        pytest.param(
            _with_evidence_status(_core_pack(), "pass"), '"pass"', id="evidence item status"
        ),
        pytest.param(
            replace(_core_pack(), coding_profile=_coding_profile(hygiene_status="SKIPPED")),
            '"SKIPPED"',
            id="engineering hygiene status",
        ),
    ],
)
def test_every_status_in_an_evidence_pack_must_be_a_claim_status(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase, pack: EvidencePack, shown: str
) -> None:
    task = adapter.start_session()

    with pytest.raises(InvalidClaimStatusError, match=shown):
        adapter.submit(task, pack)

    assert experience_base.evidence_pack(task.id) is None


@pytest.mark.parametrize("status", list(ClaimStatus))
def test_each_of_the_six_claim_statuses_is_accepted(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase, status: ClaimStatus
) -> None:
    task = adapter.start_session()
    pack = _with_evidence_status(_core_pack(claim_status=status), status)

    adapter.submit(task, _with_overall_status(pack, status))

    stored = experience_base.evidence_pack(task.id)
    assert stored is not None
    assert stored.claims[0].status == status


def test_an_evidence_pack_without_the_coding_profile_is_accepted(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    pack = _core_pack()

    adapter.submit(task, pack)

    assert experience_base.evidence_pack(task.id) == pack


@pytest.mark.parametrize(
    "section", ["claims", "plan", "rationale", "exploration_archive", "risks", "manifest"]
)
def test_an_evidence_pack_missing_a_core_section_is_rejected(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase, section: str
) -> None:
    task = adapter.start_session()
    missing: dict[str, Any] = {section: None}

    with pytest.raises(EvidencePackSchemaError, match=section):
        adapter.submit(task, replace(_core_pack(), **missing))

    assert experience_base.evidence_pack(task.id) is None


def test_something_other_than_an_evidence_pack_is_rejected(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    native: Any = {"claims": [{"id": "CLM-001", "status": "PASS"}]}

    with pytest.raises(EvidencePackSchemaError):
        adapter.submit(task, native)

    assert experience_base.evidence_pack(task.id) is None


def test_an_evidence_pack_with_the_coding_profile_is_stored_with_it(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    pack = replace(_core_pack(), coding_profile=_coding_profile())

    adapter.submit(task, pack)

    assert experience_base.evidence_pack(task.id) == pack


# Collection at Task end


def test_submitting_again_replaces_the_earlier_evidence_pack(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    adapter.submit(task, _core_pack(claim_status="NOT_RUN"))
    corrected = _core_pack(claim_status="PASS")

    adapter.submit(task, corrected)

    assert experience_base.evidence_pack(task.id) == corrected


def test_a_rejected_resubmission_keeps_the_earlier_evidence_pack(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    accepted = _core_pack()
    adapter.submit(task, accepted)

    with pytest.raises(InvalidClaimStatusError):
        adapter.submit(task, _core_pack(claim_status="DONE"))

    assert experience_base.evidence_pack(task.id) == accepted


def test_an_evidence_pack_is_still_stored_after_the_experience_base_is_reopened(
    db_path: Path,
) -> None:
    pack = replace(_core_pack(), coding_profile=_coding_profile())
    with open_experience_base(db_path) as experience_base:
        task = FakeHarnessAdapter(experience_base).start_session()
        FakeHarnessAdapter(experience_base).submit(task, pack)

    with open_experience_base(db_path) as reopened:
        assert reopened.evidence_pack(task.id) == pack


def test_an_evidence_pack_is_kept_once_its_task_ends(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    pack = _core_pack()
    adapter.submit(task, pack)

    experience_base.end_task(task.id)

    assert experience_base.evidence_pack(task.id) == pack


def test_an_ended_task_takes_its_evidence_pack_and_stays_ended(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    experience_base.end_task(task.id)
    pack = _core_pack()

    adapter.submit(task, pack)

    assert experience_base.evidence_pack(task.id) == pack
    assert not experience_base.get_task(task.id).is_open


def test_an_evidence_pack_submitted_after_its_task_ends_replaces_the_earlier_one(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    adapter.submit(task, _core_pack(claim_status="NOT_RUN"))
    experience_base.end_task(task.id)

    adapter.submit(task, _core_pack(claim_status="PASS"))

    assert experience_base.evidence_pack(task.id) == _core_pack(claim_status="PASS")


def test_an_evidence_pack_for_an_unknown_task_is_refused(
    experience_base: ExperienceBase,
) -> None:
    with pytest.raises(NoSuchTaskError):
        experience_base.submit_evidence_pack("no-such-task", _core_pack())


def test_each_task_keeps_its_own_evidence_pack(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    first = adapter.start_session()
    second = adapter.start_session()
    adapter.submit(first, _core_pack(claim_status="PASS"))
    adapter.submit(second, _core_pack(claim_status="FAIL"))

    assert experience_base.evidence_pack(first.id) == _core_pack(claim_status="PASS")
    assert experience_base.evidence_pack(second.id) == _core_pack(claim_status="FAIL")
