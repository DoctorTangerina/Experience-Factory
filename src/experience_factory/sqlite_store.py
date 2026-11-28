"""SQLite implementation of the storage interface, in WAL mode (ADR-0004)."""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path

from experience_factory.data_packages import (
    AttributeValue,
    Characterization,
    DataPackageRecord,
    DuplicateTaskError,
    DuplicateValueError,
    UnknownTaskError,
)
from experience_factory.evidence_packs import EvidencePack, decode_pack, encode_pack
from experience_factory.gqm import (
    ApprovalState,
    Goal,
    GoalStatement,
    GqmElement,
    Judge,
    Metric,
    MetricDefinition,
    MetricKind,
    Question,
    UnknownElementError,
)
from experience_factory.harness_adapters import HarnessCapability
from experience_factory.tasks import Task
from experience_factory.traces import TraceSegment, decode_segment, encode_segment

_TABLES = {
    GqmElement.GOAL: "goals",
    GqmElement.QUESTION: "questions",
    GqmElement.METRIC: "metrics",
}


class _GoalLevel(StrEnum):
    """Whether a stored Goal is an Organization Goal or a Project Goal."""

    ORGANIZATION = "organization"
    PROJECT = "project"


_APPROVED = ApprovalState.APPROVED.value

_GOAL_COLUMNS = "id, version, purpose, issue, object, viewpoint"
_METRIC_COLUMNS = (
    "id, version, question_id, name, definition, kind, rubric,"
    " judge_provider, judge_model, judge_effort"
)

_TASK_COLUMNS = "id, project, work_item, state"

# Every version of a GQM plan element is one row, sharing the element's approval state and its place
# in the order elements were added (seq). Questions belong to a Goal and Metrics to a Question
# across all of its versions; goal_version and question_version only record which version of the
# parent was current when the row was stored.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id        TEXT    NOT NULL,
    version   INTEGER NOT NULL,
    level     TEXT    NOT NULL CHECK (level IN ('organization', 'project')),
    project   TEXT    CHECK ((level = 'project') = (project IS NOT NULL)),
    state     TEXT    NOT NULL CHECK (state IN ('proposed', 'approved', 'rejected', 'retired')),
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
    state        TEXT    NOT NULL CHECK (state IN ('proposed', 'approved', 'rejected')),
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
    state            TEXT    NOT NULL CHECK (state IN ('proposed', 'approved', 'rejected')),
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

-- Task boundaries as Harness Adapters report them. Kept apart from the tasks table above, which
-- holds the measurement context recorded under a caller-chosen Task id.
CREATE TABLE IF NOT EXISTS task_boundaries (
    id        TEXT    NOT NULL PRIMARY KEY,
    project   TEXT    NOT NULL,
    work_item TEXT,
    state     TEXT    NOT NULL CHECK (state IN ('open', 'ended')),
    seq       INTEGER NOT NULL
);

-- A work item is bound to at most one open Task per Project, even with concurrent sessions.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_task_per_work_item
    ON task_boundaries (project, work_item) WHERE state = 'open' AND work_item IS NOT NULL;

CREATE TABLE IF NOT EXISTS task_predecessors (
    task_id        TEXT    NOT NULL REFERENCES task_boundaries (id),
    predecessor_id TEXT    NOT NULL REFERENCES task_boundaries (id),
    position       INTEGER NOT NULL,
    PRIMARY KEY (task_id, predecessor_id)
);

-- Each Harness Adapter's latest capability declaration: one row per optional capability it
-- supports. An adapter with no rows supports none.
CREATE TABLE IF NOT EXISTS harness_capabilities (
    adapter    TEXT NOT NULL,
    capability TEXT NOT NULL,
    PRIMARY KEY (adapter, capability)
);

-- Each Trace segment is a gzip-compressed file in the trace directory next to the database
-- (ADR-0004); file names the file relative to that directory.
CREATE TABLE IF NOT EXISTS trace_segments (
    id       TEXT    NOT NULL PRIMARY KEY,
    task_id  TEXT    NOT NULL REFERENCES task_boundaries (id),
    file     TEXT    NOT NULL UNIQUE,
    seq      INTEGER NOT NULL
);

