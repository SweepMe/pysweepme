"""Tests for the raw I/O of the built-in port types (``write_raw``, ``read_raw``, ``read_bytes``) with fake ports."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import create_autospec

import pytest
import pyvisa
import serial
from pyvisa.constants import StatusCode

from pysweepme import Ports
from pysweepme.Ports import (
    ASRLport,
    COMport,
    GPIBport,
    IncompleteMessageError,
    Port,
    PrologixGPIBcontroller,
    PXIport,
    SOCKETport,
    TCPIPport,
    USBTMCport,
    VISAport,
)

if TYPE_CHECKING:
    from collections.abc import Callable

VISA_PORTS: dict[str, tuple[type[VISAport], str]] = {
    "GPIB": (GPIBport, "GPIB0::22::INSTR"),
    "PXI": (PXIport, "PXI0::2-11.0::INSTR"),
    "ASRL": (ASRLport, "ASRL3::INSTR"),
    "USBTMC": (USBTMCport, "USB0::0x0957::0x1796::MY1234::INSTR"),
    "TCPIP": (TCPIPport, "TCPIP0::192.168.0.10::inst0::INSTR"),
}
ALL_PORTS = [*VISA_PORTS, "SOCKET", "COM"]


class FakeVisaLib:
    """Stands in for the VISA library of a resource: ``read`` serves queued messages like viRead with END."""

    def __init__(self) -> None:
        """Start without messages, so that reading times out."""
        self.messages: list[bytes] = []
        self.error_code: int | None = None

    def read(self, _session: int, count: int) -> tuple[bytes, StatusCode]:
        """Return up to count bytes of the next message, whose last bytes come with END, or raise an error."""
        if self.error_code is not None:
            raise pyvisa.errors.VisaIOError(self.error_code)
        if not self.messages:
            raise pyvisa.errors.VisaIOError(StatusCode.error_timeout)
        message = self.messages.pop(0)
        if len(message) > count:
            self.messages.insert(0, message[count:])
            return message[:count], StatusCode.success_max_count_read
        return message, StatusCode.success


class FakeSocket:
    """Stands in for a connected ``socket.socket``: ``recv`` serves queued chunks, ``sendall`` records the data."""

    def __init__(self, chunks: list[bytes]) -> None:
        """Queue the chunks that the peer sends."""
        self.chunks = list(chunks)
        self.sent: list[bytes] = []

    def recv(self, bufsize: int) -> bytes:
        """Return the next chunk, at most bufsize bytes, or time out like a socket with a timeout."""
        if not self.chunks:
            time.sleep(0.001)
            msg = "timed out"
            raise TimeoutError(msg)
        chunk = self.chunks.pop(0)
        if len(chunk) > bufsize:
            self.chunks.insert(0, chunk[bufsize:])
            chunk = chunk[:bufsize]
        return chunk

    def sendall(self, data: bytes) -> None:
        """Record the sent data."""
        self.sent.append(data)


class FakeSerial:
    """Stands in for an open ``serial.Serial``: ``read`` serves queued bytes, ``write`` records the data."""

    def __init__(self, data: bytes = b"") -> None:
        """Queue the bytes that the instrument sends."""
        self.data = bytearray(data)
        self.written: list[bytes] = []
        self.read_error: Exception | None = None

    def read(self, size: int = 1) -> bytes:
        """Return up to size bytes; like pyserial at a timeout, fewer bytes if no more arrive."""
        if self.read_error is not None:
            raise self.read_error
        chunk = bytes(self.data[: max(size, 0)])
        del self.data[: len(chunk)]
        return chunk

    def write(self, data: bytes) -> int:
        """Record the written data."""
        self.written.append(bytes(data))
        return len(data)


class CustomPort(Port):
    """A port class from outside pysweepme that implements only text I/O."""

    def __init__(self) -> None:
        """Set up the port without Port.__init__, which needs a registered port type."""
        self.port = None
        self.port_ID = "CUSTOM"
        self.port_properties = {"type": "Custom", "ID": "CUSTOM", "debug": False}
        self.written: list[str] = []

    def write_internal(self, cmd: str) -> None:
        """Record the written command."""
        self.written.append(cmd)


@pytest.fixture(autouse=True)
def asrl_port_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register ASRL, which is commented out in ``port_types``, so that ``ASRLport`` can be created."""
    monkeypatch.setitem(Ports.port_types, "ASRL", Ports.ASRL())


