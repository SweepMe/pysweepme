"""PortManager.try_identify must treat a port that cannot be opened as an expected outcome, not an error.

Identification probes resources that may well not be there — VISA lists configured addresses whether or not anything
is connected — so failing to open one is normal. get_port reports every failure with a full traceback, which put one
traceback into the debug log for each absent port whenever SweepMe!'s "Identify all" ran.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, cast

import pytest

from pysweepme import PortManager as PortManagerModule
from pysweepme import Ports

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pysweepme.Ports import Port

_ABSENT = "GPIB0::99::INSTR"

Logged = dict[str, list[tuple[object, ...]]]


@pytest.fixture
def manager_with_absent_port(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[PortManagerModule.PortManager, Logged]]:
    """A PortManager whose every port fails to open, with error/debug logging recorded."""
    logged: Logged = {"error": [], "debug": []}
    monkeypatch.setattr(PortManagerModule, "error", lambda *args, **_kw: logged["error"].append(args))
    monkeypatch.setattr(PortManagerModule, "debug", lambda *args, **_kw: logged["debug"].append(args))

    def _cannot_open(resource: str, _properties: object = None) -> NoReturn:
        msg = f"{resource} is not present in the system"
        raise OSError(msg)

    monkeypatch.setattr(Ports, "get_port", _cannot_open)
    manager = PortManagerModule.PortManager()
    yield manager, logged
    manager._ports.pop(_ABSENT, None)


def test_try_identify_is_silent_for_a_port_that_cannot_be_opened(
    manager_with_absent_port: tuple[PortManagerModule.PortManager, Logged],
) -> None:
    """An absent port gives no identification, no error and no cached port."""
    manager, logged = manager_with_absent_port

    assert manager.try_identify(_ABSENT, "GPIB") is None
    assert logged["error"] == [], "an absent port is not an error during identification"
    assert _ABSENT not in manager._ports


def test_get_port_still_reports_failures_by_default(
    manager_with_absent_port: tuple[PortManagerModule.PortManager, Logged],
) -> None:
    """Drivers rely on get_port explaining why their port could not be opened."""
    manager, logged = manager_with_absent_port

    assert manager.get_port(_ABSENT) is False
    assert len(logged["error"]) == 1


def test_get_port_can_be_asked_not_to_log(
    manager_with_absent_port: tuple[PortManagerModule.PortManager, Logged],
) -> None:
    """With log_errors=False, a port that cannot be opened is only reported by the return value."""
    manager, logged = manager_with_absent_port

    assert manager.get_port(_ABSENT, log_errors=False) is False
    assert logged["error"] == []


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


def test_open_ports_lists_only_open_ones(manager_with_ports: PortManagerModule.PortManager) -> None:
    """open_ports() leaves out cached ports that are closed."""
    assert manager_with_ports.open_ports() == ["COM5"]


def test_get_cached_port_neither_creates_nor_opens(manager_with_ports: PortManagerModule.PortManager) -> None:
    """get_cached_port() returns a closed port as it is and never creates one."""
    cached = manager_with_ports.get_cached_port("COM7")
    assert cached is not None
    assert cached.port_properties["open"] is False
    assert manager_with_ports.get_cached_port("COM9") is None
    assert "COM9" not in manager_with_ports._ports


def test_try_identify_skips_a_port_in_use(manager_with_ports: PortManagerModule.PortManager) -> None:
    """An open port belongs to a running driver; identification must not touch it."""
    assert manager_with_ports.try_identify("COM5", "COM") is None
