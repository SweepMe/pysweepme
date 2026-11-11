"""PortManager answers questions about its ports without opening or creating one, and keeps the ports in use."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from pysweepme import PortManager as PortManagerModule
from pysweepme import Ports

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pysweepme.Ports import Port


class _StandInPort:
    """Carries only the port properties that the port-state queries and the port listing look at."""

    def __init__(self, *, is_open: bool, port_type: str = "COM") -> None:
        """Create the stand-in as an open or a closed port of the given type."""
        self.port_properties = {"open": is_open, "type": port_type, "clear": False}

    def open(self) -> None:
        """Open the port."""
        self.port_properties["open"] = True

    def close(self) -> None:
        """Close the port."""
        self.port_properties["open"] = False

    def get_identification(self) -> str:
        """Answer the identification request, which needs an open port."""
        assert self.port_properties["open"], "identification asked on a closed port"
        return "Maker,Model,123,1.0"


@pytest.fixture
def manager_with_ports() -> Iterator[PortManagerModule.PortManager]:
    """A PortManager that knows COM5 as an open and COM7 as a closed port."""
    manager = PortManagerModule.PortManager()
    saved = dict(manager._ports)
    manager._ports.clear()
    manager._ports["COM5"] = cast("Port", _StandInPort(is_open=True))
    manager._ports["COM7"] = cast("Port", _StandInPort(is_open=False))
    yield manager
    manager._ports.clear()
    manager._ports.update(saved)


def test_is_port_open_reflects_the_port_state(manager_with_ports: PortManagerModule.PortManager) -> None:
    """is_port_open() answers from the cached port, and a port never created is not open."""
    assert manager_with_ports.is_port_open("COM5") is True
    assert manager_with_ports.is_port_open("COM7") is False
    assert manager_with_ports.is_port_open("COM9") is False, "a port never created is not open"


def test_get_cached_port_neither_creates_nor_opens(manager_with_ports: PortManagerModule.PortManager) -> None:
    """get_cached_port() returns a closed port as it is and never creates one."""
    cached = manager_with_ports.get_cached_port("COM7")
    assert cached is not None
    assert cached.port_properties["open"] is False
    assert manager_with_ports.get_cached_port("COM9") is None
    assert "COM9" not in manager_with_ports._ports


def test_listing_resources_keeps_open_ports(
    manager_with_ports: PortManagerModule.PortManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_resources_available() drops the closed ports of the listed types, but never an open one.

    Dropping an open port left its connection open with nothing that could close it any more, so the port stayed
    blocked, for whoever had opened it and for everyone else, until the program ended.
    """
    monkeypatch.setattr(Ports.port_types["COM"], "find_resources", lambda: ["COM5", "COM7"])
    manager_with_ports._ports["GPIB0::8::INSTR"] = cast("Port", _StandInPort(is_open=False, port_type="GPIB"))

    assert manager_with_ports.get_resources_available(["COM"]) == ["COM5", "COM7"]

    assert manager_with_ports.get_cached_port("COM5") is not None, "the open port is kept"
    assert manager_with_ports.get_cached_port("COM7") is None, "a closed port of a listed type is dropped as before"
    assert manager_with_ports.get_cached_port("GPIB0::8::INSTR") is not None, "other port types are left alone"


def test_listing_usb_resources_treats_usbtmc_ports_as_usb(
    manager_with_ports: PortManagerModule.PortManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drivers ask for "USB", and a USBTMC port carries "USBTMC" as its type: both name the same ports.

    The closed ports were compared with the name the driver used, so a closed USBTMC port was never dropped and its
    next use got the old port object instead of a new one.
    """
    monkeypatch.setattr(Ports.port_types["USBTMC"], "find_resources", lambda: ["USB0::1::2::3::INSTR"])
    manager_with_ports._ports["USB0::1::2::3::INSTR"] = cast("Port", _StandInPort(is_open=False, port_type="USBTMC"))
    manager_with_ports._ports["USB0::4::5::6::INSTR"] = cast("Port", _StandInPort(is_open=True, port_type="USBTMC"))

    assert manager_with_ports.get_resources_available(["USB"]) == ["USB0::1::2::3::INSTR"]

    assert manager_with_ports.get_cached_port("USB0::1::2::3::INSTR") is None, "the closed USBTMC port is dropped"
    assert manager_with_ports.get_cached_port("USB0::4::5::6::INSTR") is not None, "the open one is kept"


@pytest.fixture
def resource_manager_closes(monkeypatch: pytest.MonkeyPatch) -> list[None]:
    """Record every closing of the VISA resource manager instead of closing it."""
    closes: list[None] = []
    monkeypatch.setattr(Ports, "close_resourcemanager", lambda: closes.append(None))
    return closes


def test_identifying_a_port_in_use_leaves_it_open(
    manager_with_ports: PortManagerModule.PortManager,
    resource_manager_closes: list[None],
) -> None:
    """A port that is open, e.g. for a driver, is still open after its identification was read.

    The identification closed the port and the VISA resource manager, which ended the VISA session of every open port
    while those ports still counted as open, so their next use failed.
    """
    assert manager_with_ports.get_identification("COM5") == "Maker,Model,123,1.0"

    assert manager_with_ports.is_port_open("COM5") is True
    assert resource_manager_closes == [], "closing the manager would end the sessions of the open ports"


def test_identifying_a_closed_port_closes_it_again(
    manager_with_ports: PortManagerModule.PortManager,
    resource_manager_closes: list[None],
) -> None:
    """A port opened only for the identification is closed again, the resource manager is left open."""
    assert manager_with_ports.get_identification("COM7") == "Maker,Model,123,1.0"

    assert manager_with_ports.is_port_open("COM7") is False
    assert resource_manager_closes == []


def test_identifying_a_new_port_closes_it_again(
    manager_with_ports: PortManagerModule.PortManager,
    monkeypatch: pytest.MonkeyPatch,
    resource_manager_closes: list[None],
) -> None:
    """A port created for the identification, which opens it, is closed again."""
    monkeypatch.setattr(Ports, "get_port", lambda _resource: _StandInPort(is_open=True))
    monkeypatch.setattr(PortManagerModule, "Port", _StandInPort)  # get_identification only accepts Port objects

    assert manager_with_ports.get_identification("COM9") == "Maker,Model,123,1.0"

    assert manager_with_ports.is_port_open("COM9") is False
    assert resource_manager_closes == []
