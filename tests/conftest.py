"""Test harness: every core test drives the core public API, opened on a fresh database.

The Experience Base is the one the core opens, plus the test-only way to arrange Packages in it
(see `tests/support.py`).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from experience_factory import Goal
from tests.support import (
    ArrangeableExperienceBase,
    FakeHarnessAdapter,
    define_goal,
    open_arrangeable_experience_base,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "experience.db"


@pytest.fixture
def experience_base(db_path: Path) -> Iterator[ArrangeableExperienceBase]:
    with open_arrangeable_experience_base(db_path) as opened:
        yield opened


@pytest.fixture
def adapter(experience_base: ArrangeableExperienceBase) -> FakeHarnessAdapter:
    return FakeHarnessAdapter(experience_base)


@pytest.fixture
def goal(experience_base: ArrangeableExperienceBase) -> Goal:
    return define_goal(experience_base)
