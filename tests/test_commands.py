"""Tests of the communication command API: markers, @command and its argument check, describe_commands."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import textwrap
from typing import TYPE_CHECKING, Annotated, Literal

import pytest

from pysweepme import Label, Range, Unit, command, describe_commands
from pysweepme.commands import COMMAND_ATTRIBUTE, CommandInfo, command_info, derived_label, description_of
from pysweepme.EmptyDeviceClass import EmptyDevice

if TYPE_CHECKING:
    from pathlib import Path

    from pysweepme.commands import CommandSpec

Volts = Annotated[float, Unit("V")]
Amperes = Annotated[float, Unit("A")]
RfPower = Annotated[float, Unit("dBm"), Label("RF power")]
SourceMode = Literal["FVMI", "FIMV"]


class Declared(EmptyDevice):
    """A driver that declares its commands with @command."""

    def __init__(self) -> None:
        """Remember what the commands were called with."""
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    @command
    def set_voltage(self, channel: int, voltage: Annotated[Volts, Range(-20.0, 20.0)]) -> None:
        """Set the output voltage."""
        self.calls.append(("set_voltage", (channel, voltage)))

    @command(hazards="FIMV with no load drives the output to compliance.")
    def set_source_mode(self, channel: int, mode: SourceMode) -> None:
        """Set the source mode."""
        self.calls.append(("set_source_mode", (channel, mode)))

    @command
    def set_output(self, channel: int, state: bool) -> None:  # noqa: FBT001  # a command takes its value positionally
        """Switch the output."""
        self.calls.append(("set_output", (channel, state)))

    @command
    def set_points(self, channel: int, points: Annotated[int, Range(1, None)]) -> None:
        """Set the number of points."""
        self.calls.append(("set_points", (channel, points)))

    @command
    def set_offset(self, channel: int, offset: float | None = None) -> None:
        """Set an offset, or none."""
        self.calls.append(("set_offset", (channel, offset)))

    @command(returns=("voltage", "current"))
    def get_voltage_and_current(self, channel: int) -> tuple[Volts, Amperes]:  # noqa: ARG002  # a test stub
        """Measure voltage and current."""
        return (1.0, 0.001)

    @command(returns=("voltage",), reads="setpoint")
    def get_level(self, channel: int) -> Volts:  # noqa: ARG002  # a test stub
        """Read back the voltage setpoint."""
        return 1.0

    @command(returns=("rf_power",))
    def get_rf_power(self) -> RfPower:
        """Measure the RF power."""
        return -10.0

    @command(returns=("current",), reads="last")
    def fetch_current(self, channel: int) -> Amperes:  # noqa: ARG002  # a test stub
        """Return the last measured current."""
        return 0.001

    @command(returns=("status",), reads="state")
    def get_status(self) -> str:
        """Read the instrument's status."""
        return "IDLE"

    @command(returns=("temperature",))
    def fetch_temperature(self) -> float:
        """Named like a fetch, but declared without reads: a measurement, nothing is guessed from the name."""
        return 21.0

    @command(composite=True)
    def sweep_voltage(self, channel: int, start: Volts, stop: Volts) -> None:
        """Sweep the voltage from start to stop."""

    @command(
        hazards=(
            "Re-enumerates the USB device: the open port is lost.",
            "Resets every setting, also those the driver promised to keep.",
        ),
    )
    def reset(self) -> None:
        """Reset the instrument.

        A longer explanation of the reset.
        """

    def helper(self) -> str:
        """An undecorated public method: callable, but not a command."""
        return "helper"


class Undeclared(EmptyDevice):
    """An older driver without @command: every own public method is a command."""

    def set_voltage(self, voltage):  # noqa: ANN001, ANN201  # an old driver without type hints
        """Set the voltage."""
        return voltage

    def get_voltage_and_current(self) -> tuple[float, float]:
        """Measure voltage and current."""
        return (1.0, 0.001)


class Inherited(Declared):
    """A driver that inherits decorated commands and adds an undecorated method."""

    def extra(self) -> None:
        """Undecorated in a converted driver: not a command."""


def spec_of(device: EmptyDevice, name: str) -> CommandSpec:
    """The description of one command."""
    return next(spec for spec in describe_commands(device) if spec.name == name)


# --- markers -------------------------------------------------------------------------------------------------------


