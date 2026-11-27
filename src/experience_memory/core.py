"""The core public API. Harness Adapters, the CLI and the tests all go through this object."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Self

from experience_memory.gqm import Goal, GqmPlan, Judge, Metric, MetricKind, Question
from experience_memory.sqlite_store import SqliteStore
from experience_memory.storage import GqmStore


class ExperienceMemory:
    """One open Experience Base: the GQM plan and, later, everything else the core holds."""

    def __init__(self, store: GqmStore) -> None:
        self._store = store
        self._plan = GqmPlan(store)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # GQM plan

    def define_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        """Define a standing Organization Goal from the GQM template."""
        return self._plan.define_organization_goal(
            purpose=purpose, issue=issue, object=object, viewpoint=viewpoint
        )

    def add_question(self, goal_id: str, *, text: str) -> Question:
        """Refine the Goal with id `goal_id` by a Question."""
        return self._plan.add_question(goal_id, text=text)

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
        judge: Judge | None = None,
    ) -> Metric:
        """Answer the Question with id `question_id` by a Metric of the given kind.

        A Judged Metric must carry the rubric it is assessed against and the judge that assesses it.
        """
        return self._plan.add_metric(
            question_id, name=name, definition=definition, kind=kind, rubric=rubric, judge=judge
        )

    def list_organization_goals(self) -> list[Goal]:
        """The Organization Goals with their Questions and Metrics, each in the order added."""
        return self._plan.list_organization_goals()


def open_memory(path: Path | str) -> ExperienceMemory:
    """Open (creating if needed) the Experience Base stored in the SQLite database at `path`."""
    return ExperienceMemory(SqliteStore(Path(path)))
