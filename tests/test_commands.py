"""Tests of the communication command API: markers, @command and its argument check, describe_commands."""

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import sys
import textwrap
import threading
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import pytest

from pysweepme import commands
from pysweepme.commands import (
    COMMAND_ATTRIBUTE,
    CommandError,
    CommandInfo,
    CommandNotice,
    Label,
    Range,
    Selector,
    Unit,
    collecting_notices,
    command,
    command_info,
    derived_label,
    describe_commands,
    description_of,
    notice,
)
from pysweepme.EmptyDeviceClass import EmptyDevice
from pysweepme.Ports import Port

if TYPE_CHECKING:
    from pysweepme.commands import CommandSpec

Volts = Annotated[float, Unit("V")]
Amperes = Annotated[float, Unit("A")]
RfPower = Annotated[float, Unit("dBm"), Label("RF power")]
SourceMode = Literal["FVMI", "FIMV"]
Channel = Annotated[int, Selector()]
Slot = Annotated[int, Selector(), Range(1, 8)]
Pin = Annotated[Literal["FIO0", "FIO1"], Selector()]
Output = Annotated[int, Selector(stateful=True), Range(1, 4)]


class Declared(EmptyDevice):
    """A driver that declares its commands with @command."""

    def __init__(self) -> None:
        """Remember what the commands were called with."""
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    @command
    def set_voltage(self, channel: Channel, voltage: Annotated[Volts, Range(-20.0, 20.0)]) -> None:
        """Set the output voltage."""
        self.calls.append(("set_voltage", (channel, voltage)))

    @command(hazards="FIMV with no load drives the output to compliance.")
    def set_source_mode(self, channel: Channel, mode: SourceMode) -> None:
        """Set the source mode."""
        self.calls.append(("set_source_mode", (channel, mode)))

    @command
    def set_output(self, channel: Channel, state: bool) -> None:  # noqa: FBT001  # the value, positionally
        """Switch the output."""
        self.calls.append(("set_output", (channel, state)))

    @command
    def set_points(self, channel: Channel, points: Annotated[int, Range(1, None)]) -> None:
        """Set the number of points."""
        self.calls.append(("set_points", (channel, points)))

    @command
    def set_offset(self, channel: Channel, offset: float | None = None) -> None:
        """Set an offset, or none."""
        self.calls.append(("set_offset", (channel, offset)))

    @command(returns=("voltage", "current"))
    def get_voltage_and_current(self, channel: Channel) -> tuple[Volts, Amperes]:  # noqa: ARG002  # a test stub
        """Measure voltage and current."""
        return (1.0, 0.001)

    @command(returns=("voltage",), reads="setpoint")
    def get_level(self, channel: Channel) -> Volts:  # noqa: ARG002  # a test stub
        """Read back the voltage setpoint."""
        return 1.0

    @command(returns=("rf_power",))
    def get_rf_power(self) -> RfPower:
        """Measure the RF power."""
        return -10.0

    @command(returns=("current",), reads="last")
    def fetch_current(self, channel: Channel) -> Amperes:  # noqa: ARG002  # a test stub
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
    def sweep_voltage(self, channel: Channel, start: Volts, stop: Volts) -> None:
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
    assert command_info(method) == CommandInfo()
    assert getattr(Declared.get_level, COMMAND_ATTRIBUTE) == CommandInfo(
        returns=("voltage",),
        reads="setpoint",
        kind="read",
    )
    assert command_info(Declared.helper) is None


def test_command_refuses_wrong_arguments_of_its_own() -> None:
    """The argument returns must be a sequence of names, reads one of the three kinds."""
    with pytest.raises(TypeError, match="sequence of names"):
        command(returns="voltage")
    with pytest.raises(ValueError, match="reads must be one of"):
        command(reads="readback")
    with pytest.raises(TypeError, match="hazards must be a text"):
        command(hazards=("fine", 3))  # type: ignore[arg-type]


def test_hazards_are_metadata_and_shown_by_help() -> None:
    """Hazards are stored as a tuple of texts and appended to the docstring as a Hazards section."""
    assert command_info(Declared.set_source_mode) == CommandInfo(
        hazards=("FIMV with no load drives the output to compliance.",),
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

    assert command_info(undocumented) == CommandInfo(hazards=("A text wrapped over lines.",))
    assert undocumented.__doc__ == "Hazards:\n    A text wrapped over lines."


def test_declared_command_must_state_what_it_is() -> None:
    """A declared command needs a return annotation, a reader needs returns; setters take neither returns nor reads."""
    with pytest.raises(TypeError, match="needs a return annotation"):

        @command
        def no_annotation(value: float):  # noqa: ANN202
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
        from pysweepme.commands import command
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
        assert command_info(module.Device.get_reading) == CommandInfo(
            returns=("reading",),
            reads="measurement",
            kind="read",
        )
    finally:
        del sys.modules["forward_driver"]


def test_a_text_choice_must_be_written_exactly() -> None:
    """A Literal text is matched exactly - no case folding, no trimming; a near miss gets a clear error with a hint."""
    device = Declared()
    device.set_source_mode(1, "FVMI")
    assert device.calls[-1] == ("set_source_mode", (1, "FVMI"))
    calls = len(device.calls)
    with pytest.raises(ValueError, match=r"mode 'fvmi' is not one of FVMI, FIMV\. Did you mean 'FVMI'\?"):
        device.set_source_mode(1, "fvmi")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"mode ' FIMV ' is not one of FVMI, FIMV\. Did you mean 'FIMV'\?"):
        device.set_source_mode(1, " FIMV ")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"set_source_mode: mode 'XYZ' is not one of FVMI, FIMV\.$"):
        device.set_source_mode(1, "XYZ")  # type: ignore[arg-type]
    assert len(device.calls) == calls


