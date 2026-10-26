# The MIT License

# Copyright (c) 2026 SweepMe! GmbH (sweep-me.net)

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Communication commands of a driver: the markers, the @command decorator and the reader describe_commands.

A communication command is a public method of a driver that wraps one instrument command. Everything about a value is
written on the value with standard Python annotations:

    Volts = Annotated[float, Unit("V")]
    SourceMode = Literal["FVMI", "FIMV"]

    @command
    def set_voltage(self, channel: int, voltage: Annotated[Volts, Range(-20.0, 20.0)]) -> None:
        ...

`@command` marks the method as a command and checks its arguments on every call against these annotations.
`describe_commands` reads the commands of a driver instance for SweepMe!, Instrument Control and scripts alike.
"""

from __future__ import annotations

import functools
import inspect
import math
import numbers
import sys
import types
from dataclasses import dataclass, field, replace
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

if sys.version_info >= (3, 14):
    # Annotations are evaluated lazily from Python 3.14 on; a version check rather than try/except ImportError, so
    # that type checkers for older Pythons skip what they cannot know.
    import annotationlib

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .EmptyDeviceClass import EmptyDevice

__all__ = [
    "CommandInfo",
    "CommandSpec",
    "Label",
    "ParameterSpec",
    "Range",
    "Unit",
    "ValueSpec",
    "command",
    "describe_commands",
]

F = TypeVar("F", bound="Callable[..., Any]")

#: Attribute under which @command stores its metadata on the wrapped method.
COMMAND_ATTRIBUTE = "__sweepme_command__"

#: Parameter names that carry the channel of an instrument rather than a value.
CHANNEL_PARAMETERS = ("channel",)

#: What a reader reads: a new measurement, the last measured value, a setpoint (a value a command can set, whether or
#: not the instrument also measures it), or a state (a status or an identity, which no command sets).
READS = ("measurement", "last", "setpoint", "state")
#: What @command(kind=...) may state: an action whose parameters configure it, which the signature would take for a
#: setter. Everything else follows from the signature.
KINDS = ("run",)

#: Text accepted for a bool parameter, compared case-insensitively.
TRUE_TEXTS = ("true", "1", "on", "yes")
FALSE_TEXTS = ("false", "0", "off", "no")

#: Prefixes a reader name is guessed from, where the driver declares nothing.
READER_PREFIXES = ("get_", "measure_", "read_", "fetch_")


@dataclass(frozen=True)
class Unit:
    """The unit of a value, written on its annotation: `Annotated[float, Unit("V")]`."""

    symbol: str


@dataclass(frozen=True)
class Label:
    """The text shown for a value, where the one derived from its quantity name is wrong."""

    text: str


@dataclass(frozen=True)
class Range:
    """Inclusive bounds the instrument accepts for a parameter; None is an open side."""

    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        """Refuse a range whose minimum lies above its maximum."""
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            msg = f"Range minimum {self.minimum} is above its maximum {self.maximum}."
            raise ValueError(msg)

    def contains(self, value: float) -> bool:
        """Whether the value lies within the bounds; NaN never does."""
        if isinstance(value, float) and math.isnan(value):
            return False
        if self.minimum is not None and value < self.minimum:
            return False
        return not (self.maximum is not None and value > self.maximum)

    def __str__(self) -> str:
        """The bounds as text, e.g. "-20.0 ... 20.0"."""
        low = "" if self.minimum is None else f"{self.minimum} "
        high = "" if self.maximum is None else f" {self.maximum}"
        return f"{low}...{high}"


@dataclass(frozen=True)
class CommandInfo:
    """What @command declares about a command as a whole."""

    returns: tuple[str, ...] | None = None
    reads: str | None = None
    composite: bool = False
    hazards: tuple[str, ...] = ()
    kind: str = ""  # "read", "set" or "run": derived from the signature when decorated, unless kind="run" was given


@dataclass(frozen=True)
class ValueSpec:
    """Everything the annotation says about one value: type, choices, unit, label and range."""

    type: Any = None
    optional: bool = False
    choices: tuple[Any, ...] | None = None
    unit: str | None = None
    label: str | None = None
    range: Range | None = None

    @property
    def type_name(self) -> str:
        """The plain type name, e.g. "float", or "" where the annotation gives none."""
        if self.choices is not None:
            return "str" if all(isinstance(c, str) for c in self.choices) else "literal"
        return getattr(self.type, "__name__", "") if self.type is not None else ""


@dataclass(frozen=True)
class ParameterSpec:
    """One parameter of a command."""

    name: str
    value: ValueSpec
    required: bool
    default: Any = None
    is_channel: bool = False


@dataclass(frozen=True)
class CommandSpec:
    """One communication command as SweepMe!, Instrument Control and scripts see it."""

    name: str
    description: str
    hazards: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    kind: str
    returns: tuple[str, ...]
    return_values: tuple[ValueSpec, ...]
    reads: str | None
    composite: bool
    declared: bool
    quantity: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


# --- annotations -------------------------------------------------------------------------------------------------


def _is_union(hint: Any) -> bool:  # noqa: ANN401  # any annotation object
    """Whether the hint is a Union or an X | Y union."""
    return get_origin(hint) in (Union, types.UnionType)


def value_spec(hint: Any) -> ValueSpec:  # noqa: ANN401  # any annotation object
    """Split an annotation into type, Literal choices and the Unit, Label and Range markers."""
    unit = label = None
    value_range = None
    if get_origin(hint) is Annotated:
        hint, *metadata = get_args(hint)
        for item in metadata:
            if isinstance(item, Unit):
                unit = item.symbol
            elif isinstance(item, Label):
                label = item.text
            elif isinstance(item, Range):
                value_range = item
    optional = False
    if _is_union(hint):
        members = [m for m in get_args(hint) if m is not type(None)]
        optional = len(members) < len(get_args(hint))
        if len(members) == 1:
            inner = value_spec(members[0])
            return ValueSpec(
                inner.type,
                optional,
                inner.choices,
                unit or inner.unit,
                label or inner.label,
                value_range or inner.range,
            )
        hint = None
    choices = tuple(get_args(hint)) if get_origin(hint) is Literal else None
    return ValueSpec(None if choices is not None else hint, optional, choices, unit, label, value_range)


def _defining_namespace(owner: type, func: Callable[..., Any]) -> dict[str, Any] | None:
    """The namespace of the class in `owner`'s MRO that defines `func`, for its class-local aliases; else None.

    A deferred annotation (from __future__ import annotations) may name an alias of the class body, such as
    ``Volts = Annotated[float, Range(-1, 1)]``, which the module globals do not hold. An inherited command belongs to
    the class that defines it, not to the subclass it is called on.
    """
    defined_in = inspect.unwrap(func).__qualname__.rpartition(".")[0]
    for cls in getattr(owner, "__mro__", ()):
        if cls.__qualname__ == defined_in:
            return dict(vars(cls))
    return None


def _hints(func: Callable[..., Any], localns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolved annotations of a function, Annotated kept; an annotation that cannot be resolved is left out.

    Each annotation is resolved on its own: a name a driver imports only for type checkers (if TYPE_CHECKING:)
    leaves that one annotation unchecked, but must not take the checks, units and choices of the others with it.
    `localns` is the namespace of the class that defines the method (_defining_namespace), for class-local aliases.
    """
    globalns = getattr(inspect.unwrap(func), "__globals__", None)
    if sys.version_info >= (3, 14):
        # What resolves, resolved; the rest as forward references.
        annotations = annotationlib.get_annotations(func, format=annotationlib.Format.FORWARDREF)
    else:
        annotations = dict(getattr(func, "__annotations__", None) or {})
    hints: dict[str, Any] = {}
    for name, annotation in annotations.items():

        def single() -> None:
            """Carries one annotation, so that get_type_hints resolves it alone."""

        single.__annotations__ = {name: annotation}
        try:
            hints.update(get_type_hints(single, globalns=globalns, localns=localns, include_extras=True))
        # A driver must load even if a name in one annotation cannot be resolved.
        except Exception:  # noqa: BLE001, S112
            continue
    return hints