def test_range_bounds() -> None:
    """A range is inclusive, open sides are allowed, NaN is never inside, minimum above maximum is refused."""
    assert Range(-1, 1).contains(-1)
    assert Range(-1, 1).contains(1)
    assert not Range(-1, 1).contains(1.0001)
    assert Range(0, None).contains(1e12)
    assert not Range(0, None).contains(float("nan"))
    with pytest.raises(ValueError, match="above its maximum"):
        Range(2, 1)
    assert str(Range(-20.0, 20.0)) == "-20.0 ... 20.0"


# --- @command ------------------------------------------------------------------------------------------------------


def test_command_keeps_the_method() -> None:
    """The wrapper keeps name, docstring and signature, and carries the metadata."""
    method = Declared.set_voltage
    assert method.__name__ == "set_voltage"
    assert method.__doc__ == "Set the output voltage."
    assert list(inspect.signature(method).parameters) == ["self", "channel", "voltage"]
    assert command_info(method) == CommandInfo(kind="set")
    assert getattr(Declared.get_level, COMMAND_ATTRIBUTE) == CommandInfo(("voltage",), "setpoint", kind="read")
    assert command_info(Declared.helper) is None


def test_command_refuses_wrong_arguments_of_its_own() -> None:
    """The argument returns must be a sequence of names, reads one of the three kinds."""
    with pytest.raises(TypeError, match="sequence of quantity names"):
        command(returns="voltage")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="reads must be one of"):
        command(reads="readback")
    with pytest.raises(TypeError, match="hazards must be a text"):
        command(hazards=("fine", 3))  # type: ignore[arg-type]


def test_hazards_are_metadata_and_shown_by_help() -> None:
    """Hazards are stored as a tuple of texts and appended to the docstring as a Hazards section."""
    assert command_info(Declared.set_source_mode) == CommandInfo(
        hazards=("FIMV with no load drives the output to compliance.",),
        kind="set",
    )
    assert inspect.getdoc(Declared.reset) == (
        "Reset the instrument.\n\nA longer explanation of the reset.\n\nHazards:\n"
        "    Re-enumerates the USB device: the open port is lost.\n"
        "    Resets every setting, also those the driver promised to keep."
    )
    assert inspect.getdoc(Declared.set_voltage) == "Set the output voltage."

    @command(hazards="  A text   wrapped\n   over lines.  ")
    def undocumented() -> None:
        pass

    assert command_info(undocumented) == CommandInfo(hazards=("A text wrapped over lines.",), kind="run")
    assert undocumented.__doc__ == "Hazards:\n    A text wrapped over lines."


def test_declared_command_must_state_what_it_is() -> None:
    """A declared command needs a return annotation, a reader needs returns; setters take neither returns nor reads."""
    with pytest.raises(TypeError, match="needs a return annotation"):

        @command
        def no_annotation(value: float):  # type: ignore[no-untyped-def]  # noqa: ANN202
            pass

    with pytest.raises(TypeError, match=r"a reader needs returns=\(\.\.\.\)"):

        @command
        def get_voltage() -> float:
            return 1.0

    with pytest.raises(TypeError, match="only for readers"):

        @command(returns=("voltage",))
        def set_voltage(voltage: float) -> None:
            pass

    with pytest.raises(TypeError, match="only for readers"):

        @command(reads="setpoint")
        def apply_settings() -> None:
            pass


def test_reads_defaults_to_measurement() -> None:
    """Without reads a declared reader reads a measurement, whatever its name says."""
    device = Declared()
    assert spec_of(device, "fetch_temperature").reads == "measurement"
    assert spec_of(device, "fetch_current").reads == "last"
    assert spec_of(device, "get_level").reads == "setpoint"
    assert spec_of(device, "get_status").reads == "state"


@pytest.mark.skipif(sys.version_info < (3, 14), reason="only Python 3.14 evaluates annotations lazily")
def test_forward_reference_does_not_break_loading(tmp_path: Path) -> None:
    """On Python 3.14 a return annotation naming something defined later is not evaluated by @command."""
    source = textwrap.dedent(
        """
        from pysweepme import command
        from pysweepme.EmptyDeviceClass import EmptyDevice


        class Device(EmptyDevice):
            @command(returns=("reading",))
            def get_reading(self) -> Reading:
                return 1.0


        Reading = float
        """,
    )
    path = tmp_path / "forward_driver.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("forward_driver", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["forward_driver"] = module
    try:
        spec.loader.exec_module(module)
        assert command_info(module.Device.get_reading) == CommandInfo(("reading",), "measurement", kind="read")
    finally:
        del sys.modules["forward_driver"]