def test_choices_that_differ_only_in_case_stay_apart() -> None:
    """Two modes that differ only in case are two choices, and each arrives as written."""

    class Cased(EmptyDevice):
        def __init__(self) -> None:
            super().__init__()
            self.modes: list[str] = []

        @command
        def set_mode(self, mode: Literal["a", "A"]) -> None:
            """Set the mode."""
            self.modes.append(mode)

    device = Cased()
    device.set_mode("A")
    device.set_mode("a")
    assert device.modes == ["A", "a"]


def test_a_number_choice_is_converted_from_text() -> None:
    """Type conversion stays: "2" and 2.0 stand for the choice 2, 2 for the choice "2"; a bool is never a number."""

    class Numbered(EmptyDevice):
        @command
        def set_range(self, range_index: Literal[1, 2]) -> None:
            """Set the range."""
            self.range_index = range_index

        @command
        def set_slot(self, slot: Literal["1", "2"]) -> None:
            """Set the slot."""
            self.slot = slot

    device = Numbered()
    for given in ("2", 2.0, " 2 "):
        device.set_range(given)  # type: ignore[arg-type]
        assert device.range_index == 2  # noqa: PLR2004  # the choice 2 of Literal[1, 2]
        assert type(device.range_index) is int
    device.set_slot(2)  # type: ignore[arg-type]
    assert device.slot == "2"
    with pytest.raises(ValueError, match="is not one of 1, 2"):
        device.set_range(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="is not one of 1, 2"):
        device.set_range("3")  # type: ignore[arg-type]


def test_numbers_are_converted_and_ranges_checked() -> None:
    """Text becomes a number, a range is checked inclusively and the error names command, value and unit."""
    device = Declared()
    device.set_voltage("1", "2.5")  # type: ignore[arg-type]
    assert device.calls[-1] == ("set_voltage", (1, 2.5))
    device.set_voltage(1, 20)
    assert device.calls[-1] == ("set_voltage", (1, 20.0))
    with pytest.raises(ValueError, match=r"set_voltage: voltage 30\.0 is outside -20\.0 \.\.\. 20\.0 V\."):
        device.set_voltage(1, 30)
    with pytest.raises(ValueError, match="is not a number"):
        device.set_voltage(1, "high")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="is not a number"):
        device.set_voltage(1, True)  # noqa: FBT003  # a bool is not taken for a number
    device.set_points(1, "10")  # type: ignore[arg-type]
    assert device.calls[-1] == ("set_points", (1, 10))
    device.set_points(1, "4.0")  # type: ignore[arg-type]
    assert device.calls[-1] == ("set_points", (1, 4))
    with pytest.raises(ValueError, match=r"is not a number \(int\)"):
        device.set_points(1, 2.5)  # type: ignore[arg-type]
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
    assert device.calls.pop() == ("set_offset", (1, 0.5))


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

        from pysweepme.commands import Range, Unit, command
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
        device.set_range(1, "HIGH")
        assert device.last == "HIGH"
        with pytest.raises(ValueError, match="Did you mean 'HIGH'"):
            device.set_range(1, "high")
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


def test_one_unresolvable_annotation_leaves_the_others_checked() -> None:
    """A name only a type checker knows (if TYPE_CHECKING:) disables the check of that one parameter, not all."""

    class Mixed(EmptyDevice):
        @command
        def set_voltage(self, voltage: Annotated[Volts, Range(0.0, 5.0)], handler: NoSuchType) -> None:  # type: ignore[name-defined]  # noqa: F821
            """Set the voltage."""

        @command(returns=("level",))
        def get_level(self, mode: SourceMode) -> NoSuchType:  # type: ignore[name-defined]  # noqa: F821
            """Read a level."""
            return mode

    device = Mixed()
    device.set_voltage("2.5", handler=object())  # type: ignore[arg-type]
    # typing caches Annotated by equality and Range(0, 5) == Range(0.0, 5.0): the bounds print as either.
    with pytest.raises(ValueError, match=r"set_voltage: voltage 6\.0 is outside 0(\.0)? \.\.\. 5(\.0)? V\."):
        device.set_voltage(6.0, handler=object())
    assert device.get_level("FVMI") == "FVMI"
    voltage = next(p for p in spec_of(device, "set_voltage").parameters if p.name == "voltage")
    assert (voltage.value.unit, voltage.value.range) == ("V", Range(0.0, 5.0))


