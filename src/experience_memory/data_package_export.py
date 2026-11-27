"""Data Package export as Parquet, for research analysis outside the system (US-005, ADR-0004).

One row per recorded value. Each row carries everything needed to interpret the value: the Metric
version's definition, kind, rubric and judge, the model that produced a judged value, the Task's
Characterization with its schema version, the Goals selected for the Task and its Holdout
assignment.

pyarrow is imported only here, so commands that never export do not pay for loading it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from experience_memory.data_packages import AttributeValue, DataPackageRecord
from experience_memory.gqm import Goal, GoalStatement

# A Goal is exported as its id and version followed by every field of what it states.
_GOAL = pa.struct(
    [
        ("id", pa.string()),
        ("version", pa.int64()),
        *((part.name, pa.string()) for part in fields(GoalStatement)),
    ]
)


def write_parquet(records: Sequence[DataPackageRecord], path: Path) -> None:
    set_valued = _attribute_shapes(records)
    schema = pa.schema(
        [
            ("task_id", pa.string()),
            ("value", pa.float64()),
            ("metric_id", pa.string()),
            ("metric_version", pa.int64()),
            ("metric_name", pa.string()),
            ("metric_kind", pa.string()),
            ("metric_definition", pa.string()),
            ("metric_rubric", pa.string()),
            ("judge_provider", pa.string()),
            ("judge_model", pa.string()),
            ("judge_effort", pa.string()),
            ("judged_by_model", pa.string()),
            ("characterization_schema_version", pa.string()),
            ("characterization", _characterization_type(set_valued)),
            ("goals", pa.list_(_GOAL)),
            ("holdout", pa.bool_()),
        ]
    )
    rows = [_row(record, set_valued) for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)  # pyright: ignore[reportUnknownMemberType]


def _attribute_shapes(records: Sequence[DataPackageRecord]) -> dict[str, bool]:
    """Every attribute seen in any record, mapped to whether any record holds it as a set."""
    set_valued: dict[str, bool] = {}
    for record in records:
        for name, value in record.characterization.attributes.items():
            set_valued[name] = set_valued.get(name, False) or not isinstance(value, str)
    return dict(sorted(set_valued.items()))


def _characterization_type(set_valued: Mapping[str, bool]) -> pa.DataType:
    """A struct with one field per attribute seen in any record.

    An attribute held as a set in any record is a list of strings in every record, so each
    attribute keeps a single column type. A record without an attribute exports it as null.
    Parquet cannot store a struct without fields, so with no attributes at all the column is
    null-typed.
    """
    if not set_valued:
        return pa.null()
    return pa.struct(
        [
            (name, pa.list_(pa.string()) if is_set else pa.string())
            for name, is_set in set_valued.items()
        ]
    )


def _row(record: DataPackageRecord, set_valued: Mapping[str, bool]) -> dict[str, Any]:
    metric = record.metric
    definition = metric.definition
    judge_provider, judge_model, judge_effort = definition.judge_parts()
    return {
        "task_id": record.task_id,
        "value": record.value,
        "metric_id": metric.id,
        "metric_version": metric.version,
        "metric_name": metric.name,
        "metric_kind": definition.kind.value,
        "metric_definition": definition.text,
        "metric_rubric": definition.rubric,
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "judge_effort": judge_effort,
        "judged_by_model": record.judged_by_model,
        "characterization_schema_version": record.characterization.schema_version,
        "characterization": _characterization(record.characterization.attributes, set_valued),
        "goals": [_goal(goal) for goal in record.goals],
        "holdout": record.holdout,
    }


def _goal(goal: Goal) -> dict[str, Any]:
    return {"id": goal.id, "version": goal.version, **asdict(goal.statement)}


def _characterization(
    attributes: Mapping[str, AttributeValue], set_valued: Mapping[str, bool]
) -> dict[str, str | list[str] | None] | None:
    if not set_valued:
        return None
    exported: dict[str, str | list[str] | None] = {}
    for name, is_set in set_valued.items():
        value = attributes.get(name)
        if value is None or (isinstance(value, str) and not is_set):
            exported[name] = value
        else:
            exported[name] = [value] if isinstance(value, str) else sorted(value)
    return exported
