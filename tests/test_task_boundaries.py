"""BS-001 and BS-006: Task boundaries and Predecessor Tasks, reported by a Harness Adapter through
the core public API."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from experience_factory import (
    ConflictingContinuationError,
    ExperienceBase,
    NoSuchTaskError,
    PredecessorsFixedError,
    Task,
    TaskNotOpenError,
    open_experience_base,
)

PROJECT = "experience-factory"


class FakeHarnessAdapter:
    """Reports Task boundaries the way a Harness Adapter does, using only the core public API."""

    def __init__(self, experience_base: ExperienceBase, project: str = PROJECT) -> None:
        self._experience_base = experience_base
        self._project = project

    def start_session(
        self,
        *,
        work_item: str | None = None,
        continues: Task | None = None,
        depends_on: Sequence[Task] = (),
    ) -> Task:
        return self._experience_base.start_session(
            self._project,
            work_item=work_item,
            continues_task=None if continues is None else continues.id,
            depends_on=[task.id for task in depends_on],
        )

    def end_task(self, task: Task) -> None:
        self._experience_base.end_task(task.id)


@pytest.fixture
def adapter(experience_base: ExperienceBase) -> FakeHarnessAdapter:
    return FakeHarnessAdapter(experience_base)


# BS-001: resolving which Task a session belongs to


def test_a_session_with_no_work_item_and_no_declaration_starts_a_new_task(
    adapter: FakeHarnessAdapter,
) -> None:
    open_task = adapter.start_session()

    task = adapter.start_session()

    assert task.id != open_task.id
    assert task.project == PROJECT
    assert task.is_open


def test_a_session_on_a_work_item_bound_to_an_open_task_continues_that_task(
    adapter: FakeHarnessAdapter,
) -> None:
    open_task = adapter.start_session(work_item="#12")

    task = adapter.start_session(work_item="#12")

    assert task == open_task


def test_a_session_declared_as_a_continuation_joins_the_declared_task(
    adapter: FakeHarnessAdapter,
) -> None:
    open_task = adapter.start_session()

    task = adapter.start_session(continues=open_task)

    assert task == open_task


def test_a_later_process_continues_the_open_task_of_a_work_item(db_path: Path) -> None:
    with open_experience_base(db_path) as first_hook:
        open_task = FakeHarnessAdapter(first_hook).start_session(work_item="#12")

    with open_experience_base(db_path) as second_hook:
        task = FakeHarnessAdapter(second_hook).start_session(work_item="#12")

    assert task == open_task


def test_a_session_naming_a_work_item_and_continuing_a_different_task_is_refused(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    adapter.start_session(work_item="#12")
    other = adapter.start_session()

    with pytest.raises(ConflictingContinuationError):
        adapter.start_session(work_item="#12", continues=other)

    assert experience_base.get_task(other.id).work_item is None


def test_a_session_naming_a_work_item_may_declare_it_continues_that_work_items_task(
    adapter: FakeHarnessAdapter,
) -> None:
    open_task = adapter.start_session(work_item="#12")

    task = adapter.start_session(work_item="#12", continues=open_task)

    assert task == open_task


def test_a_session_cannot_continue_an_ended_task(adapter: FakeHarnessAdapter) -> None:
    ended = adapter.start_session()
    adapter.end_task(ended)

    with pytest.raises(TaskNotOpenError):
        adapter.start_session(continues=ended)


def test_a_session_cannot_continue_a_task_of_another_project(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    elsewhere = FakeHarnessAdapter(experience_base, project="another-project").start_session()

    with pytest.raises(NoSuchTaskError):
        adapter.start_session(continues=elsewhere)


def test_a_session_cannot_continue_a_task_that_does_not_exist(
    experience_base: ExperienceBase,
) -> None:
    with pytest.raises(NoSuchTaskError):
        experience_base.start_session(PROJECT, continues_task="no-such-task")


# Ending a Task


def test_an_ended_task_is_no_longer_open(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    task = adapter.start_session(work_item="#11")

    adapter.end_task(task)

    assert experience_base.get_task(task.id).is_open is False


def test_a_session_on_the_work_item_of_an_ended_task_starts_a_new_task(
    adapter: FakeHarnessAdapter,
) -> None:
    ended = adapter.start_session(work_item="#11")
    adapter.end_task(ended)

    task = adapter.start_session(work_item="#11")

    assert task.id != ended.id
    assert task.is_open


def test_an_ended_task_cannot_be_ended_again(adapter: FakeHarnessAdapter) -> None:
    task = adapter.start_session()
    adapter.end_task(task)

    with pytest.raises(TaskNotOpenError):
        adapter.end_task(task)


def test_ending_a_task_that_does_not_exist_is_refused(experience_base: ExperienceBase) -> None:
    with pytest.raises(NoSuchTaskError):
        experience_base.end_task("no-such-task")


# BS-006: a Task records its Predecessor Tasks


def test_a_task_started_with_a_dependency_records_its_predecessor_task(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    predecessor = adapter.start_session(work_item="#11")
    adapter.end_task(predecessor)

    task = adapter.start_session(work_item="#12", depends_on=[predecessor])

    assert experience_base.get_task(task.id).predecessor_ids == (predecessor.id,)


def test_a_task_records_each_predecessor_task_once_in_the_order_declared(
    adapter: FakeHarnessAdapter,
) -> None:
    first = adapter.start_session(work_item="#10")
    second = adapter.start_session(work_item="#11")

    task = adapter.start_session(work_item="#12", depends_on=[second, first, second])

    assert task.predecessor_ids == (second.id, first.id)


def test_a_session_joining_an_open_task_by_its_work_item_cannot_add_predecessor_tasks(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    earlier = adapter.start_session(work_item="#11")
    open_task = adapter.start_session(work_item="#12")

    with pytest.raises(PredecessorsFixedError):
        adapter.start_session(work_item="#12", depends_on=[earlier])

    assert experience_base.get_task(open_task.id).predecessor_ids == ()


def test_a_session_continuing_an_open_task_cannot_add_predecessor_tasks(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    earlier = adapter.start_session(work_item="#11")
    open_task = adapter.start_session()

    with pytest.raises(PredecessorsFixedError):
        adapter.start_session(continues=open_task, depends_on=[earlier])

    assert experience_base.get_task(open_task.id).predecessor_ids == ()


def test_a_dependency_on_a_task_that_does_not_exist_is_refused_and_no_task_opens(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    predecessor = adapter.start_session(work_item="#11")

    with pytest.raises(NoSuchTaskError):
        experience_base.start_session(PROJECT, work_item="#12", depends_on=["no-such-task"])

    task = adapter.start_session(work_item="#12", depends_on=[predecessor])
    assert task.predecessor_ids == (predecessor.id,)


def test_a_dependency_on_a_task_of_another_project_is_refused(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    elsewhere = FakeHarnessAdapter(experience_base, project="another-project").start_session()

    with pytest.raises(NoSuchTaskError):
        adapter.start_session(work_item="#12", depends_on=[elsewhere])