def test_a_class_local_alias_is_checked_also_when_inherited() -> None:
    """A class-local Annotated alias in a deferred annotation is resolved from the class that defines the command.

    This module has future annotations, so the alias reaches the check as text; a subclass calls the command too.
    """

    class Base(EmptyDevice):
        Level = Annotated[float, Unit("V"), Range(-1.0, 1.0)]

        @command
        def set_level(self, level: Level) -> None:
            """Set the level."""

    class Child(Base):
        pass

    for device in (Base(), Child()):
        with pytest.raises(ValueError, match=r"set_level: level 5\.0 is outside -1\.0 \.\.\. 1\.0 V\."):
            device.set_level(5.0)
        device.set_level(0.5)
        level = spec_of(device, "set_level").parameters[0]
        assert (level.value.unit, level.value.range) == ("V", Range(-1.0, 1.0))


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
    assert [p.name for p in setter.parameters if p.selector] == ["channel"]
    assert setter.selectors == ("channel",)
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
        def start_stream(self, pins: list[str], scan_rate: float) -> None:
            """Start streaming."""

        @command
        def set_scan_rate(self, scan_rate: float) -> None:
            """Set the scan rate."""

    device = Streaming()
    start = spec_of(device, "start_stream")
    assert (start.kind, start.quantity) == ("run", None)
    assert spec_of(device, "set_scan_rate").kind == "set"
    info = command_info(Streaming.start_stream)
    assert info is not None
    assert info.kind == "run"

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


class Composed(EmptyDevice):
    """A driver whose composites call commands directly, through a helper and through each other."""

    @command(hazards="HIGH drives the output to compliance.")
    def set_range(self, range_type: Literal["AUTO", "HIGH"]) -> None:
        """Set the range."""

    @command(hazards=("Drops the USB connection.",))
    def reset(self) -> None:
        """Reset the instrument."""

    @command
    def set_level(self, level: float) -> None:
        """Set the level."""

    def _prepare(self) -> None:
        self.reset()
        self.set_range("AUTO")

    @command(composite=True)
    def start_over(self) -> None:
        """Reset, then set the auto range - through a helper."""
        self._prepare()
        self.set_level(0.0)

    @command(composite=True, hazards="Sends its own raw commands.")
    def ramp(self, level: float) -> None:
        """Start over, then go to the level."""
        self.start_over()
        self.set_level(level)
        self.ramp(level)  # a cycle must not hang the walk

    @command(composite=True)
    def by_name(self) -> None:
        """Calls through getattr: not seen."""
        getattr(self, "reset")()  # noqa: B009  # the case the code cannot show


def test_a_composite_inherits_the_hazards_of_what_it_calls() -> None:
    """A composite's calls are read from its code, helpers followed; their hazards are added with their origin."""
    device = Composed()
    start_over = spec_of(device, "start_over")
    assert start_over.calls == ("reset", "set_range", "set_level")
    assert start_over.hazards == (
        "reset: Drops the USB connection.",
        "set_range: HIGH drives the output to compliance.",
    )
    ramp = spec_of(device, "ramp")
    assert ramp.calls == ("start_over", "set_level")
    assert ramp.hazards == (
        "Sends its own raw commands.",
        "reset: Drops the USB connection.",
        "set_range: HIGH drives the output to compliance.",
    )
    assert spec_of(device, "by_name").calls == ()
    assert spec_of(device, "by_name").hazards == ()
    assert spec_of(device, "set_range").calls == ()
    assert spec_of(device, "set_range").hazards == ("HIGH drives the output to compliance.",)


def test_inherited_hazards_reach_the_docstring() -> None:
    """help() shows a composite's inherited hazards too, completed when the driver class is created."""
    doc = inspect.getdoc(Composed.ramp) or ""
    assert doc.startswith("Start over, then go to the level.")
    assert "Hazards:" in doc
    assert "Sends its own raw commands." in doc
    assert "reset: Drops the USB connection." in doc
    assert "set_range: HIGH drives the output to compliance." in doc
    assert "Hazards:" not in (inspect.getdoc(Composed.by_name) or "")


def test_a_composite_of_a_subclass_inherits_from_the_base() -> None:
    """A composite calling commands its base class defines inherits their hazards as well."""

    class Child(Composed):
        @command(composite=True)
        def restart(self) -> None:
            """Reset and set the range."""
            self.reset()

    assert spec_of(Child(), "restart").hazards == ("reset: Drops the USB connection.",)
    assert "reset: Drops the USB connection." in (inspect.getdoc(Child.restart) or "")


def test_derived_labels() -> None:
    """A label derived from a quantity name starts upper case and has spaces."""
    assert derived_label("voltage_limit") == "Voltage limit"
    assert derived_label("rf_power") == "Rf power"


def test_the_receiver_passed_by_keyword_resolves_class_local_aliases() -> None:
    """A first call that passes the instance by keyword must not cache a spec without the class-local alias."""

    class Base(EmptyDevice):
        Level = Annotated[float, Unit("V"), Range(-1.0, 1.0)]

        @command
        def set_level(self, level: Level) -> None:
            """Set the level."""

    device = Base()
    Base.set_level(self=device, level=0.5)
    with pytest.raises(ValueError, match=r"set_level: level 5\.0 is outside"):
        Base.set_level(self=device, level=5.0)
    with pytest.raises(ValueError, match=r"set_level: level 5\.0 is outside"):
        device.set_level(5.0)


