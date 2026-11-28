"""Traces: the harness-neutral record of what a Project Agent did during a Task (ADR-0005).

A Harness Adapter converts its harness's native transcript into this schema and hands it over one
session segment at a time. The core accepts only this schema, and scrubs secrets from every segment
before it is stored, so no secret is kept even within the retention window.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from experience_factory.scrubbing import scrub_json, scrub_json_object, scrub_text
from experience_factory.tasks import NoSuchTaskError, TaskNotOpenError

if TYPE_CHECKING:
    from experience_factory.storage import TaskStore, TraceStore


class TraceSchemaError(TypeError):
    """A Harness Adapter handed over something other than the core's harness-neutral Trace schema,
    such as its harness's native transcript (ADR-0005)."""


type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
"""A value as JSON can carry it: tool call arguments and results are made of these."""


@dataclass(frozen=True)
class Prompt:
    """A prompt the Project Agent received."""

    text: str


@dataclass(frozen=True)
class ToolCall:
    """A tool the Project Agent called, with the arguments it passed and the result it got back."""

    tool: str
    arguments: dict[str, JsonValue]
    result: JsonValue


@dataclass(frozen=True)
class TraceError:
    """An error raised during the session, by the harness, a tool or the model."""

    message: str


type TraceEvent = Prompt | ToolCall | TraceError


@dataclass(frozen=True)
class TraceSegment:
    """The part of a Task's Trace captured in one harness session: its events in the order they
    happened, and the state the session ended in (such as "completed" or "interrupted"), if the
    harness reports one."""

    events: tuple[TraceEvent, ...]
    end_state: str | None = None


@dataclass(frozen=True)
class TraceSpan:
    """One event of a Trace, with the reference Lessons Learned and Packages cite it by."""

    reference: str
    event: TraceEvent


@dataclass(frozen=True)
class Trace:
    """A Task's Trace: its session segments in the order they were handed over.

    Once its Project's retention window has expired and retention has been applied, the Trace is
    reduced: its segments are gone and `retained_spans` holds the spans that live Lessons Learned
    or Packages cite, in Trace order.
    """

    task_id: str
    segments: tuple[TraceSegment, ...]
    retained_spans: tuple[TraceSpan, ...] | None = None

    @property
    def is_reduced(self) -> bool:
        """Whether retention has reduced the Trace to its cited spans."""
        return self.retained_spans is not None

    @property
    def spans(self) -> tuple[TraceSpan, ...]:
        """The Trace's events as citable spans, in order: every event of every segment, or only
        the retained spans of a reduced Trace."""
        if self.retained_spans is not None:
            return self.retained_spans
        events = (event for segment in self.segments for event in segment.events)
        return tuple(
            TraceSpan(span_reference(self.task_id, number), event)
            for number, event in enumerate(events, start=1)
        )


_SPAN_REFERENCE = re.compile(r"(?P<task_id>[^#]+)#span-(?P<number>[1-9][0-9]*)")


def span_reference(task_id: str, number: int) -> str:
    """The reference that cites span `number` of the Task's Trace: its events are numbered from 1,
    across segments, in the order they happened."""
    return f"{task_id}#span-{number}"


def parse_span_reference(reference: str) -> tuple[str, int] | None:
    """The Task id and span number `reference` cites, or None if it does not cite a Trace span
    (evidence may also cite other things, such as an Evidence Pack)."""
    match = _SPAN_REFERENCE.fullmatch(reference)
    if match is None:
        return None
    return match["task_id"], int(match["number"])


class Traces:
    """Accepts Trace segments from Harness Adapters, scrubs them and stores them."""

    def __init__(self, store: TraceStore, tasks: TaskStore) -> None:
        self._store = store
        self._tasks = tasks

    def hand_over(self, task_id: str, segment: TraceSegment) -> None:
        _check_schema(segment)
        if not self._store.add_trace_segment(task_id, _scrubbed(segment)):
            self._require_task(task_id)
            raise TaskNotOpenError(f"Task {task_id!r} has ended; its Trace is closed")

    def trace(self, task_id: str) -> Trace:
        self._require_task(task_id)
        retained = self._store.retained_trace_spans(task_id)
        if retained is not None:
            return Trace(
                task_id=task_id,
                segments=(),
                retained_spans=tuple(
                    TraceSpan(span_reference(task_id, number), event)
                    for number, event in sorted(retained.items())
                ),
            )
        return Trace(task_id=task_id, segments=tuple(self._store.trace_segments(task_id)))

    def _require_task(self, task_id: str) -> None:
        if self._tasks.find_task(task_id) is None:
            raise NoSuchTaskError(f"no Task with id {task_id!r}")


