"""The GQM plan registry: Goals refined into Questions and Metrics (see CONTEXT.md, Measurement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from experience_memory.storage import GqmStore


class GqmPlanError(Exception):
    """The GQM plan refused an operation."""


class UnknownElementError(GqmPlanError, LookupError):
    """The operation names a Goal, Question or Metric that is not in the GQM plan."""


class MissingRubricError(GqmPlanError, ValueError):
    """A Judged Metric was added without the rubric it must be assessed against."""


class MetricKind(StrEnum):
    """Whether a Metric is computed deterministically or assessed by an LLM against a rubric."""

    OBJECTIVE = "objective"
    JUDGED = "judged"


@dataclass(frozen=True)
class Metric:
    """A defined, versioned GQM measurement answering a Question."""

    id: str
    version: int
    question_id: str
    name: str
    definition: str
    kind: MetricKind
    rubric: str | None


@dataclass(frozen=True)
class Question:
    """A GQM Question refining a Goal into something answerable from Traces and Evidence Packs."""

    id: str
    version: int
    goal_id: str
    text: str
    metrics: tuple[Metric, ...] = field(default=())


@dataclass(frozen=True)
class Goal:
    """A GQM measurement Goal: the purpose, issue, object and viewpoint experience serves."""

    id: str
    version: int
    purpose: str
    issue: str
    object: str
    viewpoint: str
    questions: tuple[Question, ...] = field(default=())


class GqmPlan:
    """Defines and lists GQM plan elements, enforcing its rules before anything is stored."""

    def __init__(self, store: GqmStore) -> None:
        self._store = store

    def define_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        return self._store.add_organization_goal(
            purpose=purpose, issue=issue, object=object, viewpoint=viewpoint
        )

    def add_question(self, goal_id: str, *, text: str) -> Question:
        return self._store.add_question(goal_id, text=text)

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None = None,
    ) -> Metric:
        if kind is MetricKind.JUDGED and rubric is None:
            raise MissingRubricError(f"Judged Metric {name!r} has no rubric")
        return self._store.add_metric(
            question_id, name=name, definition=definition, kind=kind, rubric=rubric
        )

    def list_organization_goals(self) -> list[Goal]:
        return self._store.list_organization_goals()
