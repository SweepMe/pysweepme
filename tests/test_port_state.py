"""PortManager answers questions about its ports without opening or creating one."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from pysweepme import PortManager as PortManagerModule

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pysweepme.Ports import Port


class _StandInPort:
    """Carries only the 'open' property that the port-state queries look at."""

    def __init__(self, *, is_open: bool) -> None:
        """Create the stand-in as an open or a closed port."""
        self.port_properties = {"open": is_open}


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