@pytest.fixture
def debug_lines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collect the debug messages of the ports."""
    lines: list[str] = []
    monkeypatch.setattr(Ports, "debug", lines.append)
    return lines


def make_visa_port(kind: str, resource_class: type = pyvisa.resources.MessageBasedResource) -> tuple[VISAport, Any]:
    """Create a VISA port whose port object is a fake pyvisa resource that checks the call signatures.

    Messages for read_bytes() are queued in ``resource.visalib.messages``.
    """
    port_class, port_id = VISA_PORTS[kind]
    resource = create_autospec(resource_class, instance=True)
    resource.visalib = FakeVisaLib()
    resource.session = 1
    resource.chunk_size = 20 * 1024
    resource.ignore_warning.return_value = contextlib.nullcontext()
    port = port_class(port_id)
    port.port = resource
    return port, resource


def make_socket_port(chunks: list[bytes], read_termination: str = "\n") -> tuple[SOCKETport, FakeSocket]:
    """Create a SOCKET port whose socket is fake."""
    fake_socket = FakeSocket(chunks)
    port = SOCKETport("192.168.0.10:5025")
    port.port = fake_socket  # type: ignore[assignment]
    port.read_termination = read_termination
    port.write_termination = "\n"
    port.port_properties["timeout"] = 0.05
    return port, fake_socket


def make_com_port(data: bytes = b"") -> tuple[COMport, FakeSerial]:
    """Create a COM port whose serial port is fake."""
    fake_serial = FakeSerial(data)
    port = COMport("COM99")
    port.port = fake_serial  # type: ignore[assignment]
    return port, fake_serial


def make_port(kind: str) -> tuple[Port, Callable[[], list[bytes]]]:
    """Create a port of any kind and a function that returns the bytes it has sent so far."""
    if kind == "SOCKET":
        socket_port, fake_socket = make_socket_port([])
        return socket_port, lambda: fake_socket.sent
    if kind == "COM":
        com_port, fake_serial = make_com_port()
        return com_port, lambda: fake_serial.written
    visa_port, resource = make_visa_port(kind)
    return visa_port, lambda: [call.args[0] for call in resource.write_raw.call_args_list]


@pytest.mark.parametrize("kind", ALL_PORTS)
def test_write_raw_sends_bytes_unchanged_without_terminator(kind: str) -> None:
    """Every port type sends the bytes as they are, without encoding them or appending a terminator."""
    port, sent = make_port(kind)

    port.write_raw(b"\x01\x02\r\n")

    assert sent() == [b"\x01\x02\r\n"]


@pytest.mark.parametrize("kind", ALL_PORTS)
def test_write_raw_rejects_str(kind: str) -> None:
    """A str raises a TypeError on every port type, as it did on COM ports, instead of guessing an encoding."""
    port, sent = make_port(kind)

    with pytest.raises(TypeError, match="does not accept str"):
        port.write_raw("*RST")  # type: ignore[arg-type]

    assert sent() == []


@pytest.mark.parametrize("kind", ALL_PORTS)
@pytest.mark.parametrize("cmd", [bytearray(b"\x01\x02\r\n"), memoryview(b"\x01\x02\r\n")])
def test_write_raw_converts_bytes_like_objects_to_bytes(kind: str, cmd: bytearray | memoryview) -> None:
    """A bytearray or memoryview reaches every port type as bytes, which e.g. NI-VISA requires."""
    port, sent = make_port(kind)

    port.write_raw(cmd)

    assert sent() == [b"\x01\x02\r\n"]
    assert type(sent()[0]) is bytes


@pytest.mark.parametrize("kind", ALL_PORTS)
@pytest.mark.parametrize(("cmd", "type_name"), [([1, 2], "list"), (5, "int"), (None, "NoneType")])
def test_write_raw_rejects_other_types(kind: str, cmd: object, type_name: str) -> None:
    """Anything but bytes, bytearray or memoryview raises a TypeError that names the type, on every port type."""
    port, sent = make_port(kind)

    with pytest.raises(TypeError, match=f"does not accept {type_name}"):
        port.write_raw(cmd)  # type: ignore[arg-type]

    assert sent() == []


@pytest.mark.parametrize("kind", ALL_PORTS)
@pytest.mark.parametrize("cmd", [b"", bytearray(), memoryview(b"")])
def test_write_raw_skips_empty_bytes(kind: str, cmd: bytes | bytearray | memoryview) -> None:
    """Empty commands are skipped like in write()."""
    port, sent = make_port(kind)

    port.write_raw(cmd)

    assert sent() == []


def test_base_port_write_raw_raises_instead_of_falling_back_to_write() -> None:
    """A port class without write_raw_internal() no longer sends the bytes through write_internal()."""
    port = CustomPort()

    with pytest.raises(NotImplementedError, match="write_raw_internal"):
        port.write_raw(b"\x01")

    assert port.written == []


def test_base_port_read_raw_raises_not_implemented() -> None:
    """A port class without read_raw_internal() raises a NotImplementedError."""
    with pytest.raises(NotImplementedError, match="read_raw_internal"):
        CustomPort().read_raw()


def test_base_port_read_bytes_raises_not_implemented() -> None:
    """A port class without read_bytes_internal() raises a NotImplementedError."""
    with pytest.raises(NotImplementedError, match="read_bytes_internal"):
        CustomPort().read_bytes(4)


@pytest.mark.parametrize("count", [0, -1])
def test_read_bytes_without_positive_count_reads_nothing(count: int) -> None:
    """Like pyvisa, read_bytes() returns no bytes for count <= 0, without reading from the port."""
    port, fake_serial = make_com_port(b"\x01")

    assert port.read_bytes(count) == b""
    assert fake_serial.data == b"\x01"


def test_incomplete_message_error_shows_received_bytes() -> None:
    """The error is a TimeoutError, keeps the received bytes and shows them in its message."""
    count = 8
    error = IncompleteMessageError("COM99", b"\x01\x02", count)

    assert isinstance(error, TimeoutError)
    assert error.received == b"\x01\x02"
    assert error.count == count
    assert str(error) == "Incomplete message from port COM99: received 2 of 8 bytes before the timeout: b'\\x01\\x02'"


def test_incomplete_message_error_shortens_long_received_bytes() -> None:
    """Long received bytes are shortened in the message, but kept completely in the error."""
    received = bytes(300)
    error = IncompleteMessageError("COM99", received, 400)

    assert error.received == received
    assert str(error).endswith(f"{bytes(256)!r} ... (300 bytes in total)")


@pytest.mark.parametrize("kind", list(VISA_PORTS))
def test_visa_read_raw_reads_one_message(kind: str) -> None:
    """read_raw() reads one message with pyvisa's read_raw() and keeps the read termination."""
    port, resource = make_visa_port(kind)
    resource.read_raw.return_value = b"#14\x01\x02\x03\x04\n"

    assert port.read_raw() == b"#14\x01\x02\x03\x04\n"
    resource.read_raw.assert_called_once_with()


