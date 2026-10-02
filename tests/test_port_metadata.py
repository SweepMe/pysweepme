"""Tests for ``Ports.get_port_metadata`` (Phase 0 identification helpers)."""

from __future__ import annotations

from pysweepme.Ports import get_port_metadata


class TestUSBTMCResourceParsing:
    """``get_port_metadata`` parses VID/PID/serial out of USBTMC resource strings."""

    def test_full_resource_string(self) -> None:
        """Standard USBTMC string yields VID/PID/serial; description/manufacturer stay None."""
        fp = get_port_metadata("USB0::0x05E6::0x2400::1234567::INSTR", "USBTMC")
        assert fp["vid"] == "05E6"
        assert fp["pid"] == "2400"
        assert fp["serial_number"] == "1234567"
        assert fp["description"] is None
        assert fp["manufacturer"] is None

    def test_lowercase_hex_is_uppercased(self) -> None:
        """Lower-case VID/PID hex digits should be normalized to upper-case."""
        fp = get_port_metadata("USB0::0x05e6::0x2a00::SN1::INSTR", "USBTMC")
        assert fp["vid"] == "05E6"
        assert fp["pid"] == "2A00"

    def test_short_hex_is_zero_padded(self) -> None:
        """VID/PID with fewer than 4 hex digits get zero-padded to 4."""
        fp = get_port_metadata("USB0::0x5E6::0x12::SN1::INSTR", "USBTMC")
        assert fp["vid"] == "05E6"
        assert fp["pid"] == "0012"

    def test_usb_alias_for_usbtmc(self) -> None:
        """``"USB"`` should be treated as ``"USBTMC"`` for resource parsing."""
        fp = get_port_metadata("USB0::0x05E6::0x2400::SN::INSTR", "USB")
        assert fp["vid"] == "05E6"
        assert fp["pid"] == "2400"

    def test_malformed_resource_returns_all_none(self) -> None:
        """A USBTMC resource that does not match the regex yields all-None."""
        fp = get_port_metadata("garbage", "USBTMC")
        assert fp == {
            "vid": None,
            "pid": None,
            "serial_number": None,
            "description": None,
            "manufacturer": None,
        }


class TestNonUSBPortTypes:
    """Port types other than COM/USBTMC always return an all-None fingerprint."""

    def test_gpib_returns_all_none(self) -> None:
        """GPIB has no OS-level VID/PID, so metadata is empty."""
        fp = get_port_metadata("GPIB0::24::INSTR", "GPIB")
        assert all(v is None for v in fp.values())

    def test_tcpip_returns_all_none(self) -> None:
        """TCPIP devices have no USB-level VID/PID either."""
        fp = get_port_metadata("TCPIP::192.168.0.1::INSTR", "TCPIP")
        assert all(v is None for v in fp.values())

    def test_socket_returns_all_none(self) -> None:
        """Raw sockets carry no metadata beyond the address."""
        fp = get_port_metadata("127.0.0.1:5025", "SOCKET")
        assert all(v is None for v in fp.values())


class TestCOMUnknownResource:
    """COM lookup for a non-existent port returns all-None, never raises."""

    def test_unknown_com_returns_all_none(self) -> None:
        """``serial.tools.list_ports`` won't find a fake COM port; metadata stays empty."""
        # COM9999 is exceedingly unlikely to exist on the test runner
        fp = get_port_metadata("COM9999", "COM")
        assert fp["vid"] is None
        assert fp["pid"] is None
        assert fp["serial_number"] is None
        assert fp["description"] is None
        assert fp["manufacturer"] is None


class TestFingerprintShape:
    """The returned dict always has the five expected keys."""

    def test_keys_are_stable(self) -> None:
        """Every call returns the same five keys, regardless of port type."""
        expected_keys = {"vid", "pid", "serial_number", "description", "manufacturer"}
        for port_type, resource in [
            ("COM", "COM9999"),
            ("USBTMC", "USB0::0x1::0x2::S::INSTR"),
            ("GPIB", "GPIB0::24::INSTR"),
            ("TCPIP", "TCPIP::192.168.0.1::INSTR"),
            ("UNKNOWN", "garbage"),
        ]:
            fp = get_port_metadata(resource, port_type)
            assert set(fp.keys()) == expected_keys


class _FakeComPort:
    """Stand-in for a pyserial ``ListPortInfo``."""

    def __init__(self, device: str, vid: int, pid: int, serial_number: str) -> None:
        self.device = device
        self.vid = vid
        self.pid = pid
        self.serial_number = serial_number
        self.description = f"USB Serial Device ({device})"
        self.manufacturer = "Example"


class TestCOMMetadataScan:
    """COM metadata comes from one device-tree walk shared by a burst of lookups."""

    @staticmethod
    def _patch_comports(monkeypatch) -> dict:
        import serial.tools.list_ports

        from pysweepme import Ports

        monkeypatch.setattr(Ports, "_comports_cache", None)
        calls = {"scans": 0}

        def fake_comports():
            calls["scans"] += 1
            return [_FakeComPort("COM10", 0x0483, 0x5740, "2071347C4E46"), _FakeComPort("COM5", 0x2341, 0x43, "A1")]

        monkeypatch.setattr(serial.tools.list_ports, "comports", fake_comports)
        return calls

    def test_com_metadata_is_read_from_the_device_tree(self, monkeypatch) -> None:
        self._patch_comports(monkeypatch)
        fp = get_port_metadata("COM10", "COM")
        assert (fp["vid"], fp["pid"], fp["serial_number"]) == ("0483", "5740", "2071347C4E46")

    def test_a_burst_of_lookups_walks_the_tree_once(self, monkeypatch) -> None:
        """REGRESSION: refreshing a list of ports walked the whole device tree once per COM port."""
        calls = self._patch_comports(monkeypatch)
        for resource in ["COM10", "COM5", "COM10", "COM7", "COM5"]:
            get_port_metadata(resource, "COM")
        assert calls["scans"] == 1

    def test_an_old_scan_is_not_reused(self, monkeypatch) -> None:
        from pysweepme import Ports

        calls = self._patch_comports(monkeypatch)
        get_port_metadata("COM10", "COM")
        taken_at, listing = Ports._comports_cache
        Ports._comports_cache = (taken_at - 2 * Ports._COMPORTS_CACHE_SECONDS, listing)

        get_port_metadata("COM10", "COM")

        assert calls["scans"] == 2
