"""SQLite implementation of the storage interface, in WAL mode (ADR-0004)."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

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
            " judge_provider, judge_model, judge_effort FROM metrics"
            " WHERE question_id = ? AND question_version = ? ORDER BY seq",
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


def _judge_from(row: sqlite3.Row) -> Judge | None:
    if row["judge_provider"] is None:
        return None
    return Judge(
        provider=row["judge_provider"], model=row["judge_model"], effort=row["judge_effort"]
    )