def test_list_elements_are_checked() -> None:
    """Each element of a list, a variadic tuple or a Sequence is checked and converted; text is no list."""
    np = pytest.importorskip("numpy")

    class Pins(EmptyDevice):
        @command
        def set_pins(self, pins: list[Literal["AIN0", "AIN1"]]) -> None:
            """Select the pins."""
            self.pins = pins

        @command
        def set_levels(self, levels: tuple[Annotated[float, Range(0.0, 5.0)], ...]) -> None:
            """Set the levels."""
            self.levels = levels

    device = Pins()
    device.set_pins(["AIN1", "AIN0"])
    assert device.pins == ["AIN1", "AIN0"]
    with pytest.raises(ValueError, match=r"set_pins: pins\[0\] 'AIN9' is not one of AIN0, AIN1\."):
        device.set_pins(["AIN9"])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="is not a list"):
        device.set_pins("AIN0,AIN1")  # type: ignore[arg-type]
    device.set_levels(("1.5", 2))  # type: ignore[arg-type]
    assert device.levels == (1.5, 2.0)
    with pytest.raises(ValueError, match=r"levels\[1\] 6\.0 is outside 0\.0 \.\.\. 5\.0"):
        device.set_levels((1.0, 6.0))
    array = np.array([1.0, 2.0])
    device.set_levels(array)
    assert device.levels is array  # checked, handed on as it is
    with pytest.raises(ValueError, match="is outside"):
        device.set_levels(np.array([[1.0, 9.0]]))


def test_command_refuses_what_cannot_be_called_by_name() -> None:
    """Static and class methods, properties, *args/**kwargs and a channel default are refused when loading."""
    with pytest.raises(TypeError, match="plain instance method"):
        command(staticmethod(lambda: None))
    with pytest.raises(TypeError, match="plain instance method"):
        command(property(lambda _self: 1))  # type: ignore[call-overload]
    with pytest.raises(TypeError, match=r"\*channels cannot be passed by name"):

        @command
        def set_mode(self: object, mode: str, *channels: int) -> None:
            """Set the mode of channels."""

    with pytest.raises(TypeError, match=r"\*\*options cannot be passed by name"):

        @command
        def configure_all(self: object, **options: float) -> None:
            """Configure."""


def test_an_override_without_command_is_refused() -> None:
    """A subclass overriding a command without @command would silently drop it, so creating the class fails."""

    class Base(EmptyDevice):
        @command
        def set_level(self, level: float) -> None:
            """Set the level."""

        def helper(self) -> None:
            """Not a command."""

    with pytest.raises(TypeError, match=r"overrides the command Base\.set_level without @command"):

        class Child(Base):
            def set_level(self, level: float) -> None:
                """Set the level, differently."""

    class Decorated(Base):
        @command
        def set_level(self, level: float) -> None:
            """Set the level, differently."""

        def helper(self) -> None:
            """Still not a command, and overriding a helper is fine."""

    assert command_info(Decorated.set_level) is not None


def test_a_numeric_choice_keeps_its_range() -> None:
    """A Range beside numeric Literal choices still holds: the choice 1 is outside Range(2, 2)."""

    class Narrowed(EmptyDevice):
        @command
        def set_gain(self, gain: Annotated[Literal[1, 2], Range(2, 2)]) -> None:
            """Set the gain."""
            self.gain = gain

    device = Narrowed()
    device.set_gain("2")  # type: ignore[arg-type]
    assert device.gain == 2  # noqa: PLR2004  # the choice 2
    with pytest.raises(ValueError, match=r"set_gain: gain 1 is outside 2 \.\.\. 2\."):
        device.set_gain(1)


def test_an_array_whose_elements_need_converting_is_refused() -> None:
    """An array is handed on as it is, so an array of texts for numbers is refused instead of passed on unconverted."""
    np = pytest.importorskip("numpy")

    class Levels(EmptyDevice):
        @command
        def set_levels(self, levels: list[float]) -> None:
            """Set the levels."""
            self.levels = levels

    device = Levels()
    numbers_array = np.array([1, 2])
    device.set_levels(numbers_array)
    assert device.levels is numbers_array
    with pytest.raises(ValueError, match=r"levels\[0\] '1\.5' would need converting"):
        device.set_levels(np.array(["1.5", "2.0"]))
    device.set_levels(["1.5", "2.0"])  # type: ignore[list-item]
    assert device.levels == [1.5, 2.0]


def test_a_positional_only_parameter_is_refused() -> None:
    """A parameter before / cannot be passed by name; the receiver itself may be positional-only."""
    with pytest.raises(TypeError, match="level is positional-only"):

        @command
        def set_level(self: object, level: float, /) -> None:
            """Set the level."""

    @command
    def set_offset(self: object, /, offset: float) -> None:
        """Set the offset."""

    assert command_info(set_offset) is not None


# --- selectors -----------------------------------------------------------------------------------------------------


