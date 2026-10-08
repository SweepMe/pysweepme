"""PortManager.try_identify must treat a port that cannot be opened as an expected outcome, not an error.

Identification probes resources that may well not be there — VISA lists configured addresses whether or not anything
is connected — so failing to open one is normal. get_port reports every failure with a full traceback, which put one
traceback into the debug log for each absent port whenever SweepMe!'s "Identify all" ran.
"""

from __future__ import annotations

import pytest

from pysweepme import PortManager as port_manager_module
from pysweepme import Ports

_ABSENT = "GPIB0::99::INSTR"


@pytest.fixture
def manager_with_absent_port(monkeypatch):
    """A PortManager whose every port fails to open, with error/debug logging recorded."""
    logged: dict[str, list[tuple]] = {"error": [], "debug": []}
    monkeypatch.setattr(port_manager_module, "error", lambda *args, **_kw: logged["error"].append(args))
    monkeypatch.setattr(port_manager_module, "debug", lambda *args, **_kw: logged["debug"].append(args))

    def _cannot_open(resource, properties=None):
        msg = f"{resource} is not present in the system"
        raise OSError(msg)

    monkeypatch.setattr(Ports, "get_port", _cannot_open)
    manager = port_manager_module.PortManager()
    yield manager, logged
    manager._ports.pop(_ABSENT, None)


def test_try_identify_is_silent_for_a_port_that_cannot_be_opened(manager_with_absent_port) -> None:
    manager, logged = manager_with_absent_port

    assert manager.try_identify(_ABSENT, "GPIB") is None
    assert logged["error"] == [], "an absent port is not an error during identification"
    assert _ABSENT not in manager._ports


def test_get_port_still_reports_failures_by_default(manager_with_absent_port) -> None:
    """Drivers rely on get_port explaining why their port could not be opened."""
    manager, logged = manager_with_absent_port

    assert manager.get_port(_ABSENT) is False
    assert len(logged["error"]) == 1


def test_get_port_can_be_asked_not_to_log(manager_with_absent_port) -> None:
    manager, logged = manager_with_absent_port

    assert manager.get_port(_ABSENT, log_errors=False) is False
    assert logged["error"] == []


class _StandInPort:
    def __init__(self, is_open: bool) -> None:
        self.port_properties = {"open": is_open}


@pytest.fixture
def manager_with_ports():
    manager = port_manager_module.PortManager()
    saved = dict(manager._ports)
    manager._ports.clear()
    manager._ports["COM5"] = _StandInPort(is_open=True)
    manager._ports["COM7"] = _StandInPort(is_open=False)
    yield manager
    manager._ports.clear()
    manager._ports.update(saved)


def test_is_port_open_reflects_the_port_state(manager_with_ports) -> None:
    assert manager_with_ports.is_port_open("COM5") is True
    assert manager_with_ports.is_port_open("COM7") is False
    assert manager_with_ports.is_port_open("COM9") is False, "a port never created is not open"


def test_open_ports_lists_only_open_ones(manager_with_ports) -> None:
    assert manager_with_ports.open_ports() == ["COM5"]


def test_get_cached_port_neither_creates_nor_opens(manager_with_ports) -> None:
    assert manager_with_ports.get_cached_port("COM7").port_properties["open"] is False
    assert manager_with_ports.get_cached_port("COM9") is None
    assert "COM9" not in manager_with_ports._ports


def test_try_identify_skips_a_port_in_use(manager_with_ports) -> None:
    """An open port belongs to a running driver; identification must not touch it."""
    assert manager_with_ports.try_identify("COM5", "COM") is None
