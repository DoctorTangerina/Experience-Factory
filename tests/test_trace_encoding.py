"""The stored form of a Trace (#68): Traces and retained spans written by earlier versions of the
core still decode the same, and a stored event of a type the core does not know is refused.

Driven at the encoding seam, since a stored Trace cannot be written in an older form through the
core public API."""

import pytest

from experience_factory import ErrorEvent, Prompt, ToolCall, TraceSegment
from experience_factory.traces import decode_event, decode_segment

# A segment exactly as the core stored it before the error event was renamed.
STORED_SEGMENT = (
    b'{"version": 1, "events": ['
    b'{"type": "prompt", "text": "Fix the flaky test"}, '
    b'{"type": "tool_call", "tool": "bash", "arguments": {"command": "pytest"}, '
    b'"result": "1 failed"}, '
    b'{"type": "error", "message": "pytest exited with status 1"}'
    b'], "end_state": "completed"}'
)


def test_a_segment_stored_before_the_error_event_was_renamed_decodes_the_same() -> None:
    assert decode_segment(STORED_SEGMENT) == TraceSegment(
        events=(
            Prompt("Fix the flaky test"),
            ToolCall(tool="bash", arguments={"command": "pytest"}, result="1 failed"),
            ErrorEvent("pytest exited with status 1"),
        ),
        end_state="completed",
    )


def test_a_retained_error_span_stored_before_the_rename_decodes_the_same() -> None:
    assert decode_event({"type": "error", "message": "timed out"}) == ErrorEvent("timed out")


def test_a_stored_event_of_an_unknown_type_is_refused() -> None:
    with pytest.raises(ValueError, match="'thought'"):
        decode_event({"type": "thought", "message": "maybe it is flaky"})
