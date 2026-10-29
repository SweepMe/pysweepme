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

import ast
import collections.abc
import contextlib
import functools
import inspect
import math
import numbers
import sys
import textwrap
import types
import warnings
import weakref
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from pathlib import Path
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
    from collections.abc import Callable, Iterator, Sequence

    from .EmptyDeviceClass import EmptyDevice

__all__ = [
    "CommandError",
    "CommandInfo",
    "CommandNotice",
    "CommandSpec",
    "Label",
    "ParameterSpec",
    "Range",
    "Selector",
    "Unit",
    "ValueSpec",
    "collecting_notices",
    "command",
    "describe_commands",
    "notice",
    "selector_overlaps",
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


@dataclass(frozen=True, kw_only=True)
class Selector:
    """Marks a parameter that addresses a part of the instrument - a channel, a slot, a pin - rather than a value.

    Written on the parameter's alias like the other markers: `Channel = Annotated[int, Selector(), Range(1, 2)]`. A
    selector is no value: `enable_output(channel: Channel) -> None` runs, and a setter's quantity is its other
    parameter. In a driver using @command only marked parameters are selectors; in a driver without it, a parameter
    named `channel` is the one selector, as before.

    `Selector(stateful=True)` marks a selector the instrument keeps as a selection (`INST:OUT2`, then `VOLT 5`). The
    driver selects it in `apply_selectors`, and @command calls that only when the selection changes; the selection is
    remembered on the Port, so every driver instance on it knows it.

    `Selector(overlaps={"TRACK25V": ("+25V", "-25V")})` names values that reach the same hardware as other values
    (tracking drives both 25 V outputs; on a LabJack T4, AIN4 is FIO4). The relation is symmetric and not transitive:
    TRACK25V overlaps +25V and -25V, which stay apart. Where it depends on the model, `overlaps="pin_overlaps"` names a
    method of the driver answering the mapping for the connected instrument, or None while it is not known.

    Its options are keyword-only, so that one added later cannot shift the meaning of an existing driver's call.
    """

    stateful: bool = False
    #: Values that reach the same hardware, {value: (other values, ...)}, or the name of a method answering that.
    overlaps: Overlaps | str | None = None

    def __post_init__(self) -> None:
        """Keep a mapping of overlaps as a tuple of pairs, so the marker stays immutable and hashable."""
        if self.overlaps is not None and not isinstance(self.overlaps, str):
            object.__setattr__(self, "overlaps", freeze_overlaps(self.overlaps))


#: Overlaps as a Selector keeps them: ((value, (other values, ...)), ...).
Overlaps = tuple[tuple[Any, tuple[Any, ...]], ...]


def freeze_overlaps(overlaps: object) -> Overlaps:
    """A mapping {value: other value or values} as the tuple of pairs a Selector keeps; TypeError if it is none."""
    if isinstance(overlaps, collections.abc.Mapping):
        items = list(overlaps.items())
    elif isinstance(overlaps, tuple):  # kept as pairs already: a copy of a marker
        items = list(overlaps)
    else:
        msg = f"Selector overlaps must be a mapping {{value: (other values, ...)}} or a method name, not {overlaps!r}."
        raise TypeError(msg)
    frozen = []
    for value, others in items:
        listed = (
            (others,)
            if isinstance(others, (str, bytes)) or not isinstance(others, collections.abc.Iterable)
            else tuple(others)
        )
        frozen.append((value, listed))
    return tuple(frozen)


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


@dataclass(frozen=True, kw_only=True)
class CommandInfo:
    """What @command declares about a command as a whole (keyword-only, like every spec here: fields can be added)."""

    returns: tuple[str, ...] | None = None
    reads: str | None = None
    composite: bool = False
    hazards: tuple[str, ...] = ()
    #: "read" (a return annotation other than None) or "run" (stated with kind="run") when decorated; "" otherwise:
    #: set or run then follows from whether a value parameter remains besides the selectors, which are only known
    #: once their aliases resolve - describe_command decides it.
    kind: str = ""


@dataclass(frozen=True, kw_only=True)
class ValueSpec:
    """Everything the annotation says about one value: type, choices, unit, label and range."""

    type: Any = None
    optional: bool = False
    choices: tuple[Any, ...] | None = None
    unit: str | None = None
    label: str | None = None
    range: Range | None = None
    #: For a list, a variadic tuple or a Sequence: the spec of each element (`list[Literal["AIN0", "AIN1"]]`).
    items: ValueSpec | None = None
    #: Marked Selector(): the value addresses a part of the instrument.
    selector: bool = False
    #: Marked Selector(stateful=True): the instrument keeps it as a selection, which @command makes when it changes.
    stateful: bool = False
    #: Selector(overlaps=...): values reaching the same hardware as other values, or the method answering them.
    overlaps: Overlaps | str | None = None

    @property
    def type_name(self) -> str:
        """The plain type name, e.g. "float", or "" where the annotation gives none."""
        if self.choices is not None:
            return "str" if all(isinstance(c, str) for c in self.choices) else "literal"
        return getattr(self.type, "__name__", "") if self.type is not None else ""


@dataclass(frozen=True, kw_only=True)
class ParameterSpec:
    """One parameter of a command."""

    name: str
    value: ValueSpec
    required: bool
    default: Any = None
    #: It addresses a part of the instrument (Selector(); in a driver without @command a parameter named channel).
    selector: bool = False


@dataclass(frozen=True, kw_only=True)
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
    #: For a composite: the commands it calls, read from its code (hazards then holds theirs as well).
    calls: tuple[str, ...] = ()
    #: The names of the parameters that are selectors, in signature order.
    selectors: tuple[str, ...] = ()


# --- annotations -------------------------------------------------------------------------------------------------


def _is_union(hint: Any) -> bool:  # noqa: ANN401  # any annotation object
    """Whether the hint is a Union or an X | Y union."""
    return get_origin(hint) in (Union, types.UnionType)


def value_spec(hint: Any) -> ValueSpec:  # noqa: ANN401  # any annotation object
    """Split an annotation into type, Literal choices and the Unit, Label, Range and Selector markers."""
    unit = label = None
    value_range = None
    selector = stateful = False
    overlaps: Overlaps | str | None = None
    if get_origin(hint) is Annotated:
        hint, *metadata = get_args(hint)
        for item in metadata:
            if isinstance(item, Unit):
                unit = item.symbol
            elif isinstance(item, Label):
                label = item.text
            elif isinstance(item, Range):
                value_range = item
            elif isinstance(item, Selector):
                selector, stateful, overlaps = True, item.stateful, item.overlaps
    optional = False
    if _is_union(hint):
        members = [m for m in get_args(hint) if m is not type(None)]
        optional = len(members) < len(get_args(hint))
        if len(members) == 1:
            inner = value_spec(members[0])
            return ValueSpec(
                type=inner.type,
                optional=optional,
                choices=inner.choices,
                unit=unit or inner.unit,
                label=label or inner.label,
                range=value_range or inner.range,
                items=inner.items,
                selector=selector or inner.selector,
                stateful=stateful or inner.stateful,
                overlaps=overlaps if overlaps is not None else inner.overlaps,
            )
        hint = None
    choices = tuple(get_args(hint)) if get_origin(hint) is Literal else None
    return ValueSpec(
        type=None if choices is not None else hint,
        optional=optional,
        choices=choices,
        unit=unit,
        label=label,
        range=value_range,
        items=_item_spec(hint),
        selector=selector,
        stateful=stateful,
        overlaps=overlaps,
    )


#: The containers whose elements a ValueSpec describes with `items`.
SEQUENCE_ORIGINS = (list, tuple, collections.abc.Sequence)


def _item_spec(hint: Any) -> ValueSpec | None:  # noqa: ANN401  # any annotation object
    """The spec of each element of `list[X]`, `tuple[X, ...]` or `Sequence[X]`; None for anything else."""
    if get_origin(hint) not in SEQUENCE_ORIGINS:
        return None
    members = get_args(hint)
    if get_origin(hint) is tuple:
        return value_spec(members[0]) if len(members) == 2 and members[1] is Ellipsis else None  # noqa: PLR2004
    return value_spec(members[0]) if len(members) == 1 else None


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
    """The choice a value stands for: a text choice written exactly, a number choice also given as text.

    Text is never adjusted - "fvmi" is not "FVMI" (decided 2026-10-27 after review: a clear error rather than a
    silent correction, and two modes may differ in case only). What is converted is the type: "2" or 2.0 stand for
    the choice 2, and 2 for the choice "2".
    """
    for choice in choices:
        if value == choice and type(value) is type(choice):
            return True, choice
    for choice in choices:
        if isinstance(choice, bool) or isinstance(value, bool):
            continue  # True is not 1, and "True" is no number
        if isinstance(choice, numbers.Real):
            number = _to_float(value)
            if number is not None and number == choice:
                return True, choice
        elif isinstance(choice, str) and isinstance(value, numbers.Real) and str(value) == choice:
            return True, choice
    return False, None


def _near_choice(value: object, choices: tuple[Any, ...]) -> str:
    """A hint for a text that misses a choice only in case or outer spaces: " Did you mean 'FVMI'?", else ""."""
    if not isinstance(value, str):
        return ""
    text = value.strip().casefold()
    near = [choice for choice in choices if isinstance(choice, str) and choice.strip().casefold() == text]
    return f" Did you mean {near[0]!r}?" if len(near) == 1 else ""


def check_value(command_name: str, parameter: str, value: object, spec: ValueSpec) -> Any:  # noqa: ANN401
    """Check and convert one argument against its annotation; raise ValueError if it does not fit."""
    if value is None and spec.optional:
        return None
    if spec.items is not None:
        return _check_items(command_name, parameter, value, spec.items)
    if spec.choices is not None:
        choice = _check_choice(command_name, parameter, value, spec.choices)
        _check_range(command_name, parameter, choice, spec)
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
        _check_range(command_name, parameter, number, spec)
        return number
    _check_range(command_name, parameter, value, spec)
    return value


def _check_range(command_name: str, parameter: str, value: object, spec: ValueSpec) -> None:
    """Refuse a number outside the spec's Range (inclusive); anything that is no number is not range-checked."""
    if spec.range is None or isinstance(value, bool) or not isinstance(value, numbers.Real):
        return
    if not spec.range.contains(float(value)):
        unit = f" {spec.unit}" if spec.unit else ""
        raise _fail(command_name, parameter, value, f"is outside {spec.range}{unit}.")


def _check_choice(command_name: str, parameter: str, value: object, choices: tuple[Any, ...]) -> Any:  # noqa: ANN401
    """The choice a value stands for; a ValueError naming the choices, and the right spelling of a near miss."""
    found, choice = _match_choice(value, choices)
    if not found:
        allowed = ", ".join(str(c) for c in choices)
        raise _fail(command_name, parameter, value, f"is not one of {allowed}.{_near_choice(value, choices)}")
    return choice


def _checks_something(spec: ValueSpec) -> bool:
    """Whether check_value would check or convert anything for this spec."""
    return (
        spec.choices is not None or spec.type in (bool, int, float) or spec.range is not None or spec.items is not None
    )


def _check_items(command_name: str, parameter: str, value: object, items: ValueSpec) -> Any:  # noqa: ANN401
    """Check every element of a list argument; a list or tuple comes back converted.

    A NumPy array is handed on as it is, so an element that would need converting (an array of texts for a number) is
    refused rather than passed on unconverted; pysweepme does not import NumPy to build a converted one.
    """
    if isinstance(value, (str, bytes)) or not (isinstance(value, (list, tuple)) or hasattr(value, "tolist")):
        raise _fail(command_name, parameter, value, "is not a list.")
    if not _checks_something(items):
        return value
    if not isinstance(value, (list, tuple)):
        flat = value.ravel() if hasattr(value, "ravel") else value  # an array
        for index, item in enumerate(flat.tolist()):
            if check_value(command_name, f"{parameter}[{index}]", item, items) != item:
                raise _fail(
                    command_name,
                    f"{parameter}[{index}]",
                    item,
                    "would need converting: pass a list, or an array of the annotated type.",
                )
        return value
    checked = [check_value(command_name, f"{parameter}[{index}]", item, items) for index, item in enumerate(value)]
    return tuple(checked) if isinstance(value, tuple) else checked


# --- @command ----------------------------------------------------------------------------------------------------


def _checked(func: F) -> F:
    """Wrap a method so that its arguments are checked against their annotations on every call."""
    signature = _signature(func)
    receiver = next(iter(signature.parameters), None)  # "self" of a method
    specs: dict[str, ValueSpec] | None = None

    def parameter_specs(bound: inspect.BoundArguments) -> dict[str, ValueSpec]:
        """The value specs of the parameters, resolved at the first call, when the driver module is complete.

        The instance tells which class defines the command, for its class-local aliases. It is taken from the bound
        arguments, so that a call passing it by keyword (`Base.set_level(self=device, level=5)`) resolves them too.
        """
        nonlocal specs
        if specs is None:
            instance = bound.arguments.get(receiver) if receiver is not None else None
            localns = _defining_namespace(type(instance), func) if instance is not None else None
            hints = _hints(func, localns)
            specs = {
                name: value_spec(hints[name])
                for name, parameter in signature.parameters.items()
                if name in hints
                and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            }
        return specs

    def call(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # the command's own return value
        """Check the given arguments, select a stateful selector where it changed, then call the command."""
        bound = signature.bind(*args, **kwargs)
        checks = parameter_specs(bound)
        if checks:
            for name, value in bound.arguments.items():
                if name in checks:
                    bound.arguments[name] = check_value(func.__name__, name, value, checks[name])
            wanted = {
                name: value for name, value in bound.arguments.items() if name in checks and checks[name].stateful
            }
            if wanted and receiver is not None:
                _select(bound.arguments[receiver], wanted)
            return func(*bound.args, **bound.kwargs)
        return func(*args, **kwargs)

    return _keeping_notices(func, call, receiver)


def _keeping_notices(func: F, call: Callable[..., Any], receiver: str | None) -> F:
    """The command as its callers see it: the outermost call of a context keeps its notices in the device's notices."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # the command's own return value
        """Call the command, keeping the notices of an outermost call for the device's `notices`."""
        if _CALL_NOTICES.get() is not None:
            return call(*args, **kwargs)  # called by a composite: its notices are the composite's
        notices: list[str] = []
        token = _CALL_NOTICES.set(notices)
        try:
            return call(*args, **kwargs)
        finally:
            _CALL_NOTICES.reset(token)
            instance = args[0] if args else kwargs.get(receiver) if receiver is not None else None
            if instance is not None:
                with contextlib.suppress(AttributeError):  # a driver class that refuses new attributes
                    instance.notices = tuple(notices)

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

    Every argument is keyword-only with a default that means "not declared": one added later keeps today's behavior
    for the drivers that do not use it.
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
        returns=tuple(returns) if returns is not None else None,
        reads=reads,
        composite=bool(composite),
        hazards=_hazards(hazards),
        kind=kind or "",
    )

    def decorate(method: F) -> F:
        """Check the declaration, wrap the method, attach the metadata and show the hazards in the docstring."""
        if isinstance(method, (staticmethod, classmethod, property)):
            msg = (
                f"@command {type(method).__name__}: a command is a plain instance method (def name(self, ...)), "
                f"called on the driver - not a {type(method).__name__}."
            )
            raise TypeError(msg)
        info = _completed(method, declared)
        wrapped = _checked(method)
        setattr(wrapped, COMMAND_ATTRIBUTE, info)
        if info.hazards:
            wrapped.__doc__ = _with_hazards(method.__doc__, info.hazards)
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


def _check_parameters(name: str, method: Callable[..., Any]) -> None:
    """Refuse parameters a call by name cannot fill: positional-only ones and *args/**kwargs."""
    for index, parameter in enumerate(_signature(method).parameters.values()):
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY and index > 0:
            msg = (
                f"@command {name}: {parameter.name} is positional-only (before /) and cannot be passed by name "
                f"(an agent or a tile calls commands with named arguments); remove the /."
            )
            raise TypeError(msg)
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            stars = "*" if parameter.kind is inspect.Parameter.VAR_POSITIONAL else "**"
            msg = (
                f"@command {name}: {stars}{parameter.name} cannot be passed by name (an agent or a tile calls "
                f"commands with named arguments); take a list or named parameters instead."
            )
            raise TypeError(msg)


def _completed(method: Callable[..., Any], declared: CommandInfo) -> CommandInfo:
    """Check what a declared command must state and complete it with its kind and the default of reads.

    In a declared driver nothing is guessed from method names: a command needs a return annotation, a reader needs
    the quantity names of its answer in returns, and a reader reads a measurement unless reads says otherwise.
    """
    name = getattr(method, "__name__", repr(method))
    _check_parameters(name, method)
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
    return declared  # kind "run" if stated, else set or run by its parameters, decided by describe_command


def _hazards(hazards: str | Sequence[str] | None) -> tuple[str, ...]:
    """The hazards as a tuple of non-empty texts; refuse anything that is not text."""
    if hazards is None:
        return ()
    items = (hazards,) if isinstance(hazards, str) else tuple(hazards)
    if not all(isinstance(item, str) for item in items):
        msg = "@command hazards must be a text or a sequence of texts."
        raise TypeError(msg)
    return tuple(text for item in items if (text := " ".join(item.split())))


def _with_hazards(doc: str | None, hazards: Sequence[str]) -> str:
    """A docstring with the hazards as a "Hazards:" section at its end, so that help() shows them."""
    section = "\n".join(f"    {hazard}" for hazard in hazards)
    return f"{inspect.cleandoc(doc or '')}\n\nHazards:\n{section}".lstrip()


def command_info(method: object) -> CommandInfo | None:
    """The @command metadata of a method or function, None if it is not decorated."""
    info = getattr(method, COMMAND_ATTRIBUTE, None)
    return info if isinstance(info, CommandInfo) else None


# --- errors and notices ------------------------------------------------------------------------------------------


class CommandError(RuntimeError):
    """A command that could not do what it was asked, with the code of the instrument or its library where it has one.

    `raise CommandError("The stage is busy.", code=38)`: a script branches on `error.code`, Instrument Control records
    it. The message says what went wrong; the code is kept apart, so that it is not said twice.
    """

    def __init__(self, message: str = "", *, code: int | str | None = None) -> None:
        """Keep the message as the exception's text and the code beside it."""
        super().__init__(message)
        self.code = code


class CommandNotice(UserWarning):
    """The warning a notice raises when nobody collects notices: a script's console shows it."""


#: The lists every notice of this context is appended to (collecting_notices), innermost last.
_COLLECTORS: ContextVar[tuple[list[str], ...]] = ContextVar("pysweepme_notice_collectors", default=())
#: The notices of the outermost command call running in this context, for its device's `notices`.
_CALL_NOTICES: ContextVar[list[str] | None] = ContextVar("pysweepme_call_notices", default=None)


@contextlib.contextmanager
def collecting_notices() -> Iterator[list[str]]:
    """Collect the notices raised inside the block, across commands and driver instances, in the list it yields.

    A ContextVar keeps it per thread and per call. While a collector is active, a notice raises no warning; nested
    collectors each get every notice of their block.
    """
    notices: list[str] = []
    token = _COLLECTORS.set((*_COLLECTORS.get(), notices))
    try:
        yield notices
    finally:
        _COLLECTORS.reset(token)


def notice(text: str) -> None:
    """Report that a command did what it was asked, with something a person should know.

    The text goes to the running command call (the device's `notices`) and to every active collector; with no
    collector a CommandNotice warning shows it, at the line of the script that called the command. EmptyDevice.notice
    is the driver's way to call it.
    """
    text = str(text)
    call = _CALL_NOTICES.get()
    if call is not None:
        call.append(text)
    collectors = _COLLECTORS.get()
    for collected in collectors:
        collected.append(text)
    if not collectors:
        warnings.warn(text, CommandNotice, stacklevel=_caller_level())


#: pysweepme's own folder: its frames are skipped when a notice warning looks for the caller.
_PACKAGE_FOLDER = Path(__file__).resolve().parent


def _caller_level() -> int:
    """The stacklevel, seen from notice(), of the first frame outside pysweepme and the driver that gave the notice.

    That is the script line that called the command, which is what its author needs; without one (the driver itself
    is the top of the stack), the driver's line.
    """

    def inside(frame: types.FrameType, place: Path) -> bool:
        """Whether the frame's code lies in this folder or is this file."""
        return Path(frame.f_code.co_filename).resolve().is_relative_to(place)

    frame: types.FrameType | None = sys._getframe(2)  # noqa: SLF001  # notice's caller, its stacklevel 2
    level = 2
    while frame is not None and inside(frame, _PACKAGE_FOLDER):
        frame, level = frame.f_back, level + 1
    if frame is None:
        return 2
    driver_file, driver_level = Path(frame.f_code.co_filename).resolve(), level
    while frame is not None and (inside(frame, _PACKAGE_FOLDER) or inside(frame, driver_file)):
        frame, level = frame.f_back, level + 1
    return level if frame is not None else driver_level


# --- what a composite calls --------------------------------------------------------------------------------------

#: Per driver class, the commands each composite calls - read from the code once.
_CALLS: weakref.WeakKeyDictionary[type, dict[str, tuple[str, ...]]] = weakref.WeakKeyDictionary()


def _self_calls(function: Callable[..., Any]) -> list[str]:
    """The methods a function calls on its instance (`self.<name>(...)`), in source order; [] without its source."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(function))))
    except (OSError, TypeError, SyntaxError):
        return []
    definition = tree.body[0] if tree.body else None
    if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)) or not definition.args.args:
        return []
    instance = definition.args.args[0].arg
    calls = [
        node
        for node in ast.walk(definition)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == instance
    ]
    calls.sort(key=lambda node: (node.lineno, node.col_offset))
    return list(dict.fromkeys(node.func.attr for node in calls))  # type: ignore[attr-defined]  # checked above


def _defined_by_driver(cls: type, name: str) -> bool:
    """Whether the driver defines this method itself (or a driver base class does), not EmptyDevice or object."""
    from .EmptyDeviceClass import EmptyDevice  # noqa: PLC0415  # EmptyDeviceClass imports this module lazily too

    owner = next((klass for klass in cls.__mro__ if name in vars(klass)), None)
    return owner is not None and owner is not object and not issubclass(EmptyDevice, owner)


def calls_of(cls: type, name: str) -> tuple[str, ...]:
    """The commands a command calls, read from its code: helpers of the driver are followed, a command stops the walk.

    Only `self.<name>(...)` calls are seen - not a call through getattr, nor one into a function outside the driver
    class, nor raw port traffic. Without readable source the answer is ().
    """
    known = _CALLS.setdefault(cls, {})
    if name in known:
        return known[name]
    found: list[str] = []
    seen = {name}

    def walk(method: Callable[..., Any]) -> None:
        """Into a helper where it is called, so the commands come in the order they are called."""
        for called in _self_calls(method):
            if called in seen:
                continue
            seen.add(called)
            member = getattr(cls, called, None)
            if command_info(member) is not None:
                found.append(called)
            elif callable(member) and _defined_by_driver(cls, called):
                walk(member)

    method = getattr(cls, name, None)
    if callable(method):
        walk(method)
    known[name] = tuple(found)
    return known[name]


def _hazard_origins(cls: type, name: str, stack: frozenset[str]) -> list[tuple[str, str]]:
    """(command, hazard) for a command's own hazards and, for a composite, those of every command it calls."""
    info = command_info(getattr(cls, name, None))
    if info is None:
        return []
    pairs = [(name, hazard) for hazard in info.hazards]
    if info.composite:
        for called in calls_of(cls, name):
            if called in stack:
                continue  # a cycle: what it brings is already being collected
            for pair in _hazard_origins(cls, called, stack | {called}):
                if pair not in pairs:
                    pairs.append(pair)
    return pairs


def hazards_of(cls: type, name: str) -> tuple[str, ...]:
    """A command's hazards: its own, then those a composite inherits, each prefixed with the command it comes from."""
    return tuple(
        hazard if origin == name else f"{origin}: {hazard}"
        for origin, hazard in _hazard_origins(cls, name, frozenset({name}))
    )


def check_selector_defaults(cls: type) -> None:
    """Refuse a default on a selector of a command the driver class defines.

    A call leaving it out would silently address whichever subunit the default names. Called by
    EmptyDevice.__init_subclass__: the selector aliases, class-local ones included, resolve only once the class body
    ran.
    """
    for name, member in vars(cls).items():
        if command_info(member) is None:
            continue
        function = inspect.unwrap(member)
        hints = _hints(function, dict(vars(cls)))
        for parameter in _signature(function).parameters.values():
            if (
                parameter.default is not inspect.Parameter.empty
                and parameter.name in hints
                and value_spec(hints[parameter.name]).selector
            ):
                msg = (
                    f"@command {name}: the selector {parameter.name} takes no default - a call that leaves it out "
                    f"would silently address whichever {parameter.name} the default names."
                )
                raise TypeError(msg)


# --- selections kept by the instrument ----------------------------------------------------------------------------

#: The class attribute holding a driver class's stateful selectors, {name: ValueSpec}; set when the class is created.
STATEFUL_ATTRIBUTE = "_stateful_selectors"
#: Marks an apply_selectors that remembers what it selected.
REMEMBERS_ATTRIBUTE = "__pysweepme_remembers_selection__"


def stateful_selectors(cls: type) -> dict[str, ValueSpec]:
    """The selectors the commands of a driver class mark Selector(stateful=True), by name, base classes included."""
    found: dict[str, ValueSpec] = {}
    for klass in reversed(cls.__mro__):
        for member in vars(klass).values():
            if command_info(member) is None:
                continue
            function = inspect.unwrap(member)
            for name, hint in _hints(function, dict(vars(klass))).items():
                spec = value_spec(hint)
                if spec.stateful:
                    found[name] = spec
    return found


def prepare_stateful_selectors(cls: type) -> None:
    """Record the class's stateful selectors and make its apply_selectors remember what it selects.

    Called by EmptyDevice.__init_subclass__. A stateful selector the class's apply_selectors cannot take is refused:
    the selection could never be made.
    """
    stateful = stateful_selectors(cls)
    setattr(cls, STATEFUL_ATTRIBUTE, stateful)
    if not stateful:
        return
    names = ", ".join(sorted(stateful))
    hook = inspect.getattr_static(cls, "apply_selectors", None)
    if not callable(hook) or getattr(hook, "__qualname__", "") == "EmptyDevice.apply_selectors":
        msg = f"{cls.__name__}: the stateful selector(s) {names} need apply_selectors({names}) to select them."
        raise TypeError(msg)
    parameters = _signature(hook).parameters
    takes_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    missing = sorted(name for name in stateful if name not in parameters and not takes_any)
    if missing:
        msg = (
            f"{cls.__name__}: the stateful selector(s) {', '.join(missing)} are selected in apply_selectors, which "
            f"does not take them - define apply_selectors({names}) and select there."
        )
        raise TypeError(msg)
    if not getattr(hook, REMEMBERS_ATTRIBUTE, False):
        setattr(cls, "apply_selectors", _remembering(hook))  # noqa: B010  # a method replaced on the class


# --- values reaching the same hardware ----------------------------------------------------------------------------


def selector_specs(cls: type) -> dict[str, list[tuple[str, ValueSpec]]]:
    """The selectors the commands of a driver class take, by name: (command, spec) per command, base classes too."""
    found: dict[str, dict[str, ValueSpec]] = {}
    for klass in reversed(cls.__mro__):
        for command_name, member in vars(klass).items():
            if command_info(member) is None:
                continue
            function = inspect.unwrap(member)
            for name, hint in _hints(function, dict(vars(klass))).items():
                spec = value_spec(hint)
                if spec.selector:
                    found.setdefault(name, {})[command_name] = spec
    return {name: list(uses.items()) for name, uses in found.items()}


def check_selector_overlaps(cls: type) -> None:
    """Refuse overlaps a driver class declares wrongly; a class whose selectors declare none is not looked at.

    Called by EmptyDevice.__init_subclass__. Every command takes the selector with the same overlaps, every value
    named is one the selector takes and none overlaps itself, and a method named instead exists on the class.
    """
    for name, uses in selector_specs(cls).items():
        declared = {spec.overlaps for _, spec in uses}
        if declared == {None}:
            continue
        if len(declared) > 1:
            commands = ", ".join(sorted(command_name for command_name, _ in uses))
            msg = (
                f"{cls.__name__}: the selector {name} is declared with different overlaps in {commands} - use one "
                f"alias for it in every command."
            )
            raise TypeError(msg)
        spec = uses[0][1]
        overlaps = spec.overlaps
        if isinstance(overlaps, str):
            if not callable(getattr(cls, overlaps, None)):
                msg = f"{cls.__name__}: the selector {name} names the method {overlaps} for its overlaps, which is "
                msg += "missing."
                raise TypeError(msg)
            continue
        named = [listed for value, others in overlaps or () for listed in (value, *others)]
        try:
            for listed in named:
                check_value("Selector overlaps", name, listed, replace(spec, optional=False))
        except ValueError as exc:
            msg = f"{cls.__name__}: {exc}"
            raise TypeError(msg) from None
        for value, others in overlaps or ():
            if value in others:
                msg = f"{cls.__name__}: the selector {name} lists {value!r} as overlapping itself."
                raise TypeError(msg)


def selector_overlaps(device: Any, spec: ValueSpec) -> dict[Any, tuple[Any, ...]] | None:  # noqa: ANN401
    """The values of a selector that reach the same hardware, both ways round: {value: (other values, ...)}.

    {} for a selector that declares none. Where it names a method, the driver instance is asked each time, since the
    answer may depend on the instrument connected (its model); None when the method does not know yet.
    """
    overlaps = spec.overlaps
    if isinstance(overlaps, str):
        answer = getattr(device, overlaps)()
        if answer is None:
            return None
        overlaps = freeze_overlaps(answer)
    both: dict[Any, list[Any]] = {}
    for value, others in overlaps or ():
        for other in others:
            if other not in both.setdefault(value, []):
                both[value].append(other)
            if value not in both.setdefault(other, []):
                both[other].append(value)
    return {value: tuple(others) for value, others in both.items()}


def _remembering(hook: Callable[..., Any]) -> Callable[..., Any]:
    """apply_selectors, remembering the stateful selections it made - or forgetting them all if it failed half way."""
    signature = _signature(hook)

    @functools.wraps(hook)
    def apply_selectors(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # the hook's own result
        try:
            result = hook(self, *args, **kwargs)
        except BaseException:
            forget_selections(self)
            raise
        given: dict[str, Any] = {}
        for name, value in signature.bind(self, *args, **kwargs).arguments.items():
            if signature.parameters[name].kind is inspect.Parameter.VAR_KEYWORD:
                given.update(value)
            else:
                given[name] = value
        stateful = getattr(type(self), STATEFUL_ATTRIBUTE, {})
        made = {
            name: check_value("apply_selectors", name, value, stateful[name])
            for name, value in given.items()
            if name in stateful
        }
        if made:
            _remember(self, made)
        return result

    setattr(apply_selectors, REMEMBERS_ATTRIBUTE, True)
    return apply_selectors


def _owner(device: Any) -> str:  # noqa: ANN401  # any driver instance
    """Who made a selection: the driver's file and class - another driver on the same port means another meaning."""
    cls = type(device)
    module = sys.modules.get(cls.__module__)
    return f"{getattr(module, '__file__', '') or cls.__module__}:{cls.__qualname__}"


def _holder(device: Any) -> Any:  # noqa: ANN401  # a Port, or the driver instance itself
    """Where the selection is kept: the Port, shared by every instance on the resource; without one the instance."""
    port = getattr(device, "port", None)
    return port if port is not None and callable(getattr(port, "remember_selection", None)) else device


def current_selection(device: Any) -> dict[str, Any]:  # noqa: ANN401  # any driver instance
    """What the instrument has selected, as far as this driver knows: {} when unknown or selected by another driver."""
    holder = _holder(device)
    if holder is device:
        record = getattr(device, "_selection", None)
        return dict(record[1]) if record and record[0] == _owner(device) else {}
    selection: dict[str, Any] = holder.selection(_owner(device))
    return selection


def _remember(device: Any, values: dict[str, Any]) -> None:  # noqa: ANN401  # any driver instance
    holder = _holder(device)
    if holder is device:
        known = current_selection(device)
        device._selection = (_owner(device), {**known, **values})  # noqa: SLF001  # the memory of a portless driver
    else:
        holder.remember_selection(_owner(device), values)


def forget_selections(device: Any) -> None:  # noqa: ANN401  # any driver instance
    """Forget what the instrument has selected: the next command selects again."""
    holder = _holder(device)
    if holder is device:
        device._selection = None  # noqa: SLF001  # the memory of a portless driver
    else:
        holder.forget_selections()


def _select(device: Any, wanted: dict[str, Any]) -> None:  # noqa: ANN401  # any driver instance
    """Have the driver select what a command needs, unless the instrument has it selected already."""
    current = current_selection(device)
    changed = {name: value for name, value in wanted.items() if name not in current or current[name] != value}
    if changed:
        device.apply_selectors(**changed)


def declares_commands(cls: type) -> bool:
    """Whether the class or one of its bases has a method decorated with @command.

    EmptyDevice.__init_subclass__ runs the checks of a declared driver only where this is true, so a driver without
    @command - most drivers - is created exactly as before, whatever checks are added later.
    """
    return any(command_info(member) is not None for klass in cls.__mro__ for member in vars(klass).values())


def check_command_overrides(cls: type) -> None:
    """Refuse a method that overrides a command of a base class without @command: the command would silently vanish.

    Called by EmptyDevice.__init_subclass__, when the driver class is created.
    """
    for name, member in vars(cls).items():
        if name.startswith("_") or command_info(member) is not None:
            continue
        for base in cls.__mro__[1:]:
            if name in vars(base):
                if command_info(vars(base)[name]) is not None:
                    msg = (
                        f"{cls.__name__}.{name} overrides the command {base.__name__}.{name} without @command: "
                        f"decorate the override too, or it is no command any more."
                    )
                    raise TypeError(msg)
                break


def complete_hazard_sections(cls: type) -> None:
    """Show the inherited hazards in the docstrings of the composites a driver class defines.

    Called by EmptyDevice.__init_subclass__: only once the class body ran are the commands a composite calls there.
    """
    for name, member in vars(cls).items():
        info = command_info(member)
        if info is None or not info.composite:
            continue
        hazards = hazards_of(cls, name)
        if hazards != info.hazards:
            member.__doc__ = _with_hazards(inspect.unwrap(member).__doc__, hazards)


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

    parameters: list[ParameterSpec] = []
    for parameter in signature.parameters.values():
        if parameter.name == "self" or parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        required = parameter.default is inspect.Parameter.empty
        value = value_spec(hints[parameter.name]) if parameter.name in hints else ValueSpec()
        parameters.append(
            ParameterSpec(
                name=parameter.name,
                value=value,
                required=required,
                default=None if required else parameter.default,
                # Declared: only what is marked. Undeclared: also the one selector known by its name.
                selector=value.selector or (info is None and parameter.name in CHANNEL_PARAMETERS),
            ),
        )
    value_parameters = [p for p in parameters if not p.selector]

    return_values = _return_values(hints["return"]) if "return" in hints else None
    if info is not None:
        # Declared: everything comes from @command and the signature, nothing from the name.
        kind = info.kind or ("set" if value_parameters else "run")
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
        hazards=hazards_of(type(device), name) if info else (),
        parameters=tuple(parameters),
        kind=kind,
        returns=returns,
        return_values=return_values or (),
        reads=reads,
        composite=bool(info and info.composite),
        declared=info is not None,
        quantity=quantity,
        labels=labels,
        calls=calls_of(type(device), name) if info and info.composite else (),
        selectors=tuple(p.name for p in parameters if p.selector),
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
