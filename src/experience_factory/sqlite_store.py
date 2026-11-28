"""SQLite implementation of the storage interface, in WAL mode (ADR-0004)."""

from __future__ import annotations

import contextlib
import gzip
import json
import os
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
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
from experience_factory.packages import (
    ApplicabilityScope,
    Package,
    PackageState,
    PackageType,
    Provenance,
    StateChange,
)
from experience_factory.tasks import Task
from experience_factory.trace_retention import TaskEnd
from experience_factory.traces import (
    RetainedSpans,
    TraceEvent,
    TraceSegment,
    decode_event,
    decode_segment,
    encode_event,
    encode_segment,
)

_MICROSECOND = timedelta(microseconds=1)

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

-- A work item is bound to at most one Task per Project, ever, even with concurrent sessions: a
-- later session on it reopens that Task.
CREATE UNIQUE INDEX IF NOT EXISTS one_task_per_work_item
    ON task_boundaries (project, work_item) WHERE work_item IS NOT NULL;

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

-- When each Task last ended: Trace retention ages an ended Task's Trace from this time. A reopened
-- Task keeps its row until it ends again, so only Tasks whose state is 'ended' count.
CREATE TABLE IF NOT EXISTS task_ends (
    task_id  TEXT NOT NULL PRIMARY KEY REFERENCES task_boundaries (id),
    ended_at TEXT NOT NULL
);

-- Each Project's Trace retention window, in microseconds. A Project with no row keeps its Traces.
CREATE TABLE IF NOT EXISTS trace_retention_windows (
    project   TEXT    NOT NULL PRIMARY KEY,
    window_us INTEGER NOT NULL CHECK (window_us >= 0)
);