def _check_schema(segment: object) -> None:
    """Refuse `segment` unless it is in the harness-neutral Trace schema, all the way down. The
    static types say the same, but nothing makes a Harness Adapter heed them."""
    if not isinstance(segment, TraceSegment):
        raise TraceSchemaError(f"expected a TraceSegment, got {type(segment).__name__}")
    events = _unchecked(segment.events)
    if not isinstance(events, tuple):
        raise TraceSchemaError("a segment's events must be a tuple")
    for event in cast(tuple[object, ...], events):
        _check_event(event)
    _check_text(segment.end_state, "a segment's end state", optional=True)


def _check_event(event: object) -> None:
    match event:
        case Prompt(text):
            _check_text(text, "a prompt")
        case ToolCall(tool, arguments, result):
            _check_text(tool, "a tool call's tool")
            if not isinstance(_unchecked(arguments), dict):
                raise TraceSchemaError("tool call arguments must be a JSON object")
            _check_json(arguments, "tool call arguments")
            _check_json(result, "a tool call result")
        case TraceError(message):
            _check_text(message, "an error")
        case _:
            raise TraceSchemaError(f"not a Trace event of the harness-neutral schema: {event!r}")


def _check_text(value: object, what: str, *, optional: bool = False) -> None:
    if not (isinstance(value, str) or (optional and value is None)):
        raise TraceSchemaError(f"{what} must be text, got {type(value).__name__}")


def _check_json(value: object, what: str) -> None:
    match value:
        case None | bool() | int() | str():
            pass
        case float() if math.isfinite(value):
            pass
        case list():
            for item in cast(list[object], value):
                _check_json(item, what)
        case dict():
            for key, item in cast(dict[object, object], value).items():
                if not isinstance(key, str):
                    raise TraceSchemaError(f"{what} have a key that is not text: {key!r}")
                _check_json(item, what)
        case _:
            raise TraceSchemaError(f"{what} hold a value JSON cannot carry: {value!r}")


def _unchecked(value: object) -> object:
    """`value` as a plain object, so its runtime type can be checked against the declared one."""
    return value


def _scrubbed(segment: TraceSegment) -> TraceSegment:
    return TraceSegment(
        events=tuple(_scrubbed_event(event) for event in segment.events),
        end_state=None if segment.end_state is None else scrub_text(segment.end_state),
    )


def _scrubbed_event(event: TraceEvent) -> TraceEvent:
    match event:
        case Prompt(text):
            return Prompt(scrub_text(text))
        case ToolCall(tool, arguments, result):
            return ToolCall(
                tool=scrub_text(tool),
                arguments=scrub_json_object(arguments),
                result=scrub_json(result),
            )
        case TraceError(message):
            return TraceError(scrub_text(message))


# The stored form of a segment. Bump the version when the schema changes, and keep reading the old.
_ENCODING_VERSION = 1


def encode_segment(segment: TraceSegment) -> bytes:
    """`segment` as UTF-8 JSON, the form it is stored in."""
    document = {
        "version": _ENCODING_VERSION,
        "events": [encode_event(event) for event in segment.events],
        "end_state": segment.end_state,
    }
    return json.dumps(document, ensure_ascii=False, allow_nan=False).encode()


def encode_event(event: TraceEvent) -> dict[str, JsonValue]:
    """`event` as a JSON object, the form a retained span is stored in."""
    match event:
        case Prompt(text):
            return {"type": "prompt", "text": text}
        case ToolCall(tool, arguments, result):
            return {"type": "tool_call", "tool": tool, "arguments": arguments, "result": result}
        case TraceError(message):
            return {"type": "error", "message": message}


def decode_segment(data: bytes) -> TraceSegment:
    """The segment `encode_segment` turned into `data`."""
    document: dict[str, Any] = json.loads(data)
    return TraceSegment(
        events=tuple(decode_event(event) for event in document["events"]),
        end_state=document["end_state"],
    )


def decode_event(event: dict[str, Any]) -> TraceEvent:
    """The event `encode_event` turned into `event`."""
    match event["type"]:
        case "prompt":
            return Prompt(event["text"])
        case "tool_call":
            return ToolCall(
                tool=event["tool"], arguments=event["arguments"], result=event["result"]
            )
        case _:
            return TraceError(event["message"])