@pytest.mark.parametrize("kind", list(VISA_PORTS))
def test_visa_read_raw_with_digits_reads_bytes(kind: str) -> None:
    """read_raw(digits), kept for existing drivers, reads digits bytes like read_bytes()."""
    port, resource = make_visa_port(kind)
    resource.visalib.messages = [b"\x00\n\x01\x02\x03"]

    assert port.read_raw(4) == b"\x00\n\x01\x02"
    resource.read_raw.assert_not_called()


@pytest.mark.parametrize("kind", list(VISA_PORTS))
def test_visa_read_bytes_reads_exact_byte_count(kind: str) -> None:
    """read_bytes() reads exactly count bytes and leaves the rest of the message for the next read."""
    port, resource = make_visa_port(kind)
    resource.visalib.messages = [b"\x00\n\x01\x02\x03"]

    assert port.read_bytes(4) == b"\x00\n\x01\x02"
    assert resource.visalib.messages == [b"\x03"]


def test_visa_read_bytes_continues_after_end_of_message() -> None:
    """Without break_on_termchar, read_bytes() reads on into the next message, like pyvisa."""
    port, resource = make_visa_port("GPIB")
    resource.visalib.messages = [b"\x00\x01", b"\x02\x03"]

    assert port.read_bytes(4) == b"\x00\x01\x02\x03"


