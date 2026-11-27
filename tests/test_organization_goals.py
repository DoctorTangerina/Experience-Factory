"""US-001: Organization Goals with Questions and Metrics, through the core public API."""

from pathlib import Path

from experience_memory import ExperienceMemory, MetricKind, open_memory


def test_a_defined_organization_goal_is_listed(memory: ExperienceMemory) -> None:
    memory.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    [goal] = memory.list_organization_goals()

    assert goal.purpose == "understand"
    assert goal.issue == "why Tasks fail"
    assert goal.object == "agent Tasks"
    assert goal.viewpoint == "the Organization"


def test_a_goal_is_refined_into_questions(memory: ExperienceMemory) -> None:
    goal = memory.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    memory.add_question(goal.id, text="How many tool calls does a Task make?")
    memory.add_question(goal.id, text="How many tool calls fail?")

    [listed] = memory.list_organization_goals()
    assert [q.text for q in listed.questions] == [
        "How many tool calls does a Task make?",
        "How many tool calls fail?",
    ]


def test_the_gqm_plan_persists_across_reopening(db_path: Path) -> None:
    with open_memory(db_path) as memory:
        goal = memory.define_organization_goal(
            purpose="understand",
            issue="why Tasks fail",
            object="agent Tasks",
            viewpoint="the Organization",
        )
        question = memory.add_question(goal.id, text="Did the Task follow its plan?")
        memory.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
            rubric="5: every step followed ... 1: plan ignored",
        )

    with open_memory(db_path) as reopened:
        [listed] = reopened.list_organization_goals()

    assert listed.issue == "why Tasks fail"
    [listed_question] = listed.questions
    assert listed_question.text == "Did the Task follow its plan?"
    [metric] = listed_question.metrics
    assert metric.name == "plan adherence"
    assert metric.kind is MetricKind.JUDGED
    assert metric.rubric == "5: every step followed ... 1: plan ignored"