def test_literal_is_matched_case_insensitively() -> None:
    """A Literal argument is matched without case and outer spaces and handed on in its canonical spelling."""
    device = Declared()
    device.set_source_mode(1, " fvmi ")
    assert device.calls[-1] == ("set_source_mode", (1, "FVMI"))
    with pytest.raises(ValueError, match=r"set_source_mode: mode 'XYZ' is not one of FVMI, FIMV\."):
        device.set_source_mode(1, "XYZ")


def test_numbers_are_converted_and_ranges_checked() -> None:
    """Text becomes a number, a range is checked inclusively and the error names command, value and unit."""
    device = Declared()
    device.set_voltage("1", "2.5")
    assert device.calls[-1] == ("set_voltage", (1, 2.5))
    device.set_voltage(1, 20)
    assert device.calls[-1] == ("set_voltage", (1, 20.0))
    with pytest.raises(ValueError, match=r"set_voltage: voltage 30\.0 is outside -20\.0 \.\.\. 20\.0 V\."):
        device.set_voltage(1, 30)
    with pytest.raises(ValueError, match="is not a number"):
        device.set_voltage(1, "high")
    with pytest.raises(ValueError, match="is not a number"):
        device.set_voltage(1, True)  # noqa: FBT003  # a bool is not taken for a number
    device.set_points(1, "10")
    assert device.calls[-1] == ("set_points", (1, 10))
    device.set_points(1, "4.0")
    assert device.calls[-1] == ("set_points", (1, 4))
    with pytest.raises(ValueError, match=r"is not a number \(int\)"):
        device.set_points(1, 2.5)
    with pytest.raises(ValueError, match=r"is outside 1 \.\.\."):
        device.set_points(1, 0)


def test_bool_and_optional_arguments() -> None:
    """Bools accept their usual texts and 0/1; None passes where the annotation allows it."""
    device = Declared()
    for text, expected in (("on", True), ("False", False), ("1", True), (0, False), (True, True)):
        device.set_output(1, text)  # type: ignore[arg-type]
        assert device.calls[-1] == ("set_output", (1, expected))
    with pytest.raises(ValueError, match="is not a bool"):
        device.set_output(1, "maybe")  # type: ignore[arg-type]
    device.set_offset(1)
    assert device.calls[-1] == ("set_offset", (1, None))
    device.set_offset(1, None)
    assert device.calls[-1] == ("set_offset", (1, None))
    device.set_offset(1, "0.5")  # type: ignore[arg-type]
    assert device.calls[-1] == ("set_offset", (1, 0.5))


def test_keyword_arguments_are_checked() -> None:
    """Arguments passed by keyword are checked like positional ones."""
    device = Declared()
    device.set_voltage(channel=2, voltage="-1")  # type: ignore[arg-type]
    assert device.calls[-1] == ("set_voltage", (2, -1.0))
    with pytest.raises(ValueError, match="outside"):
        device.set_voltage(channel=2, voltage=-21)


def test_driver_module_with_future_annotations(tmp_path: Path) -> None:
    """In a driver module with `from __future__ import annotations` the aliases at module level are resolved."""
    source = textwrap.dedent(
        '''
        from __future__ import annotations

        from typing import Annotated, Literal

        from pysweepme import Range, Unit, command
        from pysweepme.EmptyDeviceClass import EmptyDevice

        Volts = Annotated[float, Unit("V")]
        Mode = Literal["AUTO", "HIGH", "LOW"]


        class Device(EmptyDevice):
            """A driver written as a separate module."""

            @command
            def set_range(self, channel: int, mode: Mode) -> None:
                """Set the range."""
                self.last = mode

            @command
            def set_voltage(self, channel: int, voltage: Annotated[Volts, Range(0, 5)]) -> None:
                """Set the voltage."""
                self.last = voltage
        ''',
    )
    path = tmp_path / "future_driver.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("future_driver", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["future_driver"] = module
    try:
        spec.loader.exec_module(module)
        device = module.Device()
        device.set_range(1, "high")
        assert device.last == "HIGH"
        device.set_voltage(1, "5")
        assert device.last == float("5")
        with pytest.raises(ValueError, match=r"outside 0 \.\.\. 5 V"):
            device.set_voltage(1, 6)
        voltage = next(p for p in spec_of(device, "set_voltage").parameters if p.name == "voltage")
        assert voltage.value.unit == "V"
        assert voltage.value.range == Range(0, 5)
    finally:
        del sys.modules["future_driver"]


def test_undeclared_and_unresolvable_annotations_are_left_alone() -> None:
    """A parameter without annotation, or with one that cannot be resolved, is passed through unchecked."""

    @command(returns=("value",))
    def plain(value) -> object:  # noqa: ANN001  # deliberately without a parameter annotation
        return value

    @command(returns=("value",))
    def unresolvable(value: NoSuchType) -> object:  # type: ignore[name-defined]  # noqa: F821
        return value

    assert plain("anything") == "anything"
    assert unresolvable("anything") == "anything"