def test_visa_read_bytes_with_break_on_termchar_stops_at_end_of_message() -> None:
    """With break_on_termchar, read_bytes() stops at the end of a message, even before count bytes."""
    port, resource = make_visa_port("GPIB")
    resource.visalib.messages = [b"1.5\n", b"2.5\n"]

    assert port.read_bytes(8, break_on_termchar=True) == b"1.5\n"
    assert resource.visalib.messages == [b"2.5\n"]


@pytest.mark.parametrize("kind", list(VISA_PORTS))
def test_visa_read_bytes_raises_incomplete_message_with_received_bytes(kind: str) -> None:
    """At a timeout, the bytes of completed low-level reads are passed to the IncompleteMessageError."""
    port, resource = make_visa_port(kind)
    resource.visalib.messages = [b"\x01\x02"]

    with pytest.raises(IncompleteMessageError, match=r"received 2 of 8 bytes") as excinfo:
        port.read_bytes(8)

    assert excinfo.value.received == b"\x01\x02"
    assert isinstance(excinfo.value.__cause__, pyvisa.errors.VisaIOError)


def test_visa_read_bytes_passes_other_visa_errors() -> None:
    """VISA errors other than a timeout reach the caller unchanged."""
    port, resource = make_visa_port("TCPIP")
    resource.visalib.error_code = StatusCode.error_connection_lost

    with pytest.raises(pyvisa.errors.VisaIOError) as excinfo:
        port.read_bytes(4)

    assert not isinstance(excinfo.value, IncompleteMessageError)


