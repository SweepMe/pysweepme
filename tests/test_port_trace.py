"""Tests for the ``Port`` trace subscriber mechanism (Phase 0)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from pysweepme.Ports import Port, TraceCallback, TraceEvent


class FakePort(Port):
    """Minimal ``Port`` for trace testing — never touches real hardware.

    The base ``Port.__init__`` calls ``initialize_port_properties`` which
    looks up ``port_types[self.port_properties["type"]]``. Our fake type
    isn't registered there, so we bypass the parent ``__init__`` entirely
    and set up just the attributes the trace path needs.
    """

    def __init__(self, port_id: str = "FAKE") -> None:
        self.port: object = None
        self.port_ID = port_id
        self._trace_subscribers: list[TraceCallback] = []
        self.port_properties = {  # type: ignore[typeddict-item]
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
        self.raw_writes_log: list[object] = []
        self.next_read: str = ""
        self.next_raw_read: bytes = b""
        self.write_raises: Exception | None = None
        self.read_raises: Exception | None = None

    def write_internal(self, cmd: str) -> None:
        if self.write_raises is not None:
            raise self.write_raises
        self.writes_log.append(cmd)

    def write_raw_internal(self, cmd: object) -> None:
        if self.write_raises is not None:
            raise self.write_raises
        self.raw_writes_log.append(cmd)

    def read_internal(self, digits: int) -> str:
        if self.read_raises is not None:
            raise self.read_raises
        return self.next_read

    def read_raw_internal(self, digits: int) -> bytes:
        if self.read_raises is not None:
            raise self.read_raises
        return self.next_raw_read


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
        raise ValueError("subscriber bug")

    events: list[TraceEvent] = []
    port.subscribe_trace(bad_cb)
    port.subscribe_trace(events.append)

    # write should NOT raise even though the first subscriber does
    port.write("hello")

    assert len(events) == 1
    assert events[0]["payload"] == "hello"


def test_raising_subscriber_is_unsubscribed(port: FakePort) -> None:
    """A subscriber that raises is dropped rather than kept registered.

    Regression: a GUI consumer whose widget had been destroyed stayed
    subscribed and raised on every read and write for the rest of the
    measurement, producing one traceback per I/O in the debug log.
    """
    calls = [0]

    def bad_cb(_event: TraceEvent) -> None:
        calls[0] += 1
        raise RuntimeError("Signal source has been deleted")

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
        raise RuntimeError("boom")

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

    port.write("a")
    port.write("b")
    port.write("c")

    assert len(events) == 3
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