# --- checking arguments ------------------------------------------------------------------------------------------


def _fail(command_name: str, parameter: str, value: object, expected: str) -> ValueError:
    """The error for a refused argument: command, parameter, value and what is allowed."""
    return ValueError(f"{command_name}: {parameter} {value!r} {expected}")


def _to_float(value: object) -> float | None:
    """Convert a number or its text to float; None where it is not one (a bool is not taken for a number)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return float(value) if isinstance(value, numbers.Real) else None


def _to_int(value: object) -> int | None:
    """Convert a whole number or its text ("4" or "4.0") to int; None where it is not one."""
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    number = _to_float(value)
    return int(number) if number is not None and number.is_integer() else None


def _to_number(value: object, kind: type) -> float | int | None:
    """Convert a number or its text to the given kind, int or float; None where it is not one."""
    return _to_int(value) if kind is int else _to_float(value)


def _to_bool(value: object) -> bool | None:
    """Convert a bool, 0/1 or its text to bool; None where it is not one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral) and int(value) in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_TEXTS:
            return True
        if text in FALSE_TEXTS:
            return False
    return None


def _match_choice(value: object, choices: tuple[Any, ...]) -> tuple[bool, Any]:
    """The canonical choice a value stands for: equal, or equal as text ignoring case and outer spaces."""
    for choice in choices:
        if value == choice and type(value) is type(choice):
            return True, choice
    text = str(value).strip().casefold()
    for choice in choices:
        if str(choice).strip().casefold() == text:
            return True, choice
    return False, None


