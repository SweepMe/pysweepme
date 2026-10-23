"""Tests for the ``Port`` trace subscriber mechanism (Phase 0)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from pysweepme.Ports import IncompleteMessageError, Port, TraceEvent


class FakePort(Port):
    """Minimal ``Port`` for trace testing — never touches real hardware.

    The base ``Port.__init__`` calls ``initialize_port_properties`` which looks up
    ``port_types[self.port_properties["type"]]``. Our fake type isn't registered there, so we bypass the parent
    ``__init__`` entirely and set up just the attributes the I/O path needs. The trace state comes from the class-level
    defaults of ``Port``, which is what a third-party subclass that bypasses ``__init__`` relies on, too.
    """

    def __init__(self, port_id: str = "FAKE") -> None:
        """Create a closed fake port that records what is written and returns what the test sets up."""
        self.port: object = None
        self.port_ID = port_id
        self.port_properties = {
            "type": "Fake",
            "active": True,
            "open": False,
            "clear": True,
            "Name": "",
            "NrDevices": 0,
            "debug": False,
            "ID": port_id,
            "rstrip": False,
            "raw_read": False,
            "raw_write": False,
            "timeout": 1,
            "delay": 0,
            "EOL": "\n",
            "EOLwrite": None,
            "EOLread": None,
            "Exception": True,
        }
        self.port_type = None
        self.actualwritetime = time.perf_counter()

        # Hooks for tests to inject behaviour.
        self.writes_log: list[str] = []
        self.raw_writes_log: list[bytes] = []
        self.next_read: str = ""
        self.next_raw_read: bytes = b""
        self.write_raises: Exception | None = None
        self.read_raises: BaseException | None = None

    def write_internal(self, cmd: str) -> None:
        """Record the command, or raise the error set up by the test."""
        if self.write_raises is not None:
            raise self.write_raises
        self.writes_log.append(cmd)

    def write_raw_internal(self, cmd: bytes) -> None:
        """Record the bytes, or raise the error set up by the test."""
        if self.write_raises is not None:
            raise self.write_raises
        self.raw_writes_log.append(cmd)

    def read_internal(self, _digits: int) -> str:
        """Return the message set up by the test, or raise its error."""
        if self.read_raises is not None:
            raise self.read_raises
        return self.next_read

    def read_raw_internal(self) -> bytes:
        """Return the bytes set up by the test, or raise its error."""
        if self.read_raises is not None:
            raise self.read_raises
        return self.next_raw_read

    def read_bytes_internal(self, count: int, *, break_on_termchar: bool) -> bytes:  # noqa: ARG002
        """Return up to count of the bytes set up by the test, or raise its error."""
        if self.read_raises is not None:
            raise self.read_raises
        return self.next_raw_read[:count]


@pytest.fixture
def port() -> FakePort:
    """A fresh ``FakePort`` per test."""
    return FakePort()


def test_empty_subscriber_list_is_a_noop(port: FakePort) -> None:
    """With no subscribers, write/read must complete without constructing events."""
    port.write("hello")
    assert port.writes_log == ["hello"]
    port.next_read = "world"
    assert port.read() == "world"


def test_subscribe_and_receive_write_event(port: FakePort) -> None:
    """A subscribed callback receives a ``TraceEvent`` after each write."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    port.write("MEAS:VOLT?")

    assert len(events) == 1
    ev = events[0]
    assert ev["direction"] == "write"
    assert ev["payload"] == "MEAS:VOLT?"
    assert ev["port"] == "FAKE"
    assert ev["ok"] is True
    assert ev["err"] is None
    assert isinstance(ev["t"], float)


def test_subscribe_and_receive_read_event(port: FakePort) -> None:
    """A subscribed callback receives a ``TraceEvent`` after each read."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.next_read = "3.14"

    answer = port.read()

    assert answer == "3.14"
    assert len(events) == 1
    assert events[0]["direction"] == "read"
    assert events[0]["payload"] == "3.14"
    assert events[0]["ok"] is True


def test_write_raw_emits_write_raw_event(port: FakePort) -> None:
    """``write_raw`` should emit ``direction == "write_raw"``."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    port.write_raw(b"\x01\x02\x03")

    assert len(events) == 1
    assert events[0]["direction"] == "write_raw"
    assert events[0]["payload"] == b"\x01\x02\x03"


