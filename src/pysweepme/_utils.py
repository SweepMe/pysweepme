import functools
import inspect
import re
from itertools import zip_longest
from typing import Any, Callable

from . import __version__
from .ErrorMessage import debug


def _get_pysweepme_version_tuple(version: str) -> tuple[int, ...]:
    version_extract = re.search(r"^(?:\d+\.)*\d+", version)
    if not version_extract:
        msg = f"Cannot extract version from {version}"
        raise ValueError(msg)
    return tuple(map(int, version_extract.group(0).split(".")))


_pysweepme_version = _get_pysweepme_version_tuple(__version__)


def _is_version_reached(version: str) -> bool:
    version_tuple = tuple(map(int, version.split(".")))
    # zip and un-zip the version tuples to make them same length
    version_tuple, compare = zip(*zip_longest(version_tuple, _pysweepme_version, fillvalue=0))
    if version_tuple > compare:
        return False
    return True


def deprecated(
    removed_in: str,
    instructions: str,
    name: str = "",
    blame_call: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    removed_phrase = "in the next release" if _is_version_reached(removed_in) else f"in version {removed_in}"

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if callable(func):

            def get_call_blame() -> str:
                try:
                    frame = inspect.stack()[2]  # 0 is get_call_blame(), 1 is _inner()
                    file = frame.filename
                    code = (frame.code_context or [""])[0].strip()
                    line = frame.lineno
                    blame = f" ['{code.strip()}' in '{file}', line {line}]"
                except (TypeError, OSError):
                    blame = ""
                return blame

            @functools.wraps(func)
            def _inner(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
                blame_call_str = get_call_blame() if blame_call else ""
                debug(
                    f"{name or func.__name__}() is deprecated and will be removed {removed_phrase}. "
                    f"{instructions}{blame_call_str}",
                )
                return func(*args, **kwargs)

            return _inner
        msg = f"{func!s} is not callable and can't be decorated."
        raise NotImplementedError(msg)

    return decorator
