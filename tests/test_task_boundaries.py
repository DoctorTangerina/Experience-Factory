"""BS-001 and BS-006: Task boundaries and Predecessor Tasks, reported by a Harness Adapter through
the core public API."""

from dataclasses import replace
from pathlib import Path

import pytest

from experience_factory import (
    ConflictingContinuationError,
    ExperienceBase,
    NoSuchTaskError,
    PredecessorsFixedError,
    TaskNotOpenError,
    open_experience_base,
)
from tests.support import PROJECT, FakeHarnessAdapter

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


def test_a_session_naming_a_work_item_whose_task_ended_and_continuing_another_task_is_refused(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    work_items_task = adapter.start_session(work_item="#12")
    adapter.end_task(work_items_task)
    other = adapter.start_session()
    adapter.end_task(other)

    with pytest.raises(ConflictingContinuationError):
        adapter.start_session(work_item="#12", continues=other)

    assert experience_base.get_task(other.id) == replace(other, is_open=False)
    assert experience_base.get_task(work_items_task.id) == replace(work_items_task, is_open=False)


def test_a_session_continuing_a_task_bound_to_another_work_item_is_refused(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    bound = adapter.start_session(work_item="#11")

    with pytest.raises(ConflictingContinuationError):
        adapter.start_session(work_item="#12", continues=bound)

    assert experience_base.get_task(bound.id).work_item == "#11"
    assert adapter.start_session(work_item="#12").id != bound.id


def test_a_session_naming_a_work_item_with_no_task_joins_the_task_it_continues_and_binds_it(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    unbound = adapter.start_session()

    task = adapter.start_session(work_item="#12", continues=unbound)

    assert task.id == unbound.id
    assert task.work_item == "#12"
    assert task.is_open
    assert adapter.start_session(work_item="#12").id == unbound.id
    assert experience_base.get_task(unbound.id).work_item == "#12"


def test_a_session_naming_a_work_item_with_no_task_reopens_the_ended_task_it_continues(
    adapter: FakeHarnessAdapter,
) -> None:
    unbound = adapter.start_session()
    adapter.end_task(unbound)

    task = adapter.start_session(work_item="#12", continues=unbound)

    assert task.id == unbound.id
    assert task.work_item == "#12"
    assert task.is_open


def test_a_session_naming_a_work_item_may_declare_it_continues_that_work_items_task(
    adapter: FakeHarnessAdapter,
) -> None:
    open_task = adapter.start_session(work_item="#12")

    task = adapter.start_session(work_item="#12", continues=open_task)

    assert task == open_task


def test_a_session_continuing_an_ended_task_reopens_that_task(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    ended = adapter.start_session()
    adapter.end_task(ended)

    task = adapter.start_session(continues=ended)

    assert task.id == ended.id
    assert task.is_open
    assert experience_base.get_task(ended.id).is_open


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


def test_a_session_on_the_work_item_of_an_ended_task_reopens_that_task(
    adapter: FakeHarnessAdapter,
) -> None:
    ended = adapter.start_session(work_item="#11")
    adapter.end_task(ended)

    task = adapter.start_session(work_item="#11")

    assert task.id == ended.id
    assert task.is_open


def test_a_reopened_task_keeps_its_project_work_item_and_predecessor_tasks(
    adapter: FakeHarnessAdapter,
) -> None:
    predecessor = adapter.start_session(work_item="#10")
    task = adapter.start_session(work_item="#11", depends_on=[predecessor])
    adapter.end_task(task)

    reopened = adapter.start_session(work_item="#11")

    assert reopened == replace(task, is_open=True)
    assert reopened.project == PROJECT
    assert reopened.predecessor_ids == (predecessor.id,)


def test_a_reopened_task_can_be_ended_again_but_not_twice(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter
) -> None:
    task = adapter.start_session()
    adapter.end_task(task)
    adapter.start_session(continues=task)

    adapter.end_task(task)

    assert not experience_base.get_task(task.id).is_open
    with pytest.raises(TaskNotOpenError):
        adapter.end_task(task)


def test_sessions_from_two_processes_reopening_a_work_items_task_land_on_that_one_task(
    db_path: Path,
) -> None:
    with open_experience_base(db_path) as setup:
        adapter = FakeHarnessAdapter(setup)
        ended = adapter.start_session(work_item="#11")
        adapter.end_task(ended)

    with open_experience_base(db_path) as first, open_experience_base(db_path) as second:
        from_first = FakeHarnessAdapter(first).start_session(work_item="#11")
        from_second = FakeHarnessAdapter(second).start_session(work_item="#11")

    assert from_first.id == from_second.id == ended.id
    assert from_first.is_open and from_second.is_open


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


@pytest.mark.parametrize("reopened_by", ["work item", "continuation"])
def test_a_session_reopening_a_task_cannot_add_predecessor_tasks(
    experience_base: ExperienceBase, adapter: FakeHarnessAdapter, reopened_by: str
) -> None:
    earlier = adapter.start_session(work_item="#10")
    ended = adapter.start_session(work_item="#12")
    adapter.end_task(ended)

    with pytest.raises(PredecessorsFixedError):
        if reopened_by == "work item":
            adapter.start_session(work_item="#12", depends_on=[earlier])
        else:
            adapter.start_session(continues=ended, depends_on=[earlier])

    assert experience_base.get_task(ended.id) == replace(ended, is_open=False)


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
