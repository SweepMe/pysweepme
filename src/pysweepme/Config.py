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

from __future__ import annotations

import os
from configparser import ConfigParser
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Callable, Protocol, Union, cast

from pysweepme.ErrorMessage import error


class FileIOContextProtocol(Protocol):
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
    def set_full_read(self) -> None:
        """Function that shall be called when a file is read completely.

        If a file was modified by an external program, the user does not need to decide whether to overwrite the file
        or not, if the respective file was only read after the external modification.
        """


FileIOProtocol = Union[FileIOProtocolWithoutModifiedCheck, FileIOProtocolWithModifiedCheck]


class DefaultFileIO:
    custom_default_file_io: tuple[Callable[[Path | str], FileIOProtocol]] | None = None

    @classmethod
    def register_custom_default(cls, function: Callable[[Path | str], FileIOProtocol]) -> None:
        # use a tuple to prevent python from considering it a bound method
        cls.custom_default_file_io = (function,)

    @staticmethod
    def pysweepme_default_fileio(file: Path | str) -> FileIOProtocol:
        # Path has more sophisticated signatures than the FileIOProtocol, so we need to cast the type
        return cast(FileIOProtocol, Path(file))

    @staticmethod
    def default_fileio(file: Path | str) -> FileIOProtocol:
        if DefaultFileIO.custom_default_file_io:
            return DefaultFileIO.custom_default_file_io[0](file)
        return DefaultFileIO.pysweepme_default_fileio(file)


class Config(ConfigParser):
    """Convenience wrapper around ConfigParser to quickly access config files."""

    def __init__(
        self,
        file_name: Path | str,
        custom_reader_writer: Callable[[Path | str], FileIOProtocol] = DefaultFileIO.default_fileio,
    ) -> None:
        super().__init__()

        self.optionxform = str  # type: ignore

        self.file_name = file_name

        self.reader_writer = custom_reader_writer(file_name)

    def setFileName(self, file_name):
        """Deprecated."""
        self.set_filename(file_name)

    def set_filename(self, file_name):
        self.file_name = file_name

    def isConfigFile(self):
        """Deprecated."""
        return self.is_file()

    def is_file(self):
        try:
            return bool(os.path.isfile(self.file_name))
        except:
            error()

        return False

    def readConfigFile(self):
        """Deprecated."""
        return self.load_file()

    def load_file(self) -> bool:
        try:
            if self.is_file():
                with self.reader_writer.open("r", encoding="utf-8") as cf:
                    self.read_file(cf)
                    if hasattr(self.reader_writer, "set_full_read"):
                        self.reader_writer.set_full_read()
            else:
                self.read_string(self.file_name)
        except:
            error()
            return False

        return True

    def makeConfigFile(self):
        """Deprecated."""
        return self.create_file()

    def create_file(self):
        try:
            if not self.is_file():
                if not os.path.exists(os.path.dirname(self.file_name)):
                    os.mkdir(os.path.dirname(self.file_name))

                with self.reader_writer.open("w", encoding="utf-8") as cf:
                    self.write(cf)

                return True
        except:
            error()

        return False

    def setConfigSection(self, section):
        """Deprecated."""
        return self.set_section(section)

    def set_section(self, section: str) -> bool:
        try:
            if self.load_file():
                if not self.has_section(section):
                    self.add_section(section)
                with self.reader_writer.open("w", encoding="utf-8") as cf:
                    self.write(cf)
        except:
            error()
            return False

        return True

    def setConfigOption(self, section, option, value):
        """Deprecated."""
        return self.set_option(section, option, value)

    def set_option(self, section: str, option: str, value: str) -> bool:
        try:
            self.set_section(section)
            self.set(section, option, value)
            with self.reader_writer.open("w", encoding="utf-8") as cf:
                self.write(cf)
        except:
            error()
            return False

        return True

    def removeConfigOption(self, section: str, option: str) -> bool:
        try:
            if self.load_file() and self.has_section(section) and self.has_option(section, option):
                self.remove_option(section, option)
                with self.reader_writer.open("w", encoding="utf-8") as cf:
                    self.write(cf)
                return True
        except:
            error()

        return False

    def getConfigSections(self):
        """Deprecated."""
        return self.get_sections()

    def get_sections(self):
        if self.load_file():
            return self.sections()
        else:
            return []

    def getConfigOption(self, section, option):
        """Deprecated."""
        return self.get_value(section, option)

    def get_value(self, section, option):
        if self.load_file() and section in self:
            if option.lower() in self[section]:
                return self[section][option.lower()]
            elif option in self[section]:
                return self[section][option]
        return False

    def getConfigOptions(self, section):
        """Deprecated."""
        return self.get_options(section)

    def get_options(self, section):
        vals = {}
        if self.load_file() and section in self:
            for key in self[section]:
                vals[key] = self[section][key]
        return vals

    def getConfig(self):
        """Deprecated."""
        return self.get_values()

    def get_values(self):
        return {section: self.getConfigOptions(section) for section in self.getConfigSections()}