-- Each Task's Evidence Pack, as submitted by its Harness Adapter: at most one per Task.
CREATE TABLE IF NOT EXISTS evidence_packs (
    task_id   TEXT NOT NULL PRIMARY KEY REFERENCES task_boundaries (id),
    pack_json TEXT NOT NULL
);
"""


class SqliteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._trace_dir = path.parent / f"{path.stem}-traces"
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

    def _latest_version(self, element: GqmElement, element_id: str) -> int:
        row = self._conn.execute(
            f"SELECT MAX(version) FROM {_TABLES[element]} WHERE id = ?", (element_id,)
        ).fetchone()
        if row[0] is None:
            raise UnknownElementError(f"no {element} with id {element_id!r}")
        return int(row[0])

    def add_organization_goal(self, statement: GoalStatement) -> Goal:
        return self._add_goal(_GoalLevel.ORGANIZATION, None, statement, ApprovalState.APPROVED)

    def add_project_goal(self, project: str, statement: GoalStatement) -> Goal:
        return self._add_goal(_GoalLevel.PROJECT, project, statement, ApprovalState.PROPOSED)

    def _add_goal(
        self,
        level: _GoalLevel,
        project: str | None,
        statement: GoalStatement,
        state: ApprovalState,
    ) -> Goal:
        goal = Goal(id=uuid.uuid4().hex, version=1, statement=statement)
        with self._conn:
            self._conn.execute(
                "INSERT INTO goals"
                " (id, version, level, project, state, purpose, issue, object, viewpoint, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    goal.id,
                    goal.version,
                    level.value,
                    project,
                    state.value,
                    statement.purpose,
                    statement.issue,
                    statement.object,
                    statement.viewpoint,
                    self._next_seq("goals"),
                ),
            )
        return goal

    def add_goal_version(self, goal_id: str, statement: GoalStatement) -> Goal:
        with self._conn:
            goal = Goal(
                id=goal_id,
                version=self._latest_version(GqmElement.GOAL, goal_id) + 1,
                statement=statement,
            )
            self._conn.execute(
                "INSERT INTO goals"
                " (id, version, level, project, state, purpose, issue, object, viewpoint, seq)"
                " SELECT id, ?, level, project, state, ?, ?, ?, ?, seq FROM goals"
                " WHERE id = ? AND version = ?",
                (
                    goal.version,
                    statement.purpose,
                    statement.issue,
                    statement.object,
                    statement.viewpoint,
                    goal_id,
                    goal.version - 1,
                ),
            )
        return goal

    def add_question(self, goal_id: str, *, text: str, state: ApprovalState) -> Question:
        with self._conn:
            goal_version = self._latest_version(GqmElement.GOAL, goal_id)
            question = Question(id=uuid.uuid4().hex, version=1, goal_id=goal_id, text=text)
            self._conn.execute(
                "INSERT INTO questions (id, version, goal_id, goal_version, text, state, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    question.id,
                    question.version,
                    goal_id,
                    goal_version,
                    question.text,
                    state.value,
                    self._next_seq("questions"),
                ),
            )
        return question

    def add_question_version(self, question_id: str, text: str) -> Question:
        with self._conn:
            version = self._latest_version(GqmElement.QUESTION, question_id) + 1
            row = self._conn.execute(
                "SELECT goal_id FROM questions WHERE id = ? AND version = ?",
                (question_id, version - 1),
            ).fetchone()
            question = Question(id=question_id, version=version, goal_id=row["goal_id"], text=text)
            self._conn.execute(
                "INSERT INTO questions (id, version, goal_id, goal_version, text, state, seq)"
                " SELECT id, ?, goal_id, ?, ?, state, seq FROM questions"
                " WHERE id = ? AND version = ?",
                (
                    version,
                    self._latest_version(GqmElement.GOAL, question.goal_id),
                    text,
                    question_id,
                    version - 1,
                ),
            )
        return question

    def add_metric(
        self, question_id: str, *, name: str, definition: MetricDefinition, state: ApprovalState
    ) -> Metric:
        metric = Metric(
            id=uuid.uuid4().hex,
            version=1,
            question_id=question_id,
            name=name,
            definition=definition,
        )
        with self._conn:
            self._insert_metric(metric, state, self._next_seq("metrics"))
        return metric

    def get_metric(self, metric_id: str, version: int | None = None) -> Metric:
        if version is None:
            version = self._latest_version(GqmElement.METRIC, metric_id)
        return self._metric(metric_id, version)

    def add_metric_version(self, metric_id: str, definition: MetricDefinition) -> Metric:
        with self._conn:
            current = self.get_metric(metric_id)
            metric = Metric(
                id=metric_id,
                version=current.version + 1,
                question_id=current.question_id,
                name=current.name,
                definition=definition,
            )
            # The new version keeps the Metric's approval state (the same on every version) and
            # takes the first version's place in the order Metrics were added.
            first_seq = self._conn.execute(
                "SELECT MIN(seq) FROM metrics WHERE id = ?", (metric_id,)
            ).fetchone()[0]
            self._insert_metric(
                metric, self.approval_state(GqmElement.METRIC, metric_id), int(first_seq)
            )
        return metric

    def _insert_metric(self, metric: Metric, state: ApprovalState, seq: int) -> None:
        """Store one Metric version under its Question's latest version. Call inside a
        transaction."""
        question_version = self._latest_version(GqmElement.QUESTION, metric.question_id)
        definition = metric.definition
        self._conn.execute(
            f"INSERT INTO metrics ({_METRIC_COLUMNS}, question_version, state, seq)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.id,
                metric.version,
                metric.question_id,
                metric.name,
                definition.text,
                definition.kind.value,
                definition.rubric,
                *definition.judge_parts(),
                question_version,
                state.value,
                seq,
            ),
        )

    def approval_state(self, element: GqmElement, element_id: str) -> ApprovalState:
        row = self._conn.execute(
            f"SELECT state FROM {_TABLES[element]} WHERE id = ? ORDER BY version DESC LIMIT 1",
            (element_id,),
        ).fetchone()
        if row is None:
            raise UnknownElementError(f"no {element} with id {element_id!r}")
        return ApprovalState(row["state"])

    def replace_approval_state(
        self, element: GqmElement, element_id: str, expected: ApprovalState, new: ApprovalState
    ) -> bool:
        # Every version of an element shares its approval state.
        with self._conn:
            changed = self._conn.execute(
                f"UPDATE {_TABLES[element]} SET state = ? WHERE id = ? AND state = ?",
                (new.value, element_id, expected.value),
            ).rowcount
        return changed > 0

    def list_organization_goals(self) -> list[Goal]:
        return self._goals_in_force("level = ?", _GoalLevel.ORGANIZATION.value)

    def list_project_goals_in_force(self, project: str) -> list[Goal]:
        return self._goals_in_force("level = ? AND project = ?", _GoalLevel.PROJECT.value, project)

    def list_metrics_in_force(self, question_id: str) -> list[Metric]:
        question_version = self._latest_version(GqmElement.QUESTION, question_id)
        if not self._exists(
            "SELECT 1 FROM questions q JOIN goals g ON g.id = q.goal_id"
            " WHERE q.id = ? AND q.version = ? AND q.state = ? AND g.state = ? LIMIT 1",
            question_id,
            question_version,
            _APPROVED,
            _APPROVED,
        ):
            return []
        return list(self._metrics_of(question_id))

    def _goals_in_force(self, where: str, *params: object) -> list[Goal]:
        goal_rows = self._conn.execute(
            f"SELECT {_GOAL_COLUMNS} FROM goals g"
            f" WHERE {where} AND state = ?"
            " AND version = (SELECT MAX(version) FROM goals WHERE id = g.id)"
            " ORDER BY seq",
            (*params, _APPROVED),
        ).fetchall()
        return [_goal_from(row, questions=self._questions_of(row["id"])) for row in goal_rows]

    def _questions_of(self, goal_id: str) -> tuple[Question, ...]:
        rows = self._conn.execute(
            "SELECT id, version, text FROM questions q"
            " WHERE goal_id = ? AND state = ?"
            " AND version = (SELECT MAX(version) FROM questions WHERE id = q.id)"
            " ORDER BY seq",
            (goal_id, _APPROVED),
        ).fetchall()
        return tuple(
            Question(
                id=row["id"],
                version=row["version"],
                goal_id=goal_id,
                text=row["text"],
                metrics=self._metrics_of(row["id"]),
            )
            for row in rows
        )

    def _metrics_of(self, question_id: str) -> tuple[Metric, ...]:
        rows = self._conn.execute(
            f"SELECT {_METRIC_COLUMNS} FROM metrics m"
            " WHERE question_id = ? AND state = ?"
            " AND version = (SELECT MAX(version) FROM metrics WHERE id = m.id)"
            " ORDER BY seq",
            (question_id, _APPROVED),
        ).fetchall()
        return tuple(_metric_from(row) for row in rows)

    # Data Packages

    def get_goal(self, goal_id: str) -> Goal:
        version = self._latest_version(GqmElement.GOAL, goal_id)
        return self._goal(goal_id, version)

    def _goal(self, goal_id: str, version: int) -> Goal:
        row = self._conn.execute(
            f"SELECT {_GOAL_COLUMNS} FROM goals WHERE id = ? AND version = ?",
            (goal_id, version),
        ).fetchone()
        return _goal_from(row)

    def _metric(self, metric_id: str, version: int) -> Metric:
        row = self._conn.execute(
            f"SELECT {_METRIC_COLUMNS} FROM metrics WHERE id = ? AND version = ?",
            (metric_id, version),
        ).fetchone()
        if row is None:
            raise UnknownElementError(f"no Metric with id {metric_id!r} at version {version}")
        return _metric_from(row)

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

    # Task boundaries

    def join_or_open_task(
        self, project: str, *, work_item: str | None, predecessor_ids: Sequence[str]
    ) -> tuple[Task, bool]:
        if work_item is not None and (task := self._open_task_bound_to(project, work_item)):
            return task, False
        task = Task(
            id=uuid.uuid4().hex,
            project=project,
            work_item=work_item,
            is_open=True,
            predecessor_ids=tuple(predecessor_ids),
        )
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO task_boundaries (id, project, work_item, state, seq)"
                    " VALUES (?, ?, ?, 'open', ?)",
                    (task.id, project, work_item, self._next_seq("task_boundaries")),
                )
                self._conn.executemany(
                    "INSERT INTO task_predecessors (task_id, predecessor_id, position)"
                    " VALUES (?, ?, ?)",
                    [(task.id, pid, i) for i, pid in enumerate(task.predecessor_ids)],
                )
        except sqlite3.IntegrityError:
            # A concurrent session opened the work item's Task first: join it.
            if work_item is None or not (task := self._open_task_bound_to(project, work_item)):
                raise
            return task, False
        return task, True

    def end_task(self, task_id: str) -> bool:
        with self._conn:
            changed = self._conn.execute(
                "UPDATE task_boundaries SET state = 'ended' WHERE id = ? AND state = 'open'",
                (task_id,),
            ).rowcount
        return changed > 0

    def find_task(self, task_id: str) -> Task | None:
        row = self._conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM task_boundaries WHERE id = ?", (task_id,)
        ).fetchone()
        return None if row is None else self._task_from(row)

    def _open_task_bound_to(self, project: str, work_item: str) -> Task | None:
        row = self._conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM task_boundaries"
            " WHERE project = ? AND work_item = ? AND state = 'open'",
            (project, work_item),
        ).fetchone()
        return None if row is None else self._task_from(row)

    def _task_from(self, row: sqlite3.Row) -> Task:
        predecessors = self._conn.execute(
            "SELECT predecessor_id FROM task_predecessors WHERE task_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return Task(
            id=row["id"],
            project=row["project"],
            work_item=row["work_item"],
            is_open=row["state"] == "open",
            predecessor_ids=tuple(p["predecessor_id"] for p in predecessors),
        )

    def replace_harness_capabilities(
        self, adapter: str, capabilities: frozenset[HarnessCapability]
    ) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM harness_capabilities WHERE adapter = ?", (adapter,))
            self._conn.executemany(
                "INSERT INTO harness_capabilities (adapter, capability) VALUES (?, ?)",
                [(adapter, capability.value) for capability in sorted(capabilities)],
            )

    def harness_capabilities(self, adapter: str) -> frozenset[HarnessCapability]:
        rows = self._conn.execute(
            "SELECT capability FROM harness_capabilities WHERE adapter = ?", (adapter,)
        ).fetchall()
        return frozenset(HarnessCapability(row["capability"]) for row in rows)

    # Traces

    def add_trace_segment(self, task_id: str, segment: TraceSegment) -> bool:
        segment_id = uuid.uuid4().hex
        file = f"{task_id}/{segment_id}.json.gz"
        path = self._trace_dir / file
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so the database never references a partial file.
        partial = path.with_name(path.name + ".partial")
        partial.write_bytes(gzip.compress(encode_segment(segment)))
        os.replace(partial, path)
        try:
            with self._conn:
                stored = self._conn.execute(
                    "INSERT INTO trace_segments (id, task_id, file, seq)"
                    " SELECT ?, id, ?, ? FROM task_boundaries WHERE id = ? AND state = 'open'",
                    (segment_id, file, self._next_seq("trace_segments"), task_id),
                ).rowcount
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        if not stored:
            path.unlink()
        return stored > 0

    def trace_segments(self, task_id: str) -> list[TraceSegment]:
        rows = self._conn.execute(
            "SELECT file FROM trace_segments WHERE task_id = ? ORDER BY seq", (task_id,)
        ).fetchall()
        return [
            decode_segment(gzip.decompress((self._trace_dir / row["file"]).read_bytes()))
            for row in rows
        ]

    # Evidence Packs

    def put_evidence_pack(self, task_id: str, pack: EvidencePack) -> bool:
        with self._conn:
            stored = self._conn.execute(
                "INSERT INTO evidence_packs (task_id, pack_json)"
                " SELECT id, ? FROM task_boundaries WHERE id = ? AND state = 'open'"
                " ON CONFLICT (task_id) DO UPDATE SET pack_json = excluded.pack_json",
                (encode_pack(pack), task_id),
            ).rowcount
        return stored > 0

    def evidence_pack(self, task_id: str) -> EvidencePack | None:
        row = self._conn.execute(
            "SELECT pack_json FROM evidence_packs WHERE task_id = ?", (task_id,)
        ).fetchone()
        return None if row is None else decode_pack(row["pack_json"])

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


def _goal_from(row: sqlite3.Row, questions: tuple[Question, ...] = ()) -> Goal:
    return Goal(
        id=row["id"],
        version=row["version"],
        statement=GoalStatement(
            purpose=row["purpose"],
            issue=row["issue"],
            object=row["object"],
            viewpoint=row["viewpoint"],
        ),
        questions=questions,
    )


def _metric_from(row: sqlite3.Row) -> Metric:
    judge = (
        None
        if row["judge_provider"] is None
        else Judge(
            provider=row["judge_provider"], model=row["judge_model"], effort=row["judge_effort"]
        )
    )
    return Metric(
        id=row["id"],
        version=row["version"],
        question_id=row["question_id"],
        name=row["name"],
        definition=MetricDefinition(
            text=row["definition"], kind=MetricKind(row["kind"]), rubric=row["rubric"], judge=judge
        ),
    )
