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
    """A Judged Metric was added without the rubric it must be assessed against.

    A blank rubric (empty or whitespace only) counts as no rubric.
    """


class MissingJudgeError(GqmPlanError, ValueError):
    """A Judged Metric was added without the judge (provider, model, effort) that assesses it."""


class IncompleteJudgeError(GqmPlanError, ValueError):
    """A judge was given a blank provider, model or effort."""


class MetricKind(StrEnum):
    """Whether a Metric is computed deterministically or assessed by an LLM against a rubric."""

    OBJECTIVE = "objective"
    JUDGED = "judged"


@dataclass(frozen=True)
class Judge:
    """The LLM that assesses a Judged Metric. Part of the Metric's definition (ADR-0005)."""

    provider: str
    model: str
    effort: str

    def __post_init__(self) -> None:
        # Each part identifies the measurement instrument, so none may be blank.
        for part in ("provider", "model", "effort"):
            if not getattr(self, part).strip():
                raise IncompleteJudgeError(f"a judge needs a non-blank {part}")


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
    judge: Judge | None


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
        judge: Judge | None = None,
    ) -> Metric:
        if kind is MetricKind.JUDGED and (rubric is None or not rubric.strip()):
            raise MissingRubricError(f"Judged Metric {name!r} has no rubric")
        if kind is MetricKind.JUDGED and judge is None:
            raise MissingJudgeError(f"Judged Metric {name!r} has no judge")
        return self._store.add_metric(
            question_id, name=name, definition=definition, kind=kind, rubric=rubric, judge=judge
        )

    def list_organization_goals(self) -> list[Goal]:
        return self._store.list_organization_goals()
