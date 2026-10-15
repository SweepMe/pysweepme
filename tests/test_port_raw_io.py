"""Tests for the raw I/O of the built-in port types (``write_raw``, ``read_raw``, ``read_bytes``) with fake ports."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import create_autospec

import pytest
import pyvisa
from pyvisa.constants import StatusCode

from pysweepme import Ports
from pysweepme.Ports import (
    ASRLport,
    COMport,
    GPIBport,
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
        port.write_raw(b"\x01")


def test_gpib_prologix_raises_not_implemented() -> None:
    """GPIB ports behind a Prologix controller do not support raw I/O and send nothing to the controller."""
    controller = PrologixGPIBcontroller("COM99")
    fake_serial = FakeSerial()
    controller.port = fake_serial  # type: ignore[assignment]
    port = GPIBport("GPIB::5::Prologix@COM99")
    port.port = controller

    with pytest.raises(NotImplementedError, match="PrologixGPIBcontroller"):
        port.write_raw(b"\x01")

    assert fake_serial.written == []


def test_com_raw_write_property_still_appends_eol() -> None:
    """Drivers that send bytes via write() with 'raw_write' keep getting the EOL appended."""
    port, fake_serial = make_com_port()
    port.port_properties["raw_write"] = True

    port.write(b"\xaa\x01")  # type: ignore[arg-type]

    assert fake_serial.written == [b"\xaa\x01\n"]
