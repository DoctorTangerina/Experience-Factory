"""BS-004 and the Trace hand-off: a Harness Adapter hands over Trace segments for a Task through the
core public API, and the core stores them with secrets scrubbed."""

from pathlib import Path
from typing import Any

import pytest

from experience_factory import (
    ExperienceBase,
    NoSuchTaskError,
    Prompt,
    Task,
    TaskNotOpenError,
    ToolCall,
    TraceError,
    TraceSchemaError,
    TraceSegment,
    open_experience_base,
)

PROJECT = "experience-factory"


def _fake(prefix: str, rest: str) -> str:
    """A fake credential, assembled at runtime so the source never holds one whole: secret
    scanners such as GitHub push protection would otherwise reject the commit."""
    return prefix + rest


API_KEY = _fake("sk-ant-", "api03-Xq7v9Lm2Rt5Wz8Kp1Nc4Hb6Jd3Fg0Ys")


class FakeHarnessAdapter:
    """Hands over Trace segments the way a Harness Adapter does, using only the core public API.

    It has already converted its harness's native transcript into the harness-neutral schema."""

    def __init__(self, experience_base: ExperienceBase) -> None:
        self._experience_base = experience_base

    def start_session(self) -> Task:
        return self._experience_base.start_session(PROJECT)

    def hand_over(self, task: Task, segment: TraceSegment) -> None:
        self._experience_base.hand_over_trace_segment(task.id, segment)


@pytest.fixture
def adapter(experience_base: ExperienceBase) -> FakeHarnessAdapter:
    return FakeHarnessAdapter(experience_base)


# BS-004: secrets are scrubbed from Traces


