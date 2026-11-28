"""US-005: a researcher exports Data Packages from the command line."""

from pathlib import Path

import pyarrow.parquet as pq

from experience_factory import Characterization, MetricKind, open_experience_base
from experience_factory.cli import main
from tests.support import define_project_goal, open_started_task


def test_the_cli_exports_data_packages_to_parquet(db_path: Path, tmp_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = define_project_goal(experience_base, issue="wasted tool calls")
        question = experience_base.add_question(
            goal.id, text="How many tool calls does a Task make?"
        )
        metric = experience_base.add_metric(
            question.id,
            name="tool calls per Task",
            definition="Number of tool calls in the Task's Trace.",
            kind=MetricKind.OBJECTIVE,
        )
        task = open_started_task(
            experience_base,
            goal_ids=[goal.id],
            characterization=Characterization(schema_version="1", attributes={"task_type": "docs"}),
        )
        experience_base.record_metric_value(task.id, metric_id=metric.id, metric_version=1, value=6)
    out = tmp_path / "export" / "data-packages.parquet"

    exit_code = main(["--db", str(db_path), "data-packages", "export", str(out)])

    assert exit_code == 0
    table = pq.read_table(out)  # pyright: ignore[reportUnknownMemberType]
    assert table.column("task_id").to_pylist() == [task.id]
    assert table.column("value").to_pylist() == [6.0]
