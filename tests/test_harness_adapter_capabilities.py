"""BS-005: Harness Adapters declare their optional capabilities through the core public API, and
the Advisor reads them back."""

from pathlib import Path

from experience_factory import (
    ExperienceBase,
    HarnessCapability,
    open_experience_base,
)
from tests.support import FakeHarnessAdapter


def test_a_declared_capability_is_visible_to_the_advisor(experience_base: ExperienceBase) -> None:
    adapter = FakeHarnessAdapter(experience_base)
    adapter.declare([HarnessCapability.NATIVE_RENDERING])

    capabilities = experience_base.harness_adapter_capabilities(adapter.name)

    assert capabilities.supports(HarnessCapability.NATIVE_RENDERING)
    assert not capabilities.supports(HarnessCapability.JUST_IN_TIME_DELIVERY)


def test_a_declaration_is_still_visible_after_the_experience_base_is_reopened(
    db_path: Path,
) -> None:
    with open_experience_base(db_path) as experience_base:
        FakeHarnessAdapter(experience_base).declare([HarnessCapability.HUMAN_IN_THE_LOOP_APPROVALS])

    with open_experience_base(db_path) as reopened:
        capabilities = reopened.harness_adapter_capabilities("fake-harness")

    assert capabilities.supports(HarnessCapability.HUMAN_IN_THE_LOOP_APPROVALS)
    assert not capabilities.supports(HarnessCapability.NATIVE_RENDERING)


def test_declaring_again_replaces_the_earlier_declaration(experience_base: ExperienceBase) -> None:
    adapter = FakeHarnessAdapter(experience_base)
    adapter.declare([HarnessCapability.NATIVE_RENDERING])

    adapter.declare([HarnessCapability.JUST_IN_TIME_DELIVERY])

    capabilities = experience_base.harness_adapter_capabilities(adapter.name)
    assert capabilities.supports(HarnessCapability.JUST_IN_TIME_DELIVERY)
    assert not capabilities.supports(HarnessCapability.NATIVE_RENDERING)


def test_an_adapter_declaring_no_optional_capabilities_supports_none(
    experience_base: ExperienceBase,
) -> None:
    adapter = FakeHarnessAdapter(experience_base)
    adapter.declare([])

    capabilities = experience_base.harness_adapter_capabilities(adapter.name)

    assert not any(capabilities.supports(capability) for capability in HarnessCapability)


def test_each_adapter_sees_only_its_own_declaration(experience_base: ExperienceBase) -> None:
    FakeHarnessAdapter(experience_base, name="renders").declare(
        [HarnessCapability.NATIVE_RENDERING]
    )
    FakeHarnessAdapter(experience_base, name="plain").declare([])

    assert not experience_base.harness_adapter_capabilities("plain").supports(
        HarnessCapability.NATIVE_RENDERING
    )


def test_an_adapter_that_never_declared_supports_no_optional_capabilities(
    experience_base: ExperienceBase,
) -> None:
    capabilities = experience_base.harness_adapter_capabilities("never-declared")

    assert not any(capabilities.supports(capability) for capability in HarnessCapability)
