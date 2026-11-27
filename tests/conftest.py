"""Test harness: every core test drives the core public API, opened on a fresh database."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from experience_memory import ExperienceMemory, open_memory


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "experience.db"


@pytest.fixture
def memory(db_path: Path) -> Iterator[ExperienceMemory]:
    with open_memory(db_path) as opened:
        yield opened