def test_a_selector_is_no_value() -> None:
    """A Selector-marked parameter addresses a subunit: the kind and the quantity come from the other parameters."""

    class Mainframe(EmptyDevice):
        @command
        def enable_output(self, slot: Slot, channel: Channel) -> None:
            """Switch the output of a channel on."""

        @command
        def set_voltage(self, slot: Slot, channel: Channel, voltage: Volts) -> None:
            """Set the voltage of a channel."""

        @command
        def set_digital_output(self, pin: Pin, state: bool) -> None:  # noqa: FBT001  # the value, positionally
            """Set a digital output."""
            self.state = (pin, state)

        @command(returns=("voltage",))
        def get_voltage(self, slot: Slot, channel: Channel) -> Volts:  # noqa: ARG002  # a test stub
            """Measure the voltage of a channel."""
            return 1.0

    device = Mainframe()
    run = spec_of(device, "enable_output")
    assert (run.kind, run.selectors, run.quantity) == ("run", ("slot", "channel"), None)
    setter = spec_of(device, "set_voltage")
    assert (setter.kind, setter.selectors, setter.quantity) == ("set", ("slot", "channel"), "voltage")
    assert setter.labels == {"voltage": "Voltage"}
    digital = spec_of(device, "set_digital_output")
    assert (digital.kind, digital.selectors, digital.quantity) == ("set", ("pin",), "state")
    assert spec_of(device, "get_voltage").selectors == ("slot", "channel")
    slot = next(p for p in setter.parameters if p.name == "slot")
    assert (slot.selector, slot.value.range) == (True, Range(1, 8))
    with pytest.raises(ValueError, match=r"set_voltage: slot 9 is outside 1 \.\.\. 8\."):
        device.set_voltage(9, 1, 1.0)
    with pytest.raises(ValueError, match="pin 'FIO7' is not one of FIO0, FIO1"):
        device.set_digital_output("FIO7", True)  # type: ignore[arg-type]  # noqa: FBT003


def test_channel_is_a_selector_by_name_only_without_command() -> None:
    """Without @command a parameter named channel is the selector; with it, an unmarked channel is a plain value."""

    class Undeclared(EmptyDevice):
        def set_voltage(self, channel: int, voltage: float) -> None:
            """Set the voltage."""

    class Unmarked(EmptyDevice):
        @command
        def set_voltage(self, channel: int, voltage: float) -> None:
            """Set the voltage."""

    undeclared = spec_of(Undeclared(), "set_voltage")
    assert (undeclared.selectors, undeclared.quantity) == (("channel",), "voltage")
    unmarked = spec_of(Unmarked(), "set_voltage")
    assert (unmarked.selectors, unmarked.kind, unmarked.quantity) == ((), "set", None)


def test_a_class_local_selector_alias_is_recognised() -> None:
    """A selector alias in the class body resolves once the class exists, for kind and checks alike."""

    class Local(EmptyDevice):
        Output = Annotated[int, Selector(), Range(1, 2)]

        @command
        def enable(self, output: Output) -> None:
            """Enable an output."""

    spec = spec_of(Local(), "enable")
    assert (spec.kind, spec.selectors) == ("run", ("output",))
    with pytest.raises(ValueError, match="output 3 is outside"):
        Local().enable(3)


def test_a_selector_takes_no_default() -> None:
    """A default on a selector is refused when the class is created: leaving it out would address the default."""
    with pytest.raises(TypeError, match="the selector channel takes no default"):

        class Defaulted(EmptyDevice):
            @command
            def set_voltage(self, voltage: float, channel: Channel = 1) -> None:
                """Set the voltage."""

    class Plain(EmptyDevice):
        @command
        def set_voltage(self, voltage: float, delay: float = 0.0) -> None:
            """A default on a value is fine."""

    assert spec_of(Plain(), "set_voltage").selectors == ()


# --- stateful selectors ----------------------------------------------------------------------------------------------


class Selecting(EmptyDevice):
    """An instrument that keeps its output selected (INST:OUT<n>) and takes the voltage without the output."""

    def __init__(self) -> None:
        """Remember what was sent."""
        super().__init__()
        self.sent: list[str] = []

    def apply_selectors(self, output: int) -> None:
        """Select the output the next commands act on."""
        self.sent.append(f"INST:OUT{output}")

    @command
    def set_voltage(self, output: Output, voltage: Volts) -> None:  # noqa: ARG002  # selected by apply_selectors
        """Set the voltage of one output."""
        self.sent.append(f"VOLT {voltage}")

    @command(returns=("identification",))
    def get_identification(self) -> str:
        """No output involved."""
        return "NGx"


class OtherSelecting(Selecting):
    """Another driver on the same port: its selection means something else to this one."""


def shared_port() -> Port:
    """A Port without a resource behind it - the memory needs none."""
    port = Port.__new__(Port)
    port.port_properties = {}
    return port


def test_a_stateful_selection_is_sent_only_when_it_changes() -> None:
    """One output used: one INST:OUT at the first command; a change of output selects again."""
    device = Selecting()
    device.port = shared_port()
    device.set_voltage(1, 2.0)
    device.set_voltage(1, 3.0)
    device.get_identification()
    device.set_voltage(output="2", voltage=1.0)  # type: ignore[arg-type]  # @command converts it
    assert device.sent == ["INST:OUT1", "VOLT 2.0", "VOLT 3.0", "INST:OUT2", "VOLT 1.0"]