@pytest.mark.parametrize("kind", ["ASRL", "TCPIP"])
def test_visa_write_raw_waits_for_delay_like_write(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw writes keep the delay after writing of the port types that have one."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    port, sent = make_port(kind)
    port.port_properties["delay"] = 0.25

    port.write_raw(b"\x01")

    assert sent() == [b"\x01"]
    assert sleeps == [0.25]


def test_pxi_register_based_resource_raises_not_implemented() -> None:
    """PXI INSTR resources are register-based in pyvisa and have no message-based raw I/O."""
    port, _ = make_visa_port("PXI", pyvisa.resources.PXIInstrument)

    with pytest.raises(NotImplementedError, match="does not provide message-based VISA I/O"):
        port.read_raw()
    with pytest.raises(NotImplementedError, match="does not provide message-based VISA I/O"):
        port.read_bytes(4)
    with pytest.raises(NotImplementedError, match="does not provide message-based VISA I/O"):
        port.write_raw(b"\x01")


def test_gpib_prologix_raises_not_implemented() -> None:
    """GPIB ports behind a Prologix controller do not support raw I/O and send nothing to the controller."""
    controller = PrologixGPIBcontroller("COM99")
    fake_serial = FakeSerial()
    controller.port = fake_serial  # type: ignore[assignment]
    port = GPIBport("GPIB::5::Prologix@COM99")
    port.port = controller

    with pytest.raises(NotImplementedError, match="PrologixGPIBcontroller"):
        port.read_raw()
    with pytest.raises(NotImplementedError, match="PrologixGPIBcontroller"):
        port.read_bytes(4)
    with pytest.raises(NotImplementedError, match="PrologixGPIBcontroller"):
        port.write_raw(b"\x01")

    assert fake_serial.written == []


def test_socket_read_raw_reads_one_message() -> None:
    """read_raw() reads up to and including the read termination and shares the buffer with read()."""
    port, _ = make_socket_port([b"1.5\n2.5\n"])

    assert port.read_raw() == b"1.5\n"
    assert port.read() == "2.5"


def test_socket_read_raw_without_read_termination_raises_timeout() -> None:
    """Without read termination, a stream socket has no message boundary, so a message cannot be read."""
    port, _ = make_socket_port([b"\x00\x01"], read_termination="")

    with pytest.raises(TimeoutError):
        port.read_raw()


def test_socket_read_raw_with_digits_reads_bytes() -> None:
    """read_raw(digits), kept for existing drivers, reads digits bytes like read_bytes()."""
    port, _ = make_socket_port([b"\x00\n\x01\x02\x03"])

    assert port.read_raw(4) == b"\x00\n\x01\x02"


def test_socket_read_bytes_reads_exact_byte_count() -> None:
    """read_bytes() collects exactly count bytes across chunks, even if they contain the read termination."""
    port, _ = make_socket_port([b"\x00\n\x01", b"\x02\x03"])

    assert port.read_bytes(4) == b"\x00\n\x01\x02"
    assert port.read_bytes(1) == b"\x03"


def test_socket_read_bytes_with_break_on_termchar_stops_after_read_termination() -> None:
    """With break_on_termchar, read_bytes() stops after the read termination, even before count bytes."""
    port, _ = make_socket_port([b"ab\ncd"])

    assert port.read_bytes(5, break_on_termchar=True) == b"ab\n"
    assert port.read_bytes(2) == b"cd"


def test_socket_read_bytes_raises_incomplete_message_with_received_bytes() -> None:
    """At a timeout, the received bytes are taken from the buffer and passed to the IncompleteMessageError."""
    port, _ = make_socket_port([b"\x00\x01"])

    with pytest.raises(IncompleteMessageError, match=r"received 2 of 4 bytes") as excinfo:
        port.read_bytes(4)

    assert excinfo.value.received == b"\x00\x01"
    assert port.buffer == b""


def test_socket_read_still_returns_the_shorter_of_termination_and_digits() -> None:
    """read() keeps stopping at the read termination before the number of digits is reached."""
    port, _ = make_socket_port([b"ab\ncdef"])

    assert port.read(5) == "ab"
    assert port.read(3) == "cde"


def test_com_read_raw_reads_one_message() -> None:
    """read_raw() reads up to and including the EOL."""
    port, fake_serial = make_com_port(b"\x01\x02\n\x03")

    assert port.read_raw() == b"\x01\x02\n"
    assert fake_serial.data == b"\x03"


def test_com_read_raw_uses_eol_read() -> None:
    """'EOLread' takes precedence over 'EOL' like in read()."""
    port, _ = make_com_port(b"\x01\n\x02\r\n")
    port.port_properties["EOLread"] = "\r\n"

    assert port.read_raw() == b"\x01\n\x02\r\n"


def test_com_read_raw_raises_timeout_if_eol_does_not_arrive() -> None:
    """A message without EOL raises a TimeoutError that shows the bytes received so far."""
    port, _ = make_com_port(b"abc")

    with pytest.raises(TimeoutError, match="no EOL within the timeout: b'abc'"):
        port.read_raw()


def test_com_read_raw_with_digits_reads_bytes() -> None:
    """read_raw(digits), kept for existing drivers, reads digits bytes like read_bytes()."""
    port, fake_serial = make_com_port(b"\x00\n\x01\x02\x03")

    assert port.read_raw(4) == b"\x00\n\x01\x02"
    assert fake_serial.data == b"\x03"


def test_com_read_raw_with_digits_raises_incomplete_message_on_short_read() -> None:
    """read_raw(digits) no longer returns a short read at the timeout, which e.g. JUMO_diraTRON did rely on."""
    port, _ = make_com_port(b"\x01\x10\x21\x14\x00\x02\x4b\xf2")

    with pytest.raises(IncompleteMessageError, match=r"received 8 of 32 bytes") as excinfo:
        port.read_raw(32)

    assert excinfo.value.received == b"\x01\x10\x21\x14\x00\x02\x4b\xf2"


def test_com_read_bytes_reads_exact_byte_count() -> None:
    """read_bytes() reads count bytes, even if they contain the EOL."""
    port, fake_serial = make_com_port(b"\x00\n\x01\x02\x03")

    assert port.read_bytes(4) == b"\x00\n\x01\x02"
    assert fake_serial.data == b"\x03"


def test_com_read_bytes_raises_incomplete_message_with_received_bytes() -> None:
    """A short read raises an IncompleteMessageError that shows the bytes received so far."""
    port, _ = make_com_port(b"\x01\x90\x02")

    with pytest.raises(IncompleteMessageError, match=r"received 3 of 8 bytes before the timeout: b'\\x01\\x90\\x02'"):
        port.read_bytes(8)


def test_com_read_bytes_with_break_on_termchar_stops_after_eol() -> None:
    """With break_on_termchar, read_bytes() stops after the EOL, even before count bytes."""
    port, fake_serial = make_com_port(b"\x01\x02\n\x03")

    assert port.read_bytes(8, break_on_termchar=True) == b"\x01\x02\n"
    assert fake_serial.data == b"\x03"


def test_com_read_bytes_with_break_on_termchar_stops_after_count() -> None:
    """With break_on_termchar, read_bytes() still stops after count bytes if the EOL comes later."""
    port, fake_serial = make_com_port(b"abcdef\n")

    assert port.read_bytes(3, break_on_termchar=True) == b"abc"
    assert fake_serial.data == b"def\n"


def test_com_read_bytes_with_break_on_termchar_raises_incomplete_message() -> None:
    """Without EOL and fewer than count bytes, read_bytes() raises an IncompleteMessageError."""
    port, _ = make_com_port(b"ab")

    with pytest.raises(IncompleteMessageError, match="received 2 of 8 bytes and no end of message") as excinfo:
        port.read_bytes(8, break_on_termchar=True)

    assert excinfo.value.received == b"ab"


def test_com_read_bytes_propagates_serial_errors() -> None:
    """Errors of the serial port reach the caller."""
    port, fake_serial = make_com_port()
    fake_serial.read_error = serial.SerialException("device disconnected")

    with pytest.raises(serial.SerialException):
        port.read_bytes(4)


@pytest.mark.parametrize(
    ("data", "eol", "expected"),
    [
        (b"\x01\x02\r\n\x03", "\r\n", (b"\x01\x02", True)),
        (b"\n\x01", "\n", (b"", True)),
        (b"abc", "\n", (b"ab", False)),
        (b"abc", "", (b"", False)),
    ],
)
def test_com_readline_is_unchanged(data: bytes, eol: str, expected: tuple[bytes, bool]) -> None:
    """readline(), which read() uses, still removes the EOL and reports whether it arrived."""
    port, _ = make_com_port(data)
    port.port_properties["EOL"] = eol

    assert port.readline() == expected


@pytest.mark.parametrize("raw_property", [False, True])
def test_com_raw_io_ignores_and_keeps_raw_properties(raw_property: bool) -> None:  # noqa: FBT001
    """'raw_read' and 'raw_write' only affect read() and write(); raw I/O neither uses nor changes them."""
    port, fake_serial = make_com_port(b"\x01\x02\n\x03")
    port.port_properties["raw_read"] = raw_property
    port.port_properties["raw_write"] = raw_property

    port.write_raw(b"\xaa")

    assert port.read_raw() == b"\x01\x02\n"
    assert port.read_bytes(1) == b"\x03"
    assert fake_serial.written == [b"\xaa"]
    assert port.port_properties["raw_read"] is raw_property
    assert port.port_properties["raw_write"] is raw_property


def test_com_raw_write_property_still_appends_eol() -> None:
    """Drivers that send bytes via write() with 'raw_write' keep getting the EOL appended."""
    port, fake_serial = make_com_port()
    port.port_properties["raw_write"] = True

    port.write(b"\xaa\x01")  # type: ignore[arg-type]

    assert fake_serial.written == [b"\xaa\x01\n"]


def test_com_raw_io_logs_each_call_once(debug_lines: list[str]) -> None:
    """Raw I/O is logged once per call now that COM no longer goes through write() and read()."""
    port, _ = make_com_port(b"\x01\x02\n\x03")
    port.port_properties["debug"] = True

    port.write_raw(b"\xaa")
    port.read_raw()
    port.read_bytes(1)

    assert debug_lines == [
        "COM99 write_raw: b'\\xaa'",
        "COM99 read_raw: b'\\x01\\x02\\n'",
        "COM99 read_bytes: b'\\x03'",
    ]


def test_visa_raw_io_logs_each_call_once(debug_lines: list[str]) -> None:
    """VISA ports log raw I/O like write() and read()."""
    port, resource = make_visa_port("USBTMC")
    port.port_properties["debug"] = True
    resource.read_raw.return_value = b"1\n"
    resource.visalib.messages = [b"\x00"]

    port.write_raw(b"*IDN?\n")
    port.read_raw()
    port.read_bytes(1)

    port_id = VISA_PORTS["USBTMC"][1]
    assert debug_lines == [
        f"{port_id} write_raw: b'*IDN?\\n'",
        f"{port_id} read_raw: b'1\\n'",
        f"{port_id} read_bytes: b'\\x00'",
    ]
