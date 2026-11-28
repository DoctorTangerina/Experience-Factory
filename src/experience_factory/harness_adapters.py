"""Harness Adapter capabilities: what each Harness Adapter supports beyond its mandatory duties.

Every Harness Adapter must report Task boundaries, hand over Traces, inject the Advisor's push,
expose pull and collect Evidence Packs. The capabilities here are the optional extras an adapter
declares, so the Advisor can adapt delivery to what the harness supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from experience_factory.storage import HarnessAdapterStore


class HarnessCapability(StrEnum):
    """An optional capability a Harness Adapter may declare."""

    NATIVE_RENDERING = "native_rendering"
    """Renders Packages (such as Process Packages) into the harness's own forms."""

    JUST_IN_TIME_DELIVERY = "just_in_time_delivery"
    """Delivers Packages during the Task, when they become relevant, not only at Task start."""

    HUMAN_IN_THE_LOOP_APPROVALS = "human_in_the_loop_approvals"
    """Can put an approval in front of a human from inside the harness."""


@dataclass(frozen=True)
class HarnessCapabilities:
    """The optional capabilities the Harness Adapter named `adapter` declared."""

    adapter: str
    supported: frozenset[HarnessCapability]

    def supports(self, capability: HarnessCapability) -> bool:
        return capability in self.supported


class UnknownHarnessAdapterError(LookupError):
    """No Harness Adapter by that name has declared its capabilities."""


class HarnessAdapters:
    """Keeps each Harness Adapter's latest capability declaration."""

    def __init__(self, store: HarnessAdapterStore) -> None:
        self._store = store

    def declare(self, adapter: str, capabilities: Iterable[HarnessCapability]) -> None:
        self._store.replace_harness_capabilities(
            adapter, frozenset(HarnessCapability(c) for c in capabilities)
        )

    def capabilities(self, adapter: str) -> HarnessCapabilities:
        supported = self._store.find_harness_capabilities(adapter)
        if supported is None:
            raise UnknownHarnessAdapterError(
                f"no Harness Adapter named {adapter!r} has declared its capabilities"
            )
        return HarnessCapabilities(adapter=adapter, supported=supported)