def check_value(command_name: str, parameter: str, value: object, spec: ValueSpec) -> Any:  # noqa: ANN401
    """Check and convert one argument against its annotation; raise ValueError if it does not fit."""
    if value is None and spec.optional:
        return None
    if spec.choices is not None:
        found, choice = _match_choice(value, spec.choices)
        if not found:
            allowed = ", ".join(str(c) for c in spec.choices)
            raise _fail(command_name, parameter, value, f"is not one of {allowed}.")
        return choice
    if spec.type is bool:
        flag = _to_bool(value)
        if flag is None:
            raise _fail(command_name, parameter, value, "is not a bool (True or False).")
        return flag
    if spec.type in (int, float):
        number = _to_number(value, spec.type)
        if number is None:
            raise _fail(command_name, parameter, value, f"is not a number ({spec.type.__name__}).")
        if spec.range is not None and not spec.range.contains(number):
            unit = f" {spec.unit}" if spec.unit else ""
            raise _fail(command_name, parameter, number, f"is outside {spec.range}{unit}.")
        return number
    if spec.range is not None and isinstance(value, numbers.Real) and not spec.range.contains(float(value)):
        unit = f" {spec.unit}" if spec.unit else ""
        raise _fail(command_name, parameter, value, f"is outside {spec.range}{unit}.")
    return value


# --- @command ----------------------------------------------------------------------------------------------------


def _checked(func: F) -> F:
    """Wrap a method so that its arguments are checked against their annotations on every call."""
    signature = _signature(func)
    specs: dict[str, ValueSpec] | None = None

    def parameter_specs(args: tuple[Any, ...]) -> dict[str, ValueSpec]:
        """The value specs of the parameters, resolved at the first call, when the driver module is complete.

        The instance (the first argument of a method) tells which class defines the command, for its class-local
        aliases.
        """
        nonlocal specs
        if specs is None:
            localns = _defining_namespace(type(args[0]), func) if args else None
            hints = _hints(func, localns)
            specs = {
                name: value_spec(hints[name])
                for name, parameter in signature.parameters.items()
                if name in hints
                and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            }
        return specs

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # the command's own return value
        """Check the given arguments, then call the command."""
        checks = parameter_specs(args)
        if checks:
            bound = signature.bind(*args, **kwargs)
            for name, value in bound.arguments.items():
                if name in checks:
                    bound.arguments[name] = check_value(func.__name__, name, value, checks[name])
            return func(*bound.args, **bound.kwargs)
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]  # functools.wraps keeps the signature of func


