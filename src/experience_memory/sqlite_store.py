"""SQLite implementation of the storage interface, in WAL mode (ADR-0004)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from experience_memory.data_packages import (
    AttributeValue,
    Characterization,
    DataPackageRecord,
    DuplicateTaskError,
    DuplicateValueError,
    UnknownTaskError,
)
from experience_memory.gqm import Goal, Judge, Metric, MetricKind, Question, UnknownElementError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id        TEXT    NOT NULL,
    version   INTEGER NOT NULL,
    level     TEXT    NOT NULL CHECK (level IN ('organization', 'project')),
    purpose   TEXT    NOT NULL,
    issue     TEXT    NOT NULL,
    object    TEXT    NOT NULL,
    viewpoint TEXT    NOT NULL,
    seq       INTEGER NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS questions (
    id           TEXT    NOT NULL,
    version      INTEGER NOT NULL,
    goal_id      TEXT    NOT NULL,
    goal_version INTEGER NOT NULL,
    text         TEXT    NOT NULL,
    seq          INTEGER NOT NULL,
    PRIMARY KEY (id, version),
    FOREIGN KEY (goal_id, goal_version) REFERENCES goals (id, version)
);

CREATE TABLE IF NOT EXISTS metrics (
    id               TEXT    NOT NULL,
    version          INTEGER NOT NULL,
    question_id      TEXT    NOT NULL,
    question_version INTEGER NOT NULL,
    name             TEXT    NOT NULL,
    definition       TEXT    NOT NULL,
    kind             TEXT    NOT NULL CHECK (kind IN ('objective', 'judged')),
    rubric           TEXT,
    judge_provider   TEXT,
    judge_model      TEXT,
    judge_effort     TEXT,
    seq              INTEGER NOT NULL,
    PRIMARY KEY (id, version),
    FOREIGN KEY (question_id, question_version) REFERENCES questions (id, version)
);

CREATE TABLE IF NOT EXISTS tasks (
    id                    TEXT    NOT NULL PRIMARY KEY,
    schema_version        TEXT    NOT NULL,
    characterization_json TEXT    NOT NULL,
    holdout               INTEGER NOT NULL CHECK (holdout IN (0, 1))
);

CREATE TABLE IF NOT EXISTS task_goals (
    task_id      TEXT    NOT NULL REFERENCES tasks (id),
    goal_id      TEXT    NOT NULL,
    goal_version INTEGER NOT NULL,
    position     INTEGER NOT NULL,
    PRIMARY KEY (task_id, goal_id),
    FOREIGN KEY (goal_id, goal_version) REFERENCES goals (id, version)
);

CREATE TABLE IF NOT EXISTS metric_values (
    task_id        TEXT    NOT NULL REFERENCES tasks (id),
    metric_id      TEXT    NOT NULL,
    metric_version INTEGER NOT NULL,
    value          REAL    NOT NULL,
    judged_by_model TEXT,
    seq            INTEGER NOT NULL,
    PRIMARY KEY (task_id, metric_id, metric_version),
    FOREIGN KEY (metric_id, metric_version) REFERENCES metrics (id, version)
);
"""


class SqliteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Pragmas must run outside a transaction, so set them before turning transactions on.
        self._conn = sqlite3.connect(path, autocommit=True)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.autocommit = False
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def _next_seq(self, table: str) -> int:
        row = self._conn.execute(f"SELECT COALESCE(MAX(seq), 0) + 1 FROM {table}").fetchone()
        return int(row[0])

    def _exists(self, query: str, *params: object) -> bool:
        return self._conn.execute(query, params).fetchone() is not None

    def _latest_version(self, table: str, element_id: str, kind: str) -> int:
        row = self._conn.execute(
            f"SELECT MAX(version) FROM {table} WHERE id = ?", (element_id,)
        ).fetchone()
        if row[0] is None:
            raise UnknownElementError(f"no {kind} with id {element_id!r}")
        return int(row[0])

    def add_organization_goal(
        self, *, purpose: str, issue: str, object: str, viewpoint: str
    ) -> Goal:
        goal = Goal(
            id=uuid.uuid4().hex,
            version=1,
            purpose=purpose,
            issue=issue,
            object=object,
            viewpoint=viewpoint,
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO goals (id, version, level, purpose, issue, object, viewpoint, seq)"
                " VALUES (?, ?, 'organization', ?, ?, ?, ?, ?)",
                (
                    goal.id,
                    goal.version,
                    goal.purpose,
                    goal.issue,
                    goal.object,
                    goal.viewpoint,
                    self._next_seq("goals"),
                ),
            )
        return goal

    def add_question(self, goal_id: str, *, text: str) -> Question:
        with self._conn:
            goal_version = self._latest_version("goals", goal_id, "Goal")
            question = Question(id=uuid.uuid4().hex, version=1, goal_id=goal_id, text=text)
            self._conn.execute(
                "INSERT INTO questions (id, version, goal_id, goal_version, text, seq)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    question.id,
                    question.version,
                    goal_id,
                    goal_version,
                    question.text,
                    self._next_seq("questions"),
                ),
            )
        return question

    def add_metric(
        self,
        question_id: str,
        *,
        name: str,
        definition: str,
        kind: MetricKind,
        rubric: str | None,
        judge: Judge | None,
    ) -> Metric:
        with self._conn:
            question_version = self._latest_version("questions", question_id, "Question")
            metric = Metric(
                id=uuid.uuid4().hex,
                version=1,
                question_id=question_id,
                name=name,
                definition=definition,
                kind=kind,
                rubric=rubric,
                judge=judge,
            )
            self._conn.execute(
                "INSERT INTO metrics (id, version, question_id, question_version, name,"
                " definition, kind, rubric, judge_provider, judge_model, judge_effort, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    metric.id,
                    metric.version,
                    question_id,
                    question_version,
                    metric.name,
                    metric.definition,
                    metric.kind.value,
                    metric.rubric,
                    judge.provider if judge else None,
                    judge.model if judge else None,
                    judge.effort if judge else None,
                    self._next_seq("metrics"),
                ),
            )
        return metric

    def get_metric(self, metric_id: str, version: int | None = None) -> Metric:
        if version is None:
            version = self._latest_version("metrics", metric_id, "Metric")
        return self._metric(metric_id, version)

    def add_metric_version(
        self,
        metric_id: str,
        *,
        definition: str,
        kind: MetricKind,
        rubric: str | None,
        judge: Judge | None,
    ) -> Metric:
        with self._conn:
            current = self.get_metric(metric_id)
            question_version = self._latest_version("questions", current.question_id, "Question")
            metric = Metric(
                id=metric_id,
                version=current.version + 1,
                question_id=current.question_id,
                name=current.name,
                definition=definition,
                kind=kind,
                rubric=rubric,
                judge=judge,
            )
            # The new version takes the first version's place in the order Metrics were added.
            self._conn.execute(
                "INSERT INTO metrics (id, version, question_id, question_version, name,"
                " definition, kind, rubric, judge_provider, judge_model, judge_effort, seq)"
                " SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, MIN(seq) FROM metrics WHERE id = ?",
                (
                    metric.id,
                    metric.version,
                    metric.question_id,
                    question_version,
                    metric.name,
                    metric.definition,
                    metric.kind.value,
                    metric.rubric,
                    judge.provider if judge else None,
                    judge.model if judge else None,
                    judge.effort if judge else None,
                    metric_id,
                ),
            )
        return metric

    def list_organization_goals(self) -> list[Goal]:
        goal_rows = self._conn.execute(
            "SELECT id, version, purpose, issue, object, viewpoint FROM goals"
            " WHERE level = 'organization' ORDER BY seq"
        ).fetchall()
        return [
            Goal(
                id=row["id"],
                version=row["version"],
                purpose=row["purpose"],
                issue=row["issue"],
                object=row["object"],
                viewpoint=row["viewpoint"],
                questions=self._questions_of(row["id"], row["version"]),
            )
            for row in goal_rows
        ]

    def _questions_of(self, goal_id: str, goal_version: int) -> tuple[Question, ...]:
        rows = self._conn.execute(
            "SELECT id, version, text FROM questions"
            " WHERE goal_id = ? AND goal_version = ? ORDER BY seq",
            (goal_id, goal_version),
        ).fetchall()
        return tuple(
            Question(
                id=row["id"],
                version=row["version"],
                goal_id=goal_id,
                text=row["text"],
                metrics=self._metrics_of(row["id"], row["version"]),
            )
            for row in rows
        )

    def _metrics_of(self, question_id: str, question_version: int) -> tuple[Metric, ...]:
        rows = self._conn.execute(
            "SELECT id, version, name, definition, kind, rubric,"
            " judge_provider, judge_model, judge_effort FROM metrics m"
            " WHERE question_id = ? AND question_version = ?"
            " AND version = (SELECT MAX(version) FROM metrics WHERE id = m.id)"
            " ORDER BY seq",
            (question_id, question_version),
        ).fetchall()
        return tuple(
            Metric(
                id=row["id"],
                version=row["version"],
                question_id=question_id,
                name=row["name"],
                definition=row["definition"],
                kind=MetricKind(row["kind"]),
                rubric=row["rubric"],
                judge=_judge_from(row),
            )
            for row in rows
        )

    # Data Packages

    def get_goal(self, goal_id: str) -> Goal:
        version = self._latest_version("goals", goal_id, "Goal")
        return self._goal(goal_id, version)

    def _goal(self, goal_id: str, version: int) -> Goal:
        row = self._conn.execute(
            "SELECT purpose, issue, object, viewpoint FROM goals WHERE id = ? AND version = ?",
            (goal_id, version),
        ).fetchone()
        return Goal(
            id=goal_id,
            version=version,
            purpose=row["purpose"],
            issue=row["issue"],
            object=row["object"],
            viewpoint=row["viewpoint"],
        )

    def _metric(self, metric_id: str, version: int) -> Metric:
        row = self._conn.execute(
            "SELECT question_id, name, definition, kind, rubric,"
            " judge_provider, judge_model, judge_effort FROM metrics"
            " WHERE id = ? AND version = ?",
            (metric_id, version),
        ).fetchone()
        if row is None:
            raise UnknownElementError(f"no Metric with id {metric_id!r} at version {version}")
        return Metric(
            id=metric_id,
            version=version,
            question_id=row["question_id"],
            name=row["name"],
            definition=row["definition"],
            kind=MetricKind(row["kind"]),
            rubric=row["rubric"],
            judge=_judge_from(row),
        )

    def add_task(
        self,
        task_id: str,
        *,
        characterization: Characterization,
        goals: Sequence[Goal],
        holdout: bool,
    ) -> None:
        with self._conn:
            if self._exists("SELECT 1 FROM tasks WHERE id = ?", task_id):
                raise DuplicateTaskError(f"Task {task_id!r} is already recorded")
            self._conn.execute(
                "INSERT INTO tasks (id, schema_version, characterization_json, holdout)"
                " VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    characterization.schema_version,
                    _attributes_to_json(characterization.attributes),
                    int(holdout),
                ),
            )
            self._conn.executemany(
                "INSERT INTO task_goals (task_id, goal_id, goal_version, position)"
                " VALUES (?, ?, ?, ?)",
                [(task_id, goal.id, goal.version, i) for i, goal in enumerate(goals)],
            )

    def add_metric_value(
        self,
        task_id: str,
        *,
        metric_id: str,
        metric_version: int,
        value: float,
        judged_by_model: str | None,
    ) -> None:
        with self._conn:
            if not self._exists("SELECT 1 FROM tasks WHERE id = ?", task_id):
                raise UnknownTaskError(f"no recorded Task with id {task_id!r}")
            if self._exists(
                "SELECT 1 FROM metric_values"
                " WHERE task_id = ? AND metric_id = ? AND metric_version = ?",
                task_id,
                metric_id,
                metric_version,
            ):
                raise DuplicateValueError(
                    f"Task {task_id!r} already has a value for Metric {metric_id!r}"
                    f" version {metric_version}"
                )
            self._conn.execute(
                "INSERT INTO metric_values"
                " (task_id, metric_id, metric_version, value, judged_by_model, seq)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    metric_id,
                    metric_version,
                    value,
                    judged_by_model,
                    self._next_seq("metric_values"),
                ),
            )

    def list_data_package_records(self) -> list[DataPackageRecord]:
        rows = self._conn.execute(
            "SELECT v.task_id, v.metric_id, v.metric_version, v.value, v.judged_by_model,"
            " t.schema_version, t.characterization_json, t.holdout"
            " FROM metric_values v JOIN tasks t ON t.id = v.task_id ORDER BY v.seq"
        ).fetchall()
        return [
            DataPackageRecord(
                task_id=row["task_id"],
                metric=self._metric(row["metric_id"], row["metric_version"]),
                value=row["value"],
                judged_by_model=row["judged_by_model"],
                characterization=Characterization(
                    schema_version=row["schema_version"],
                    attributes=_attributes_from_json(row["characterization_json"]),
                ),
                goals=self._goals_of_task(row["task_id"]),
                holdout=bool(row["holdout"]),
            )
            for row in rows
        ]

    def _goals_of_task(self, task_id: str) -> tuple[Goal, ...]:
        rows = self._conn.execute(
            "SELECT goal_id, goal_version FROM task_goals WHERE task_id = ? ORDER BY position",
            (task_id,),
        ).fetchall()
        return tuple(self._goal(row["goal_id"], row["goal_version"]) for row in rows)


def _attributes_to_json(attributes: Mapping[str, AttributeValue]) -> str:
    # A set is stored as a sorted list, a single value as a string, so the shape survives.
    return json.dumps(
        {
            name: value if isinstance(value, str) else sorted(value)
            for name, value in attributes.items()
        }
    )


def _attributes_from_json(text: str) -> dict[str, AttributeValue]:
    raw: dict[str, str | list[str]] = json.loads(text)
    return {
        name: value if isinstance(value, str) else frozenset(value) for name, value in raw.items()
    }


def _judge_from(row: sqlite3.Row) -> Judge | None:
    if row["judge_provider"] is None:
        return None
    return Judge(
        provider=row["judge_provider"], model=row["judge_model"], effort=row["judge_effort"]
    )
