# The MIT License

# Copyright (c) 2023 SweepMe! GmbH (sweep-me.net)

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

"""This module defines types used in pysweepme."""

from __future__ import annotations

from types import TracebackType
from typing import IO, Any, Protocol, Union


class FileIOContextProtocol(Protocol):
    """Protocol for a ContextManager for IO Operations."""
    def __enter__(self) -> IO[Any]:
        """Function to return a file descriptor."""

    def __exit__(
        self,
        exc_type: type[Exception] | None,
        exc_value: Exception | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Function to close context manager."""


class FileIOProtocolWithoutModifiedCheck(Protocol):
    """Protocol for a class with a pathlib.Path compatible open() function that returns a context manager.

    In contrast to Path's open(), this function does not return a file descriptor directly and instead always
    must be used in conjunction with a `with` statement that will return the file descriptor of the opened file.
    """
    def open(  # noqa: A003, PLR0913
        self,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> FileIOContextProtocol:
        """Function to open a file compatible with pathlib.Path when used in a context manager."""


class FileIOProtocolWithModifiedCheck(FileIOProtocolWithoutModifiedCheck):
    """Protocol for a class with a pathlib.Path compatible open() function that returns a context manager.

    In contrast to Path's open(), this function does not return a file descriptor directly and instead always
    must be used in conjunction with a `with` statement that will return the file descriptor of the opened file.
    """
    def set_full_read(self) -> None:
        """Function that shall be called when a file is read completely.

        If a file was modified by an external program, the user does not need to decide whether to overwrite the file
        or not, if the respective file was only read after the external modification.
        """


FileIOProtocol = Union[FileIOProtocolWithoutModifiedCheck, FileIOProtocolWithModifiedCheck]