# --- describe_commands -----------------------------------------------------------------------------------------------


def test_declared_driver_lists_only_decorated_methods() -> None:
    """Once a driver uses @command, undecorated public methods are not commands - inherited ones included."""
    names = [spec.name for spec in describe_commands(Declared())]
    assert "helper" not in names
    assert names == sorted(names)
    assert {"set_voltage", "get_level", "reset", "sweep_voltage"} <= set(names)
    inherited = [spec.name for spec in describe_commands(Inherited())]
    assert inherited == names


def test_undeclared_driver_falls_back_to_its_public_methods() -> None:
    """Without @command every own public method counts, with kind and names guessed."""
    specs = {spec.name: spec for spec in describe_commands(Undeclared())}
    assert set(specs) == {"set_voltage", "get_voltage_and_current"}
    assert specs["set_voltage"].kind == "set"
    assert specs["set_voltage"].declared is False
    reader = specs["get_voltage_and_current"]
    assert reader.kind == "read"
    assert reader.returns == ("voltage", "current")
    assert reader.reads == "measurement"


def test_kinds_quantities_and_reads() -> None:
    """Kind comes from the signature, the quantity from the value parameter or returns, reads from @command or name."""
    device = Declared()
    setter = spec_of(device, "set_voltage")
    assert setter.kind == "set"
    assert setter.quantity == "voltage"
    assert [p.name for p in setter.parameters if p.is_channel] == ["channel"]
    voltage = next(p for p in setter.parameters if p.name == "voltage")
    assert (voltage.value.type, voltage.value.unit, voltage.value.range) == (float, "V", Range(-20.0, 20.0))
    assert setter.labels == {"voltage": "Voltage"}

    assert spec_of(device, "reset").kind == "run"
    assert spec_of(device, "sweep_voltage").composite is True

    pair = spec_of(device, "get_voltage_and_current")
    assert (pair.kind, pair.returns, pair.reads) == ("read", ("voltage", "current"), "measurement")
    assert [value.unit for value in pair.return_values] == ["V", "A"]

    readback = spec_of(device, "get_level")
    assert (readback.returns, readback.reads, readback.quantity) == (("voltage",), "setpoint", "voltage")
    assert spec_of(device, "fetch_current").reads == "last"

    rf_power = spec_of(device, "get_rf_power")
    assert rf_power.quantity == "rf_power"
    assert rf_power.labels == {"rf_power": "RF power"}

    mode = next(p for p in spec_of(device, "set_source_mode").parameters if p.name == "mode")
    assert mode.value.choices == ("FVMI", "FIMV")
    assert mode.value.type_name == "str"


def test_kind_run_for_an_action_with_parameters() -> None:
    """kind="run" makes an action with parameters a run command; refused on a reader and for any other value."""

    class Streaming(EmptyDevice):
        @command(kind="run")
        def start_stream(self, pins: list, scan_rate: float) -> None:
            """Start streaming."""

        @command
        def set_scan_rate(self, scan_rate: float) -> None:
            """Set the scan rate."""

    device = Streaming()
    start = spec_of(device, "start_stream")
    assert (start.kind, start.quantity) == ("run", None)
    assert spec_of(device, "set_scan_rate").kind == "set"
    assert command_info(Streaming.start_stream).kind == "run"

    with pytest.raises(TypeError, match="not for a reader"):

        @command(kind="run", returns=("scan_rate",))
        def get_scan_rate(_self: object) -> float:
            """A reader."""
            return 1.0

    with pytest.raises(ValueError, match="kind can only be 'run'"):
        command(kind="set")


def test_description_and_hazards() -> None:
    """The description is the first docstring line, the hazards come from @command."""
    device = Declared()
    assert spec_of(device, "set_voltage").description == "Set the output voltage."
    assert spec_of(device, "set_voltage").hazards == ()
    assert spec_of(device, "set_source_mode").hazards == ("FIMV with no load drives the output to compliance.",)
    assert spec_of(device, "reset").description == "Reset the instrument."
    assert len(spec_of(device, "reset").hazards) == 2  # noqa: PLR2004  # the two hazards declared above
    assert description_of(lambda: None) == ""


def test_derived_labels() -> None:
    """A label derived from a quantity name starts upper case and has spaces."""
    assert derived_label("voltage_limit") == "Voltage limit"
    assert derived_label("rf_power") == "Rf power"