def test_a_credential_in_a_handed_over_trace_is_not_stored(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    segment = TraceSegment(events=(Prompt(f"Call the API with key {API_KEY} and report back"),))

    adapter.hand_over(task, segment)

    stored = experience_base.trace(task.id)
    assert stored.segments == (
        TraceSegment(events=(Prompt("Call the API with key [REDACTED] and report back"),)),
    )


@pytest.mark.parametrize(
    ("handed_over", "stored"),
    [
        pytest.param(
            TraceSegment(
                events=(
                    ToolCall(
                        tool="http",
                        arguments={"headers": [f"x-api-key: {API_KEY}"], "retries": 3},
                        result="ok",
                    ),
                )
            ),
            TraceSegment(
                events=(
                    ToolCall(
                        tool="http",
                        arguments={"headers": ["x-api-key: [REDACTED]"], "retries": 3},
                        result="ok",
                    ),
                )
            ),
            id="tool call argument",
        ),
        pytest.param(
            TraceSegment(
                events=(
                    ToolCall(
                        tool="bash",
                        arguments={"command": "env"},
                        result={"stdout": f"KEY={API_KEY}\nHOME=/home/agent", "exit_code": 0},
                    ),
                )
            ),
            TraceSegment(
                events=(
                    ToolCall(
                        tool="bash",
                        arguments={"command": "env"},
                        result={"stdout": "KEY=[REDACTED]\nHOME=/home/agent", "exit_code": 0},
                    ),
                )
            ),
            id="tool call result",
        ),
        pytest.param(
            TraceSegment(events=(TraceError(f"401 Unauthorized for key {API_KEY}"),)),
            TraceSegment(events=(TraceError("401 Unauthorized for key [REDACTED]"),)),
            id="error",
        ),
        pytest.param(
            TraceSegment(events=(), end_state=f"failed: rejected {API_KEY}"),
            TraceSegment(events=(), end_state="failed: rejected [REDACTED]"),
            id="end state",
        ),
    ],
)
def test_a_credential_is_scrubbed_wherever_it_appears_in_a_segment(
    adapter: FakeHarnessAdapter,
    experience_base: ExperienceBase,
    handed_over: TraceSegment,
    stored: TraceSegment,
) -> None:
    task = adapter.start_session()

    adapter.hand_over(task, handed_over)

    assert experience_base.trace(task.id).segments == (stored,)


# Fake credentials in the formats real ones take. Each case pairs the text handed over with the
# text stored: the credential is gone and the text around it is kept.
CREDENTIALS = [
    pytest.param(
        "use " + _fake("sk-", "proj-x9Qw2Er5Ty8Ui1Op4As7Df0Gh3Jk6Lz") + " now",
        "use [REDACTED] now",
        id="OpenAI API key",
    ),
    pytest.param(
        "token " + _fake("ghp_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8") + " cloned",
        "token [REDACTED] cloned",
        id="GitHub token",
    ),
    pytest.param(
        _fake("github_pat_", "11ABCDEFG0aBcDeFgHiJkL_mNoPqRsTuVwXyZ0123456789abcdefghijklmnop")
        + " ok",
        "[REDACTED] ok",
        id="GitHub fine-grained token",
    ),
    pytest.param(
        "push with " + _fake("glpat-", "Ab12Cd34Ef56Gh78Ij90") + " done",
        "push with [REDACTED] done",
        id="GitLab token",
    ),
    pytest.param(
        "id " + _fake("AKIA", "IOSFODNN7EXAMPLE") + " set",
        "id [REDACTED] set",
        id="AWS access key id",
    ),
    pytest.param(
        "post " + _fake("xoxb-", "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx") + " sent",
        "post [REDACTED] sent",
        id="Slack token",
    ),
    pytest.param(
        "maps " + _fake("AIza", "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q") + " loaded",
        "maps [REDACTED] loaded",
        id="Google API key",
    ),
    pytest.param(
        "charge " + _fake("sk_live_", "4eC39HqLyjWDarjtT1zdp7dc") + " ok",
        "charge [REDACTED] ok",
        id="Stripe secret key",
    ),
    pytest.param(
        "publish " + _fake("npm_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8") + " ok",
        "publish [REDACTED] ok",
        id="npm token",
    ),
    pytest.param(
        "pull " + _fake("hf_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7") + " ok",
        "pull [REDACTED] ok",
        id="Hugging Face token",
    ),
    pytest.param(
        "session "
        + _fake("eyJ", "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0")
        + ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U ok",
        "session [REDACTED] ok",
        id="JSON Web Token",
    ),
    pytest.param(
        "key:\n"
        + _fake("-----BEGIN RSA ", "PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n")
        + _fake("-----END RSA ", "PRIVATE KEY-----\nend"),
        "key:\n[REDACTED]\nend",
        id="private key block",
    ),
    pytest.param(
        "curl -H 'Authorization: Bearer abc123.def456-ghi789' https://api.example.com",
        "curl -H 'Authorization: Bearer [REDACTED]' https://api.example.com",
        id="bearer token",
    ),
    pytest.param(
        "clone https://agent:s3cr3t-Pa55@git.example.com/repo.git",
        "clone https://agent:[REDACTED]@git.example.com/repo.git",
        id="password in a URL",
    ),
    pytest.param(
        "export DATABASE_PASSWORD=hunter2 && run",
        "export DATABASE_PASSWORD=[REDACTED] && run",
        id="password assignment",
    ),
    pytest.param(
        'config: {"client_secret": "plain value 42", "max_tokens": 1000}',
        'config: {"client_secret": "[REDACTED]", "max_tokens": 1000}',
        id="quoted secret assignment",
    ),
    pytest.param(
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_secret_access_key = [REDACTED]",
        id="AWS secret access key",
    ),
    pytest.param(
        "GITHUB_TOKEN: abcdef0123456789",
        "GITHUB_TOKEN: [REDACTED]",
        id="token assignment",
    ),
]


@pytest.mark.parametrize(("handed_over", "stored"), CREDENTIALS)
def test_credentials_of_common_kinds_are_scrubbed(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase, handed_over: str, stored: str
) -> None:
    task = adapter.start_session()

    adapter.hand_over(task, TraceSegment(events=(Prompt(handed_over),)))

    assert experience_base.trace(task.id).segments == (TraceSegment(events=(Prompt(stored),)),)


def test_a_tool_call_argument_named_as_a_secret_is_scrubbed(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    call = ToolCall(
        tool="login",
        arguments={"user": "agent", "password": "correct horse", "api_key": "k-1", "tokens": 5},
        result={"access_token": "opaque", "input_tokens": 812},
    )

    adapter.hand_over(task, TraceSegment(events=(call,)))

    assert experience_base.trace(task.id).segments == (
        TraceSegment(
            events=(
                ToolCall(
                    tool="login",
                    arguments={
                        "user": "agent",
                        "password": "[REDACTED]",
                        "api_key": "[REDACTED]",
                        "tokens": 5,
                    },
                    result={"access_token": "[REDACTED]", "input_tokens": 812},
                ),
            )
        ),
    )


# The Trace hand-off


def test_a_tasks_trace_consists_of_the_segments_of_each_of_its_sessions(
    experience_base: ExperienceBase,
) -> None:
    first = experience_base.start_session(PROJECT, work_item="#14")
    experience_base.hand_over_trace_segment(first.id, TraceSegment(events=(Prompt("Start"),)))
    second = experience_base.start_session(PROJECT, work_item="#14")
    experience_base.hand_over_trace_segment(second.id, TraceSegment(events=(Prompt("Resume"),)))

    trace = experience_base.trace(first.id)

    assert trace.segments == (
        TraceSegment(events=(Prompt("Start"),)),
        TraceSegment(events=(Prompt("Resume"),)),
    )


def test_a_trace_is_still_stored_after_the_experience_base_is_reopened(db_path: Path) -> None:
    with open_experience_base(db_path) as experience_base:
        task = experience_base.start_session(PROJECT)
        experience_base.hand_over_trace_segment(task.id, TraceSegment(events=(Prompt("Go"),)))

    with open_experience_base(db_path) as reopened:
        trace = reopened.trace(task.id)

    assert trace.segments == (TraceSegment(events=(Prompt("Go"),)),)


def test_each_task_has_only_its_own_trace(experience_base: ExperienceBase) -> None:
    traced = experience_base.start_session(PROJECT)
    experience_base.hand_over_trace_segment(traced.id, TraceSegment(events=(Prompt("Go"),)))
    untraced = experience_base.start_session(PROJECT)

    assert experience_base.trace(untraced.id).segments == ()


def test_a_segment_keeps_prompts_tool_calls_errors_and_end_state_in_order(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    segment = TraceSegment(
        events=(
            Prompt("Run the tests"),
            ToolCall(
                tool="bash",
                arguments={"command": "pytest -q", "timeout": 120, "env": {"CI": True}},
                result={"exit_code": 1, "stdout": "1 failed", "files": ["a.py", None]},
            ),
            TraceError("Tool call timed out after 120 s"),
            ToolCall(tool="read", arguments={"path": "a.py"}, result="def f(): ..."),
        ),
        end_state="interrupted",
    )

    adapter.hand_over(task, segment)

    assert experience_base.trace(task.id).segments == (segment,)


# The core accepts only its harness-neutral Trace schema (ADR-0005)


def _untyped(value: object) -> Any:
    """`value` with its type hidden, to hand over what a misbehaving Harness Adapter might."""
    return value


NOT_THE_SCHEMA = [
    pytest.param(
        {"type": "user", "message": {"role": "user", "content": "Run the tests"}},
        id="a harness-native transcript entry",
    ),
    pytest.param(
        TraceSegment(events=_untyped(({"role": "user", "content": "Run the tests"},))),
        id="a native message among the events",
    ),
    pytest.param(
        TraceSegment(events=_untyped([Prompt("Run the tests")])),
        id="events not as a tuple",
    ),
    pytest.param(
        TraceSegment(events=(Prompt(_untyped(b"Run the tests")),)),
        id="a prompt that is not text",
    ),
    pytest.param(
        TraceSegment(
            events=(ToolCall(tool="bash", arguments=_untyped({"paths": {"a", "b"}}), result=""),)
        ),
        id="a tool call argument JSON cannot carry",
    ),
    pytest.param(
        TraceSegment(events=(ToolCall(tool="bash", arguments=_untyped(["ls"]), result=""),)),
        id="tool call arguments that are not an object",
    ),
    pytest.param(
        TraceSegment(events=(ToolCall(tool="bash", arguments={}, result=_untyped(object())),)),
        id="a tool call result JSON cannot carry",
    ),
    pytest.param(
        TraceSegment(events=(), end_state=_untyped(1)),
        id="an end state that is not text",
    ),
]


@pytest.mark.parametrize("handed_over", NOT_THE_SCHEMA)
def test_anything_but_the_harness_neutral_schema_is_refused_and_not_stored(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase, handed_over: object
) -> None:
    task = adapter.start_session()

    with pytest.raises(TraceSchemaError):
        adapter.hand_over(task, _untyped(handed_over))

    assert experience_base.trace(task.id).segments == ()


def test_a_segment_cannot_be_handed_over_for_a_task_that_does_not_exist(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    with pytest.raises(NoSuchTaskError):
        experience_base.hand_over_trace_segment("no-such-task", TraceSegment(events=()))


def test_a_segment_cannot_be_handed_over_for_a_task_that_has_ended(
    adapter: FakeHarnessAdapter, experience_base: ExperienceBase
) -> None:
    task = adapter.start_session()
    adapter.hand_over(task, TraceSegment(events=(Prompt("Go"),)))
    experience_base.end_task(task.id)

    with pytest.raises(TaskNotOpenError):
        adapter.hand_over(task, TraceSegment(events=(Prompt("Late"),)))

    assert experience_base.trace(task.id).segments == (TraceSegment(events=(Prompt("Go"),)),)