def test_instances_on_one_port_share_the_selection() -> None:
    """Two bench entries on output 1 and 2: each selects again after the other did, never trusting its own memory."""
    port = shared_port()
    first, second = Selecting(), Selecting()
    first.port = second.port = port
    first.set_voltage(1, 1.0)
    second.set_voltage(2, 2.0)
    first.set_voltage(1, 1.5)
    second.set_voltage(2, 2.5)
    assert first.sent == ["INST:OUT1", "VOLT 1.0", "INST:OUT1", "VOLT 1.5"]
    assert second.sent == ["INST:OUT2", "VOLT 2.0", "INST:OUT2", "VOLT 2.5"]
    third = Selecting()
    third.port = port
    third.set_voltage(2, 0.5)
    assert third.sent == ["VOLT 0.5"]  # the instrument has output 2 selected, whoever selected it


def test_a_selection_by_another_driver_is_unknown() -> None:
    """Another driver class on the same port may mean something else by its selection: select again."""
    port = shared_port()
    mine, other = Selecting(), OtherSelecting()
    mine.port = other.port = port
    mine.set_voltage(1, 1.0)
    other.set_voltage(1, 1.0)
    assert other.sent == ["INST:OUT1", "VOLT 1.0"]


def test_unknown_means_select_again() -> None:
    """Forgotten after raw traffic, on open and close, by the driver's own reset - and after a failed selection."""
    device = Selecting()
    device.port = port = shared_port()
    device.set_voltage(1, 1.0)
    for forget in (port.forget_selections, port.open, port.close, device.forget_selections):
        device.sent.clear()
        forget()
        device.set_voltage(1, 1.0)
        assert device.sent == ["INST:OUT1", "VOLT 1.0"], forget
    assert port.selection("someone else") == {}


def test_a_failed_selection_is_forgotten() -> None:
    """A selection that raised may have half happened: nothing is remembered, the next command selects again."""

    class Failing(Selecting):
        fail = True

        def apply_selectors(self, output: int) -> None:
            """Fail once."""
            if self.fail:
                self.fail = False
                msg = "timeout"
                raise TimeoutError(msg)
            super().apply_selectors(output)

    device = Failing()
    device.port = shared_port()
    with pytest.raises(TimeoutError):
        device.set_voltage(1, 1.0)
    device.set_voltage(1, 1.0)
    assert device.sent == ["INST:OUT1", "VOLT 1.0"]


def test_every_selection_is_remembered() -> None:
    """A selection by a semantic function or a host (apply_selectors called directly) is known to the commands."""
    device = Selecting()
    device.port = shared_port()
    device.apply_selectors(output=3)
    device.set_voltage(3, 1.0)
    assert device.sent == ["INST:OUT3", "VOLT 1.0"]


def test_a_driver_without_port_remembers_on_itself() -> None:
    """No Port (a simulation, an SDK): the memory is the instance's."""
    device = Selecting()
    device.set_voltage(4, 1.0)
    device.set_voltage(4, 2.0)
    assert device.sent == ["INST:OUT4", "VOLT 1.0", "VOLT 2.0"]


def test_a_stateful_selector_needs_apply_selectors_taking_it() -> None:
    """Refused when the class is created: without apply_selectors, or with one not taking it, nothing could select."""
    with pytest.raises(TypeError, match=r"need apply_selectors\(output\)"):

        class NoHook(EmptyDevice):
            @command
            def set_voltage(self, output: Output, voltage: float) -> None:
                """Set the voltage."""

    with pytest.raises(TypeError, match="does not take them"):

        class WrongHook(EmptyDevice):
            def apply_selectors(self, channel: int) -> None:
                """Takes another selector."""

            @command
            def set_voltage(self, output: Output, voltage: float) -> None:
                """Set the voltage."""

    class AnyHook(EmptyDevice):
        def apply_selectors(self, **selectors: object) -> None:
            """Takes whatever is selected."""

        @command
        def set_voltage(self, output: Output, voltage: float) -> None:
            """Set the voltage."""

    assert AnyHook.apply_selectors is not EmptyDevice.apply_selectors


def test_a_plain_selector_selects_nothing() -> None:
    """A selector the instrument takes in every command (Selector() without stateful) never calls apply_selectors."""
    device = Declared()
    device.apply_selectors = lambda **_: pytest.fail("selected")  # type: ignore[method-assign]
    device.set_voltage(1, 2.0)
    assert device.calls == [("set_voltage", (1, 2.0))]


# --- values reaching the same hardware ------------------------------------------------------------------------------

Supply = Annotated[
    Literal["+6V", "+25V", "-25V", "TRACK25V"],
    Selector(overlaps={"TRACK25V": ("+25V", "-25V")}),
]


ModelPin = Annotated[str, Selector(overlaps="pin_overlaps")]


class Tracking(EmptyDevice):
    """Three outputs, and tracking driving two of them."""

    @command
    def set_voltage(self, output: Supply, voltage: float) -> None:
        """Set the voltage."""

    @command(returns=("voltage",))
    def get_voltage(self, output: Supply) -> float:  # noqa: ARG002  # a test stub
        """Measure the voltage."""
        return 0.0


