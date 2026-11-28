"""The Packager: the Experience Factory role that maintains the Experience Base (#4, AS-001).

It is the only writer of the Experience Base (ADR-0001). A run is triggered periodically by a
scheduled timer (ADR-0004). Admission, promotion, validation, scoping and retirement come in later
tickets; for now a run completes without changing anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experience_factory.storage import PackageStore


class Packager:
    """Runs the Packager over the Experience Base."""

    def __init__(self, store: PackageStore) -> None:
        self._store = store

    def run(self) -> None:
        """One periodic Packager run across all Tasks. It does nothing yet."""
