"""Command-line entry point. A thin shell over the core public API; it holds no rules of its own.

How humans define and approve GQM plan elements is still open (docs/pending-decisions.md),
so for now the CLI only inspects the plan.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from experience_memory.core import open_memory


def default_db_path() -> Path:
    """One Experience Base per machine (ADR-0004), overridable with EXPERIENCE_MEMORY_DB."""
    if override := os.environ.get("EXPERIENCE_MEMORY_DB"):
        return Path(override)
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "experience-memory" / "experience.db"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="experience-memory")
    parser.add_argument(
        "--db", type=Path, default=None, help="path to the Experience Base database"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    goals = commands.add_parser("goals", help="inspect the GQM plan's Goals")
    goal_commands = goals.add_subparsers(dest="goals_command", required=True)
    goal_commands.add_parser("list", help="list Organization Goals with Questions and Metrics")
    return parser


def _list_goals(db: Path) -> None:
    with open_memory(db) as memory:
        goals = memory.list_organization_goals()
    if not goals:
        print("No Organization Goals defined.")
        return
    for goal in goals:
        print(f"Goal {goal.id} v{goal.version}")
        print(f"  purpose:   {goal.purpose}")
        print(f"  issue:     {goal.issue}")
        print(f"  object:    {goal.object}")
        print(f"  viewpoint: {goal.viewpoint}")
        for question in goal.questions:
            print(f"  Question {question.id} v{question.version}: {question.text}")
            for metric in question.metrics:
                print(f"    Metric {metric.id} v{metric.version} [{metric.kind}]: {metric.name}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    db: Path = args.db or default_db_path()
    if args.command == "goals" and args.goals_command == "list":
        _list_goals(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