-- The Traces retention has reduced, and the spans it kept of each, copied into the database out
-- of the segment files it deleted (ADR-0004). through is the highest span number the Trace had
-- when last reduced: segments handed over after its Task is reopened are numbered after it.
CREATE TABLE IF NOT EXISTS reduced_traces (
    task_id TEXT    NOT NULL PRIMARY KEY REFERENCES task_boundaries (id),
    through INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS retained_trace_spans (
    task_id    TEXT    NOT NULL REFERENCES reduced_traces (task_id),
    number     INTEGER NOT NULL,
    event_json TEXT    NOT NULL,
    PRIMARY KEY (task_id, number)
);

-- Each Task's Evidence Pack, as submitted by its Harness Adapter: at most one per Task.
CREATE TABLE IF NOT EXISTS evidence_packs (
    task_id   TEXT NOT NULL PRIMARY KEY REFERENCES task_boundaries (id),
    pack_json TEXT NOT NULL
);

-- The Experience Base's Packages. Rows are never deleted: a Retired or Superseded Package stays
-- with its state history. The current state is the last entry of package_history.
CREATE TABLE IF NOT EXISTS packages (
    id              TEXT    NOT NULL PRIMARY KEY,
    type            TEXT    NOT NULL CHECK (type IN
                        ('product', 'process', 'relationship', 'tool', 'management', 'data')),
    title           TEXT    NOT NULL,
    summary         TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    scope_project   TEXT,
    scope_json      TEXT    NOT NULL,
    evidence_json   TEXT    NOT NULL,
    origin_project  TEXT    NOT NULL,
    origin_tasks_json TEXT  NOT NULL,
    superseded_by   TEXT    REFERENCES packages (id),
    seq             INTEGER NOT NULL
);

-- Goals belong to a Package across all of the Goal's versions, so only the Goal id is kept.
CREATE TABLE IF NOT EXISTS package_goals (
    package_id TEXT    NOT NULL REFERENCES packages (id),
    goal_id    TEXT    NOT NULL,
    position   INTEGER NOT NULL,
    PRIMARY KEY (package_id, goal_id)
);

CREATE TABLE IF NOT EXISTS package_history (
    package_id TEXT    NOT NULL REFERENCES packages (id),
    position   INTEGER NOT NULL,
    state      TEXT    NOT NULL CHECK (state IN
                   ('lesson_learned', 'candidate', 'validated', 'retired', 'superseded')),
    reason     TEXT    NOT NULL,
    PRIMARY KEY (package_id, position)
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

    def open_task(
        self, project: str, *, work_item: str | None, predecessor_ids: Sequence[str]
    ) -> tuple[Task, bool]:
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
            # A concurrent session gave the work item its Task first: join it.
            if work_item is None or not (task := self.find_task_bound_to(project, work_item)):
                raise
            reopened = self.reopen_task(task.id)
            assert reopened is not None
            return reopened, False
        return task, True

    def reopen_task(self, task_id: str, *, bind_work_item: str | None = None) -> Task | None:
        try:
            with self._conn:
                self._conn.execute(
                    "UPDATE task_boundaries SET state = 'open',"
                    " work_item = coalesce(?, work_item) WHERE id = ?",
                    (bind_work_item, task_id),
                )
        except sqlite3.IntegrityError:
            # The work item already has a Task.
            return None
        return self.find_task(task_id)

    def end_task(self, task_id: str, *, ended_at: datetime) -> bool:
        with self._conn:
            changed = self._conn.execute(
                "UPDATE task_boundaries SET state = 'ended' WHERE id = ? AND state = 'open'",
                (task_id,),
            ).rowcount
            if changed:
                self._conn.execute(
                    "INSERT INTO task_ends (task_id, ended_at) VALUES (?, ?)"
                    " ON CONFLICT (task_id) DO UPDATE SET ended_at = excluded.ended_at",
                    (task_id, ended_at.isoformat()),
                )
        return changed > 0

    def find_task(self, task_id: str) -> Task | None:
        row = self._conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM task_boundaries WHERE id = ?", (task_id,)
        ).fetchone()
        return None if row is None else self._task_from(row)

    def find_task_bound_to(self, project: str, work_item: str) -> Task | None:
        row = self._conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM task_boundaries WHERE project = ? AND work_item = ?",
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

    def retained_trace_spans(self, task_id: str) -> RetainedSpans | None:
        reduced = self._conn.execute(
            "SELECT through FROM reduced_traces WHERE task_id = ?", (task_id,)
        ).fetchone()
        if reduced is None:
            return None
        rows = self._conn.execute(
            "SELECT number, event_json FROM retained_trace_spans WHERE task_id = ?", (task_id,)
        ).fetchall()
        return RetainedSpans(
            events={row["number"]: decode_event(json.loads(row["event_json"])) for row in rows},
            through=reduced["through"],
        )

    # Trace retention

    def put_trace_retention_window(self, project: str, window: timedelta) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO trace_retention_windows (project, window_us) VALUES (?, ?)"
                " ON CONFLICT (project) DO UPDATE SET window_us = excluded.window_us",
                (project, window // _MICROSECOND),
            )

    def trace_retention_windows(self) -> dict[str, timedelta]:
        rows = self._conn.execute("SELECT project, window_us FROM trace_retention_windows")
        return {row["project"]: row["window_us"] * _MICROSECOND for row in rows}

    def ended_tasks(self) -> list[TaskEnd]:
        rows = self._conn.execute(
            "SELECT t.id, t.project, e.ended_at FROM task_boundaries t"
            " JOIN task_ends e ON e.task_id = t.id WHERE t.state = 'ended' ORDER BY t.seq"
        ).fetchall()
        return [
            TaskEnd(
                task_id=row["id"],
                project=row["project"],
                ended_at=datetime.fromisoformat(row["ended_at"]),
            )
            for row in rows
        ]

    def reduce_trace(self, task_id: str, kept: Mapping[int, TraceEvent], *, through: int) -> None:
        files = [
            row["file"]
            for row in self._conn.execute(
                "SELECT file FROM trace_segments WHERE task_id = ?", (task_id,)
            )
        ]
        with self._conn:
            self._conn.execute(
                "INSERT INTO reduced_traces (task_id, through) VALUES (?, ?)"
                " ON CONFLICT (task_id) DO UPDATE SET through = excluded.through",
                (task_id, through),
            )
            retained = self._conn.execute(
                "SELECT number FROM retained_trace_spans WHERE task_id = ?", (task_id,)
            ).fetchall()
            self._conn.executemany(
                "DELETE FROM retained_trace_spans WHERE task_id = ? AND number = ?",
                [(task_id, row["number"]) for row in retained if row["number"] not in kept],
            )
            self._conn.executemany(
                "INSERT INTO retained_trace_spans (task_id, number, event_json) VALUES (?, ?, ?)"
                " ON CONFLICT DO NOTHING",
                [
                    (task_id, number, json.dumps(encode_event(event), ensure_ascii=False))
                    for number, event in kept.items()
                ],
            )
            self._conn.execute("DELETE FROM trace_segments WHERE task_id = ?", (task_id,))
        # Delete the files only once the database no longer references them.
        for file in files:
            (self._trace_dir / file).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            (self._trace_dir / task_id).rmdir()

    # Evidence Packs

    def put_evidence_pack(self, task_id: str, pack: EvidencePack) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO evidence_packs (task_id, pack_json) VALUES (?, ?)"
                " ON CONFLICT (task_id) DO UPDATE SET pack_json = excluded.pack_json",
                (task_id, encode_pack(pack)),
            )

    def evidence_pack(self, task_id: str) -> EvidencePack | None:
        row = self._conn.execute(
            "SELECT pack_json FROM evidence_packs WHERE task_id = ?", (task_id,)
        ).fetchone()
        return None if row is None else decode_pack(row["pack_json"])

    # Packages

    def add_package(self, package: Package) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO packages (id, type, title, summary, content, scope_project,"
                " scope_json, evidence_json, origin_project, origin_tasks_json, superseded_by, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    package.id,
                    package.type.value,
                    package.title,
                    package.summary,
                    package.content,
                    package.scope.project,
                    json.dumps(
                        {name: sorted(values) for name, values in package.scope.attributes.items()}
                    ),
                    json.dumps(list(package.evidence)),
                    package.provenance.project,
                    json.dumps(list(package.provenance.task_ids)),
                    package.superseded_by,
                    self._next_seq("packages"),
                ),
            )
            self._conn.executemany(
                "INSERT INTO package_goals (package_id, goal_id, position) VALUES (?, ?, ?)",
                [(package.id, goal_id, i) for i, goal_id in enumerate(package.goal_ids)],
            )
            self._conn.executemany(
                "INSERT INTO package_history (package_id, position, state, reason)"
                " VALUES (?, ?, ?, ?)",
                [
                    (package.id, i, change.state.value, change.reason)
                    for i, change in enumerate(package.history)
                ],
            )

    def add_package_state(
        self, package_id: str, change: StateChange, superseded_by: str | None
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO package_history (package_id, position, state, reason)"
                " SELECT ?, coalesce(max(position), -1) + 1, ?, ? FROM package_history"
                " WHERE package_id = ?",
                (package_id, change.state.value, change.reason, package_id),
            )
            self._conn.execute(
                "UPDATE packages SET superseded_by = ? WHERE id = ?", (superseded_by, package_id)
            )

    def find_package(self, package_id: str) -> Package | None:
        row = self._conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        return None if row is None else self._package_from(row)

    def list_packages(self, state: PackageState | None) -> list[Package]:
        rows = self._conn.execute("SELECT * FROM packages ORDER BY seq").fetchall()
        packages = [self._package_from(row) for row in rows]
        return [p for p in packages if state is None or p.state is state]

    def _package_from(self, row: sqlite3.Row) -> Package:
        goals = self._conn.execute(
            "SELECT goal_id FROM package_goals WHERE package_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        history = self._conn.execute(
            "SELECT state, reason FROM package_history WHERE package_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        scope: dict[str, list[str]] = json.loads(row["scope_json"])
        return Package(
            id=row["id"],
            type=PackageType(row["type"]),
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            scope=ApplicabilityScope(
                project=row["scope_project"],
                attributes={name: frozenset(values) for name, values in scope.items()},
            ),
            goal_ids=tuple(g["goal_id"] for g in goals),
            evidence=tuple(json.loads(row["evidence_json"])),
            provenance=Provenance(
                project=row["origin_project"],
                task_ids=tuple(json.loads(row["origin_tasks_json"])),
            ),
            history=tuple(StateChange(PackageState(h["state"]), h["reason"]) for h in history),
            superseded_by=row["superseded_by"],
        )

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