def test_overlaps_are_kept_immutable_and_answered_both_ways_round() -> None:
    """The marker keeps a mapping as pairs; the answer adds the way back, and does not chain +25V to -25V."""
    marker = Selector(overlaps={"TRACK25V": ["+25V", "-25V"], "A": "B"})
    assert marker.overlaps == (("TRACK25V", ("+25V", "-25V")), ("A", ("B",)))
    assert hash(marker) == hash(Selector(overlaps={"TRACK25V": ("+25V", "-25V"), "A": ("B",)}))
    spec = commands.describe_command(Tracking(), "set_voltage").parameters[0].value  # type: ignore[union-attr]
    assert commands.selector_overlaps(Tracking(), spec) == {
        "TRACK25V": ("+25V", "-25V"),
        "+25V": ("TRACK25V",),
        "-25V": ("TRACK25V",),
    }
    assert commands.selector_overlaps(Tracking(), commands.value_spec(Output)) == {}


def test_overlaps_answered_by_a_method_follow_the_instrument() -> None:
    """A method named instead is asked each time: None while the model is not known, its mapping afterwards."""

    class Pins(EmptyDevice):
        model: str | None = None

        def pin_overlaps(self) -> dict[str, tuple[str, ...]] | None:
            """AIN4 is FIO4 on the T4 only."""
            if self.model is None:
                return None
            return {"AIN4": ("FIO4",)} if self.model == "T4" else {}

        @command(returns=("voltage",))
        def get_voltage(self, pin: ModelPin) -> float:  # noqa: ARG002  # a test stub
            """Measure the voltage."""
            return 0.0

    device = Pins()
    spec = commands.value_spec(ModelPin)
    assert commands.selector_overlaps(device, spec) is None
    device.model = "T7"
    assert commands.selector_overlaps(device, spec) == {}
    device.model = "T4"
    assert commands.selector_overlaps(device, spec) == {"AIN4": ("FIO4",), "FIO4": ("AIN4",)}


def test_wrong_overlaps_are_refused_when_the_class_is_created() -> None:
    """A value the selector does not take, a value overlapping itself, a missing method, two declarations."""
    with pytest.raises(TypeError, match="is not one of"):

        class Unknown(EmptyDevice):
            @command
            def set_voltage(
                self,
                output: Annotated[Literal["A", "B"], Selector(overlaps={"AB": ("A", "B")})],
                voltage: float,
            ) -> None:
                """Set the voltage."""

    with pytest.raises(TypeError, match="overlapping itself"):

        class Itself(EmptyDevice):
            @command
            def set_voltage(self, output: Annotated[int, Selector(overlaps={1: (1, 2)})], voltage: float) -> None:
                """Set the voltage."""

    with pytest.raises(TypeError, match="which is missing"):

        class NoMethod(EmptyDevice):
            @command
            def set_voltage(self, output: Annotated[int, Selector(overlaps="output_overlaps")], voltage: float) -> None:
                """Set the voltage."""

    with pytest.raises(TypeError, match="different overlaps"):

        class TwoDeclarations(EmptyDevice):
            @command
            def set_voltage(self, output: Supply, voltage: float) -> None:
                """Set the voltage."""

            @command
            def set_current(self, output: Annotated[Literal["+6V", "+25V"], Selector()], current: float) -> None:
                """Set the current."""

    with pytest.raises(TypeError, match="mapping"):
        Selector(overlaps=["A", "B"])  # type: ignore[arg-type]  # refused on purpose


# --- extending @command without breaking the drivers written before ------------------------------------------------


def test_every_command_argument_is_keyword_only_with_a_default() -> None:
    """A new @command argument cannot shift an old one, and a driver that does not use it keeps working."""
    parameters = list(inspect.signature(command).parameters.values())
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_ONLY  # the method, when used bare
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is not inspect.Parameter.empty for p in parameters[1:]
    )


def test_marker_options_and_specs_are_keyword_only() -> None:
    """Selector's options and every spec class take keywords only: a field added later shifts no existing call."""
    assert Selector(stateful=True).stateful
    with pytest.raises(TypeError):
        Selector(True)  # type: ignore[misc]  # noqa: FBT003  # positional on purpose
    for spec in (commands.CommandInfo, commands.ValueSpec, commands.ParameterSpec, commands.CommandSpec):
        assert all(item.kw_only for item in dataclasses.fields(spec)), spec.__name__


def test_unknown_annotation_metadata_is_ignored() -> None:
    """A marker pysweepme does not know (from a later version, or another library) leaves the known ones intact."""
    spec = commands.value_spec(Annotated[float, Unit("V"), "a note", object(), Range(0, 5)])
    assert (spec.type, spec.unit, spec.range) == (float, "V", Range(0, 5))


