"""BS-006: Exported Data Packages carry their measurement context (US-005, ADR-0004: Parquet)."""

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from experience_memory import Characterization, ExperienceBase, Goal, Judge, Metric, MetricKind

RUBRIC = "5: every step followed ... 1: plan ignored"


@pytest.fixture
def goal(experience_base: ExperienceBase) -> Goal:
    return experience_base.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )


@pytest.fixture
def plan_adherence_v2(experience_base: ExperienceBase, goal: Goal) -> Metric:
    question = experience_base.add_question(goal.id, text="Did the Task follow its plan?")
    v1 = experience_base.add_metric(
        question.id,
        name="plan adherence",
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric=RUBRIC,
        judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
    )
    return experience_base.redefine_metric(
        v1.id,
        definition="How closely the Task followed its stated plan.",
        kind=MetricKind.JUDGED,
        rubric=RUBRIC,
        judge=Judge(provider="anthropic", model="claude-sonnet-5-5", effort="medium"),
    )


def exported_rows(experience_base: ExperienceBase, path: Path) -> list[dict[str, Any]]:
    experience_base.export_data_packages(path)
    return pq.read_table(path).to_pylist()  # pyright: ignore[reportUnknownMemberType]


def test_each_exported_value_carries_its_measurement_context(
    experience_base: ExperienceBase, goal: Goal, plan_adherence_v2: Metric, tmp_path: Path
) -> None:
    experience_base.record_task(
        "task-1",
        characterization=Characterization(
            schema_version="1.2",
            attributes={
                "languages": frozenset({"python", "typescript"}),
                "task_type": "bugfix",
                "agent_model": "claude-opus-5-5",
            },
        ),
        goal_ids=[goal.id],
        holdout=True,
    )
    experience_base.record_metric_value(
        "task-1",
        metric_id=plan_adherence_v2.id,
        metric_version=plan_adherence_v2.version,
        value=4,
        judged_by_model="claude-sonnet-5-5-20261101",
    )

    [row] = exported_rows(experience_base, tmp_path / "data-packages.parquet")

    assert row["task_id"] == "task-1"
    assert row["value"] == 4.0
    assert row["metric_id"] == plan_adherence_v2.id
    assert row["metric_version"] == 2
    assert row["metric_name"] == "plan adherence"
    assert row["metric_kind"] == "judged"
    assert row["metric_rubric"] == RUBRIC
    assert (row["judge_provider"], row["judge_model"], row["judge_effort"]) == (
        "anthropic",
        "claude-sonnet-5-5",
        "medium",
    )
    assert row["judged_by_model"] == "claude-sonnet-5-5-20261101"
    assert row["characterization_schema_version"] == "1.2"
    assert row["characterization"] == {
        "agent_model": "claude-opus-5-5",
        "languages": ["python", "typescript"],
        "task_type": "bugfix",
    }
    assert row["goals"] == [
        {
            "id": goal.id,
            "version": 1,
            "purpose": "understand",
            "issue": "why Tasks fail",
            "object": "agent Tasks",
            "viewpoint": "the Organization",
        }
    ]
    assert row["holdout"] is True
