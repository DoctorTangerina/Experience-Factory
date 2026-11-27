"""US-001: Organization Goals with Questions and Metrics, through the core public API."""

from pathlib import Path

from experience_factory import ExperienceBase, Judge, MetricKind, open_experience_base


def test_a_defined_organization_goal_is_listed(experience_base: ExperienceBase) -> None:
    experience_base.define_organization_goal(
        purpose="understand",
        issue="why Tasks fail",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    [goal] = experience_base.list_organization_goals()

    assert goal.statement.purpose == "understand"
    assert goal.statement.issue == "why Tasks fail"
    assert goal.statement.object == "agent Tasks"
    assert goal.statement.viewpoint == "the Organization"


def test_a_goal_is_refined_into_questions(experience_base: ExperienceBase) -> None:
    goal = experience_base.define_organization_goal(
        purpose="reduce",
        issue="wasted tool calls",
        object="agent Tasks",
        viewpoint="the Organization",
    )

    experience_base.add_question(goal.id, text="How many tool calls does a Task make?")
    experience_base.add_question(goal.id, text="How many tool calls fail?")

    [listed] = experience_base.list_organization_goals()
    assert [q.text for q in listed.questions] == [
        "How many tool calls does a Task make?",
        "How many tool calls fail?",
    ]


def test_the_gqm_plan_persists_across_reopening(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        goal = experience_base.define_organization_goal(
            purpose="understand",
            issue="why Tasks fail",
            object="agent Tasks",
            viewpoint="the Organization",
        )
        question = experience_base.add_question(goal.id, text="Did the Task follow its plan?")
        experience_base.add_metric(
            question.id,
            name="plan adherence",
            definition="How closely the Task followed its stated plan.",
            kind=MetricKind.JUDGED,
            rubric="5: every step followed ... 1: plan ignored",
            judge=Judge(provider="anthropic", model="claude-haiku-5-5", effort="low"),
        )

    with open_experience_base(db_path) as reopened:
        [listed] = reopened.list_organization_goals()

    assert listed.statement.issue == "why Tasks fail"
    [listed_question] = listed.questions
    assert listed_question.text == "Did the Task follow its plan?"
    [metric] = listed_question.metrics
    assert metric.name == "plan adherence"
    assert metric.definition.kind is MetricKind.JUDGED
    assert metric.definition.rubric == "5: every step followed ... 1: plan ignored"
    assert metric.definition.judge == Judge(
        provider="anthropic", model="claude-haiku-5-5", effort="low"
    )
