"""Test harness: every core test drives the core public API, opened on a fresh database."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from experience_memory import ExperienceBase, open_experience_base


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "experience.db"


@pytest.fixture
def experience_base(db_path: Path) -> Iterator[ExperienceBase]:
    with open_experience_base(db_path) as opened:
        yield opened
