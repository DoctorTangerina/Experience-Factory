"""The storage interface behind the core (ADR-0004: SQLite today, a server database possibly later).

Implementations only persist and retrieve; the rules of the GQM plan are enforced above this line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from experience_memory.gqm import Goal, Metric, MetricKind, Question


class GqmStore(Protocol):
    def add_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal: ...

    def add_question(self, goal_id: str, *, text: str) -> Question: ...

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None,
    ) -> Metric: ...

    def list_organization_goals(self) -> list[Goal]:
        """Organization Goals with their Questions and Metrics, each in the order added."""
        ...

    def close(self) -> None: ...