@overload
def command(func: F, /) -> F: ...


@overload
def command(
    *,
    returns: Sequence[str] | None = None,
    reads: str | None = None,
    composite: bool = False,
    hazards: str | Sequence[str] | None = None,
    kind: str | None = None,
) -> Callable[[F], F]: ...


def command(  # noqa: PLR0913  # the decorator's keywords are its API
    func: F | None = None,
    /,
    *,
    returns: Sequence[str] | None = None,
    reads: str | None = None,
    composite: bool = False,
    hazards: str | Sequence[str] | None = None,
    kind: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a driver method as a communication command and check its arguments on every call.

    Use it bare (`@command`) or with arguments. Once one method of a driver has it, only decorated methods are
    commands. It must be the outermost decorator. Nothing is guessed from the method name: the method needs a return
    annotation (-> None for a setter or an action), and a reader needs returns; otherwise a TypeError is raised when
    the driver is loaded.

    Args:
        func: The method, when used bare.
        returns: Quantity names of the answered values, in answer order, e.g. ("voltage", "current"). Required for a
            reader, not allowed for a setter or an action.
        reads: What a reader reads: "measurement" (the default), "last", "setpoint" (a value a command can set,
            whether or not the instrument also measures it) or "state" (a status or an identity, which no command
            sets).
        composite: True for a higher-level function that calls other commands, not one instrument command.
        hazards: What can go wrong when the command is called, in plain text: one string, or one string per hazard.
            They are appended to the docstring as a "Hazards:" section, so that help() shows them.
        kind: "run" for an action that takes parameters, e.g. start_stream(pins, scan_rate): the signature alone
            would make it a setter. Not allowed for a reader. Without it, a command that takes a value sets and one
            that takes none runs.

    Returns:
        The wrapped method, or a decorator when called with arguments.
    """
    if isinstance(returns, str):
        msg = f"@command returns must be a sequence of quantity names, e.g. ({returns!r},), not a string."
        raise TypeError(msg)
    if reads is not None and reads not in READS:
        msg = f"@command reads must be one of {', '.join(READS)}, not {reads!r}."
        raise ValueError(msg)
    if kind is not None and kind not in KINDS:
        msg = (
            f"@command kind can only be {', '.join(map(repr, KINDS))}, not {kind!r}: "
            f"set and read follow from the signature."
        )
        raise ValueError(msg)
    declared = CommandInfo(
        tuple(returns) if returns is not None else None,
        reads,
        bool(composite),
        _hazards(hazards),
        kind or "",
    )

    def decorate(method: F) -> F:
        """Check the declaration, wrap the method, attach the metadata and show the hazards in the docstring."""
        info = _completed(method, declared)
        wrapped = _checked(method)
        setattr(wrapped, COMMAND_ATTRIBUTE, info)
        if info.hazards:
            section = "\n".join(f"    {hazard}" for hazard in info.hazards)
            wrapped.__doc__ = f"{inspect.cleandoc(method.__doc__ or '')}\n\nHazards:\n{section}".lstrip()
        return wrapped

    if func is not None:
        return decorate(func)
    return decorate


def _signature(func: Callable[..., Any]) -> inspect.Signature:
    """The signature of a function without evaluating its annotations (Python 3.14 evaluates them lazily)."""
    if sys.version_info >= (3, 14):
        return inspect.signature(func, annotation_format=annotationlib.Format.FORWARDREF)
    return inspect.signature(func)


def _raw_annotations(func: Callable[..., Any]) -> dict[str, Any]:
    """The annotations of a function without evaluating them: strings on Python 3.14+, else as stored."""
    if sys.version_info >= (3, 14):
        return dict(annotationlib.get_annotations(func, format=annotationlib.Format.STRING))
    return dict(getattr(func, "__annotations__", None) or {})


def _is_none_annotation(annotation: object) -> bool:
    """Whether a return annotation, evaluated or as text, says None."""
    if annotation is None or annotation is type(None):
        return True
    return isinstance(annotation, str) and annotation.strip() in ("None", "NoneType")


def _completed(method: Callable[..., Any], declared: CommandInfo) -> CommandInfo:
    """Check what a declared command must state and complete it with its kind and the default of reads.

    In a declared driver nothing is guessed from method names: a command needs a return annotation, a reader needs
    the quantity names of its answer in returns, and a reader reads a measurement unless reads says otherwise.
    """
    name = getattr(method, "__name__", repr(method))
    annotations = _raw_annotations(method)
    if "return" not in annotations:
        msg = f"@command {name}: needs a return annotation, -> None for a setter or an action."
        raise TypeError(msg)
    reader = not _is_none_annotation(annotations["return"])
    if reader and not declared.returns:
        msg = (
            f"@command {name}: a reader needs returns=(...) with the quantity names of its answer, "
            f"e.g. returns=('voltage',)."
        )
        raise TypeError(msg)
    if not reader and (declared.returns is not None or declared.reads is not None):
        msg = f"@command {name}: returns and reads are only for readers, and it is annotated -> None."
        raise TypeError(msg)
    if reader and declared.kind:
        msg = f"@command {name}: kind={declared.kind!r} is for an action annotated -> None, not for a reader."
        raise TypeError(msg)
    if reader:
        return replace(declared, kind="read", reads=declared.reads or "measurement")
    if declared.kind:
        return declared
    parameters = _signature(method).parameters.values()
    takes_value = any(
        p.name != "self"
        and p.name not in CHANNEL_PARAMETERS
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in parameters
    )
    return replace(declared, kind="set" if takes_value else "run")


def _hazards(hazards: str | Sequence[str] | None) -> tuple[str, ...]:
    """The hazards as a tuple of non-empty texts; refuse anything that is not text."""
    if hazards is None:
        return ()
    items = (hazards,) if isinstance(hazards, str) else tuple(hazards)
    if not all(isinstance(item, str) for item in items):
        msg = "@command hazards must be a text or a sequence of texts."
        raise TypeError(msg)
    return tuple(text for item in items if (text := " ".join(item.split())))


def command_info(method: object) -> CommandInfo | None:
    """The @command metadata of a method or function, None if it is not decorated."""
    info = getattr(method, COMMAND_ATTRIBUTE, None)
    return info if isinstance(info, CommandInfo) else None


# --- describe_commands -------------------------------------------------------------------------------------------


def description_of(func: Callable[..., Any]) -> str:
    """The first line of a docstring, "" if there is none."""
    lines = (inspect.getdoc(func) or "").splitlines()
    return lines[0].strip() if lines else ""


def derived_label(quantity: str) -> str:
    """The label derived from a quantity name: "voltage_limit" -> "Voltage limit"."""
    text = quantity.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _guess_reads(name: str) -> str | None:
    """What a reader reads, guessed from its name."""
    if name.endswith("_setpoint"):
        return "setpoint"
    if name.startswith("fetch_"):
        return "last"
    if name.startswith(("get_", "measure_", "read_")):
        return "measurement"
    return None


def _quantity_of_name(name: str) -> str:
    """The quantity a reader name points at: "get_voltage_setpoint" -> "voltage"."""
    for prefix in READER_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return name.removesuffix("_setpoint")


def _return_values(hint: Any) -> tuple[ValueSpec, ...] | None:  # noqa: ANN401  # any annotation object
    """The value specs of what a command answers; () for -> None, None where it is not annotated."""
    if hint is None or hint is type(None):
        return ()
    spec_hint = hint
    if get_origin(spec_hint) is Annotated:
        spec_hint = get_args(spec_hint)[0]
    if get_origin(spec_hint) is tuple:
        members = get_args(spec_hint)
        if members and members[-1] is not Ellipsis:
            return tuple(value_spec(m) for m in members)
    return (value_spec(hint),)


def _guess_returns(name: str, count: int) -> tuple[str, ...]:
    """Quantity names guessed from a reader name, or [0], [1], ... where they cannot be."""
    base = _quantity_of_name(name)
    if count == 1:
        return (base,)
    parts = base.split("_and_")
    if len(parts) == count:
        return tuple(parts)
    return tuple(f"{base}[{index}]" for index in range(count))


def _uses_command(device: EmptyDevice) -> bool:
    """Whether any method of the driver class, inherited ones included, carries @command."""
    cls = type(device)
    return any(command_info(getattr(cls, name, None)) is not None for name in dir(cls) if not name.startswith("_"))


def _command_names(device: EmptyDevice) -> list[str]:
    """The communication commands: the decorated methods, or every own public method where none is decorated."""
    if _uses_command(device):
        cls = type(device)
        return sorted(name for name in dir(cls) if not name.startswith("_") and command_info(getattr(cls, name)))
    return sorted(device.list_functions())


def describe_command(device: EmptyDevice, name: str) -> CommandSpec | None:  # noqa: C901
    """Describe one communication command of a driver instance; None if it is not a method."""
    method = getattr(device, name, None)
    if method is None or not callable(method):
        return None
    info = command_info(method)
    function = inspect.unwrap(method)
    try:
        signature = _signature(function)
    except (TypeError, ValueError):
        return None
    hints = _hints(function, _defining_namespace(type(device), function))
    description = description_of(function)

    parameters = []
    for parameter in signature.parameters.values():
        if parameter.name == "self" or parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        required = parameter.default is inspect.Parameter.empty
        parameters.append(
            ParameterSpec(
                name=parameter.name,
                value=value_spec(hints[parameter.name]) if parameter.name in hints else ValueSpec(),
                required=required,
                default=None if required else parameter.default,
                is_channel=parameter.name in CHANNEL_PARAMETERS,
            ),
        )
    value_parameters = [p for p in parameters if not p.is_channel]

    return_values = _return_values(hints["return"]) if "return" in hints else None
    if info is not None:
        # Declared: everything comes from @command and the signature, nothing from the name.
        kind = info.kind
        returns = info.returns or ()
        reads = info.reads
    else:
        # Undeclared (an older driver): what the annotations do not say is guessed from the name.
        if return_values is None:
            kind = (
                "read"
                if name.startswith(("get_", "is_", "measure_", "read_", "fetch_"))
                else ("set" if name.startswith("set_") else "run")
            )
        elif return_values:
            kind = "read"
        else:
            kind = "set" if value_parameters else "run"
        returns = _guess_returns(name, len(return_values) if return_values else 1) if kind == "read" else ()
        reads = _guess_reads(name) if kind == "read" else None

    quantity = None
    if kind == "set" and len(value_parameters) == 1:
        quantity = value_parameters[0].name
    elif kind == "read" and len(returns) == 1:
        quantity = returns[0]

    labels = {p.name: p.value.label or derived_label(p.name) for p in value_parameters}
    for index, quantity_name in enumerate(returns):
        spec = return_values[index] if return_values and index < len(return_values) else None
        labels[quantity_name] = (spec.label if spec else None) or derived_label(quantity_name)

    return CommandSpec(
        name=name,
        description=description,
        hazards=info.hazards if info else (),
        parameters=tuple(parameters),
        kind=kind,
        returns=returns,
        return_values=return_values or (),
        reads=reads,
        composite=bool(info and info.composite),
        declared=info is not None,
        quantity=quantity,
        labels=labels,
    )


def describe_commands(device: EmptyDevice) -> list[CommandSpec]:
    """Describe the communication commands of a driver instance, in name order.

    A driver whose methods carry @command has exactly the decorated methods as commands, described by @command and
    their annotations alone. A driver without @command (an older one) has every public method it defines beyond
    EmptyDevice as a command (`EmptyDevice.list_functions`), and what its annotations do not say is guessed from the
    method name.
    """
    specs = []
    for name in _command_names(device):
        spec = describe_command(device, name)
        if spec is not None:
            specs.append(spec)
    return specs
