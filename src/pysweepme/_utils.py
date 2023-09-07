import functools
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
    if version_tuple < compare:
        return False
    return True


def deprecated(
    removed_in: str,
    instructions: str,
    name: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    removed_phrase = "in the next release" if _is_version_reached(removed_in) else f"in version {removed_in}"

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if callable(func):

            @functools.wraps(func)
            def _inner(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                debug(f"{name or func.__name__} is deprecated and will be removed {removed_phrase}. {instructions}")
                return func(*args, **kwargs)

            return _inner
        msg = f"{func!s} is not callable and can't be decorated."
        raise NotImplementedError(msg)

    return decorator