def test_a_driver_without_command_is_not_checked_at_class_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The checks of declared drivers never run for one without @command, so a check added later cannot break it."""

    def refuse(cls: type) -> None:
        pytest.fail(f"{cls.__name__} was checked")

    for check in (
        "check_command_overrides",
        "check_selector_defaults",
        "check_selector_overlaps",
        "complete_hazard_sections",
        "prepare_stateful_selectors",
    ):
        monkeypatch.setattr(commands, check, refuse)

    class Undeclared(EmptyDevice):
        def set_voltage(self, channel: int = 1, voltage: float = 0.0) -> None:
            """A selector default is refused in a declared driver, not here."""

    assert not commands.declares_commands(Undeclared)
    assert commands.declares_commands(Declared)


# --- error codes and notices -------------------------------------------------------------------------------------


class Stage(EmptyDevice):
    """A stage that moves beyond its calibrated range with a notice, and refuses to move while busy."""

    def __init__(self) -> None:
        """Start idle."""
        super().__init__()
        self.busy = False

    @command
    def set_position(self, position: float) -> None:
        """Move to a position; it is calibrated up to 50."""
        if self.busy:
            msg = "The stage is busy."
            raise CommandError(msg, code=38)
        if position > 50:  # noqa: PLR2004  # the calibrated range of this test stage
            notice(f"Position {position:g} lies outside the calibrated range.")

    @command(composite=True)
    def move_twice(self, position: float) -> None:
        """Move to a position and one further."""
        self.set_position(position)
        self.set_position(position + 1)

    @command
    def fail_after_notice(self) -> None:
        """Give a notice, then fail."""
        notice("Half way.")
        msg = "Failed."
        raise RuntimeError(msg)


def test_a_notice_is_kept_for_the_last_call_only() -> None:
    """device.notices holds the notices of the last command called on the instance, replaced by each call."""
    stage = Stage()
    assert not stage.notices
    with collecting_notices():
        stage.set_position(60)
        assert stage.notices == ("Position 60 lies outside the calibrated range.",)
        stage.set_position(10)
        assert not stage.notices


def test_a_composite_is_one_call() -> None:
    """The notices of the commands a composite calls are the composite's."""
    stage = Stage()
    with collecting_notices():
        stage.move_twice(55)
    assert stage.notices == (
        "Position 55 lies outside the calibrated range.",
        "Position 56 lies outside the calibrated range.",
    )


def test_collecting_notices_gathers_a_block_and_warns_nothing() -> None:
    """A block collects across commands and instances; nested blocks each get every notice; no warning is raised."""
    first, second = Stage(), Stage()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a warning would fail the test
        with collecting_notices() as outer:
            first.set_position(60)
            with collecting_notices() as inner:
                second.set_position(70)
    assert outer == ["Position 60 lies outside the calibrated range.", "Position 70 lies outside the calibrated range."]
    assert inner == ["Position 70 lies outside the calibrated range."]


def test_a_notice_nobody_collects_warns_at_the_script_line(tmp_path: Path) -> None:
    """Without a collector a CommandNotice shows the notice, at the line of the script that called the command."""
    driver = tmp_path / "notice_driver.py"
    driver.write_text(
        textwrap.dedent(
            """
            from pysweepme.commands import command, notice
            from pysweepme.EmptyDeviceClass import EmptyDevice


            class Device(EmptyDevice):
                @command
                def set_position(self, position: float) -> None:
                    \"\"\"Move.\"\"\"
                    notice(f"Position {position:g} lies outside the calibrated range.")
            """,
        ),
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("notice_driver", driver)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    device = module.Device()
    with pytest.warns(CommandNotice, match="Position 60 lies outside the calibrated range.") as caught:
        device.set_position(60)  # the script line the warning points at
    assert Path(caught[0].filename).resolve() == Path(__file__).resolve()
    assert device.notices == ("Position 60 lies outside the calibrated range.",)


def test_the_notices_of_a_failing_command_are_kept() -> None:
    """A command that raises after a notice still leaves it in notices."""
    stage = Stage()
    with collecting_notices() as notices, pytest.raises(RuntimeError, match="Failed"):
        stage.fail_after_notice()
    assert stage.notices == ("Half way.",)
    assert notices == ["Half way."]


def test_a_notice_outside_a_command_reaches_the_collectors() -> None:
    """A notice from a semantic phase or a helper goes to the collectors; no command's notices change."""
    stage = Stage()
    with collecting_notices() as notices:
        notice("Configured with defaults.")
    assert notices == ["Configured with defaults."]
    assert stage.notices == ()


def test_collectors_are_per_thread() -> None:
    """Two threads collecting at once each get only their own notices."""
    results: dict[int, list[str]] = {}

    def run(position: int) -> None:
        with collecting_notices() as notices:
            for _ in range(50):
                Stage().set_position(position)
        results[position] = notices

    threads = [threading.Thread(target=run, args=(position,)) for position in (60, 70)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results[60] == ["Position 60 lies outside the calibrated range."] * 50
    assert results[70] == ["Position 70 lies outside the calibrated range."] * 50


def test_command_error_carries_a_code() -> None:
    """CommandError is a RuntimeError whose text is the message and whose code is kept beside it, by keyword only."""
    stage = Stage()
    stage.busy = True
    with pytest.raises(CommandError) as caught:
        stage.set_position(10)
    assert isinstance(caught.value, RuntimeError)
    assert (str(caught.value), caught.value.code) == ("The stage is busy.", 38)
    assert CommandError("No code.").code is None
    with pytest.raises(TypeError):
        CommandError("busy", 38)  # type: ignore[misc]  # the code is keyword-only