def test_read_raw_emits_read_raw_event(port: FakePort) -> None:
    """``read_raw`` should emit ``direction == "read_raw"``."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.next_raw_read = b"\xde\xad\xbe\xef"

    answer = port.read_raw()

    assert answer == b"\xde\xad\xbe\xef"
    assert len(events) == 1
    assert events[0]["direction"] == "read_raw"
    assert events[0]["payload"] == b"\xde\xad\xbe\xef"


def test_read_bytes_emits_read_bytes_event(port: FakePort) -> None:
    """``read_bytes`` should emit ``direction == "read_bytes"``."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.next_raw_read = b""

    answer = port.read_bytes(2)

    assert answer == b""
    assert [(e["direction"], e["payload"]) for e in events] == [("read_bytes", b"")]


def test_read_raw_with_digits_is_reported_once_as_read_bytes(port: FakePort) -> None:
    """read_raw(digits) returns read_bytes(digits), so it is reported as the read_bytes() it is, and only once."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.next_raw_read = b""

    port.read_raw(3)

    assert [(e["direction"], e["payload"]) for e in events] == [("read_bytes", b"")]


@pytest.mark.parametrize("count", [0, -1])
def test_read_bytes_without_positive_count_does_not_emit(port: FakePort, count: int) -> None:
    """Nothing is read for count <= 0, so nothing is reported, like an empty write."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    assert port.read_bytes(count) == b""
    assert events == []


def test_empty_write_raw_does_not_emit(port: FakePort) -> None:
    """``write_raw(b"")`` sends nothing, like ``write("")``, so there is nothing to report."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    port.write_raw(b"")

    assert events == []
    assert port.raw_writes_log == []


def test_write_raw_rejecting_str_does_not_emit(port: FakePort) -> None:
    """A str is refused before anything is sent, so there is no I/O to report."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    with pytest.raises(TypeError):
        port.write_raw("*RST")  # type: ignore[arg-type]

    assert events == []


def test_incomplete_read_bytes_emits_with_ok_false_and_reraises(port: FakePort) -> None:
    """A read_bytes() that times out is reported as failed, with the error that shows the bytes received."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.read_raises = IncompleteMessageError("FAKE", b"", 4)

    with pytest.raises(IncompleteMessageError):
        port.read_bytes(4)

    assert len(events) == 1
    assert events[0]["direction"] == "read_bytes"
    assert events[0]["ok"] is False
    assert "received 1 of 4 bytes" in (events[0]["err"] or "")


def test_empty_write_does_not_emit(port: FakePort) -> None:
    """``write("")`` is a no-op in the existing API; no trace either."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    port.write("")

    assert events == []
    assert port.writes_log == []


def test_write_failure_emits_with_ok_false_and_reraises(port: FakePort) -> None:
    """If the underlying write raises, the event is still emitted (ok=False) and the exception propagates."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.write_raises = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        port.write("MEAS:VOLT?")

    assert len(events) == 1
    assert events[0]["direction"] == "write"
    assert events[0]["ok"] is False
    assert events[0]["err"] == "boom"


def test_read_failure_emits_with_ok_false_and_reraises(port: FakePort) -> None:
    """If the underlying read raises, the event is still emitted (ok=False) and the exception propagates."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.read_raises = TimeoutError("no data")

    with pytest.raises(TimeoutError, match="no data"):
        port.read()

    assert len(events) == 1
    assert events[0]["direction"] == "read"
    assert events[0]["ok"] is False
    assert events[0]["err"] == "no data"


def test_interrupted_read_is_reported_as_failed(port: FakePort) -> None:
    """A read ended by a BaseException such as KeyboardInterrupt is reported as failed, not as a successful read."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.read_raises = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        port.read()

    assert [event["ok"] for event in events] == [False]


def test_unsubscribe_stops_delivery(port: FakePort) -> None:
    """After ``unsubscribe_trace`` the callback no longer receives events."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.write("first")
    port.unsubscribe_trace(events.append)
    port.write("second")

    assert len(events) == 1
    assert events[0]["payload"] == "first"


