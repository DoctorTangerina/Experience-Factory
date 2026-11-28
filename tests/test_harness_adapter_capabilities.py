"""BS-005: Harness Adapters declare their optional capabilities through the core public API, and
the Advisor reads them back."""

from collections.abc import Iterable
from pathlib import Path

import pytest

from experience_factory import (
    ExperienceBase,
    HarnessCapability,
    UnknownHarnessAdapterError,
    open_experience_base,
)


class FakeHarnessAdapter:
    """Declares its capabilities the way a Harness Adapter does, using only the core public API."""

    def __init__(self, experience_base: ExperienceBase, name: str = "fake-harness") -> None:
        self._experience_base = experience_base
        self.name = name

    def declare(self, capabilities: Iterable[HarnessCapability]) -> None:
        self._experience_base.declare_harness_adapter(self.name, capabilities=capabilities)


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
    FakeHarnessAdapter(experience_base, "renders").declare([HarnessCapability.NATIVE_RENDERING])
    FakeHarnessAdapter(experience_base, "plain").declare([])

    assert not experience_base.harness_adapter_capabilities("plain").supports(
        HarnessCapability.NATIVE_RENDERING
    )


def test_reading_an_adapter_that_never_declared_is_refused(
    experience_base: ExperienceBase,
) -> None:
    with pytest.raises(UnknownHarnessAdapterError):
        experience_base.harness_adapter_capabilities("never-declared")