def test_subscribe_is_idempotent(port: FakePort) -> None:
    """Subscribing the same callback twice should register it only once."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.subscribe_trace(events.append)  # second call should be a no-op

    port.write("hello")

    assert len(events) == 1


def test_unsubscribe_unknown_is_noop(port: FakePort) -> None:
    """Unsubscribing a callback that was never registered must not raise."""

    def cb(_event: TraceEvent) -> None:
        pass

    # should not raise
    port.unsubscribe_trace(cb)


def test_multiple_subscribers_all_receive(port: FakePort) -> None:
    """All registered subscribers should receive each event."""
    events_a: list[TraceEvent] = []
    events_b: list[TraceEvent] = []
    port.subscribe_trace(events_a.append)
    port.subscribe_trace(events_b.append)

    port.write("CMD")

    assert len(events_a) == 1
    assert len(events_b) == 1
    assert events_a[0] is not events_b[0] or events_a[0] == events_b[0]
    assert events_a[0]["payload"] == "CMD"
    assert events_b[0]["payload"] == "CMD"


def test_subscriber_exception_does_not_break_others(port: FakePort) -> None:
    """A buggy subscriber must not prevent later subscribers from running."""

    def bad_cb(_event: TraceEvent) -> None:
        msg = "subscriber bug"
        raise ValueError(msg)

    events: list[TraceEvent] = []
    port.subscribe_trace(bad_cb)
    port.subscribe_trace(events.append)

    # write should NOT raise even though the first subscriber does
    port.write("hello")

    assert len(events) == 1
    assert events[0]["payload"] == "hello"


def test_raising_subscriber_is_unsubscribed(port: FakePort) -> None:
    """A subscriber that raises is dropped rather than kept registered.

    Regression: a GUI consumer whose widget had been destroyed stayed subscribed and raised on every read and write for
    the rest of the measurement, producing one traceback per I/O in the debug log.
    """
    calls = [0]

    def bad_cb(_event: TraceEvent) -> None:
        calls[0] += 1
        msg = "Signal source has been deleted"
        raise RuntimeError(msg)

    port.subscribe_trace(bad_cb)

    port.write("first")
    port.write("second")
    port.write("third")

    # Called once, then removed — not once per write.
    assert calls[0] == 1
    assert bad_cb not in port._trace_subscribers


def test_healthy_subscriber_survives_a_neighbours_failure(port: FakePort) -> None:
    """Dropping a broken subscriber must not disturb the well-behaved ones."""

    def bad_cb(_event: TraceEvent) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    events: list[TraceEvent] = []
    port.subscribe_trace(bad_cb)
    port.subscribe_trace(events.append)

    port.write("one")
    port.write("two")

    assert bad_cb not in port._trace_subscribers
    assert events.append in port._trace_subscribers
    assert [e["payload"] for e in events] == ["one", "two"]


def test_subscriber_can_unsubscribe_itself_during_iteration(port: FakePort) -> None:
    """A callback that unsubscribes itself while being called must not break the dispatch."""
    call_count = [0]

    def self_unsub(_event: TraceEvent) -> None:
        call_count[0] += 1
        port.unsubscribe_trace(self_unsub)

    port.subscribe_trace(self_unsub)

    port.write("first")  # should call self_unsub once, then unsubscribe
    port.write("second")  # should NOT call self_unsub again

    assert call_count[0] == 1


def test_event_timestamp_is_monotonic(port: FakePort) -> None:
    """Successive events from the same port have monotonically non-decreasing timestamps."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    commands = ["a", "b", "c"]

    for cmd in commands:
        port.write(cmd)

    assert [e["payload"] for e in events] == commands
    assert events[0]["t"] <= events[1]["t"] <= events[2]["t"]


def test_event_port_field_carries_resource_string() -> None:
    """The ``port`` field in the event should match the resource string used to construct the Port."""
    p = FakePort(port_id="COM42")
    events: list[TraceEvent] = []
    p.subscribe_trace(events.append)

    p.write("hi")

    assert events[0]["port"] == "COM42"


def test_payload_object_passes_through_unmodified(port: FakePort) -> None:
    """The trace payload object must be the same object handed to write/read."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    cmd: Any = "VOLT 1.0"
    port.write(cmd)

    assert events[0]["payload"] is cmd


# ---------------------------------------------------------------------------
# Raw I/O that a port class does not implement
# ---------------------------------------------------------------------------


class NoRawPort(FakePort):
    """No raw implementation of its own, so the NotImplementedError of the base Port applies."""

    write_raw_internal = Port.write_raw_internal


def test_unsupported_raw_write_is_reported_as_failed() -> None:
    """The base Port no longer falls back to write(); its NotImplementedError shows up as one failed event."""
    port = NoRawPort()
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)

    with pytest.raises(NotImplementedError):
        port.write_raw(b"*RST")

    assert [(e["direction"], e["ok"]) for e in events] == [("write_raw", False)]
    assert port.writes_log == []


def test_subscribers_are_not_shared_between_ports() -> None:
    """The empty class-level default must never become a list that every port appends to."""
    first, second = FakePort("A"), FakePort("B")
    events: list[TraceEvent] = []

    first.subscribe_trace(events.append)
    second.write("*IDN?")

    assert events == []
    assert Port._trace_subscribers == ()


def test_consecutive_calls_are_each_reported(port: FakePort) -> None:
    """A write followed by a read, like the two halves of a query, yields two events."""
    events: list[TraceEvent] = []
    port.subscribe_trace(events.append)
    port.next_read = "ID"

    port.write("*IDN?")
    port.read()

    assert [e["direction"] for e in events] == ["write", "read"]
