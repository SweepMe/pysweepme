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
from typing import Callable, cast

from .ErrorMessage import error
from .pysweepme_types import FileIOProtocol


class DefaultFileIO:
    """Manages which class shall be used to perform File IO operations.

    By default, pathlib.Path() will be used, but the application may register an alternative default that behaves
    the same when calling open() in a `with` statement.
    """

    custom_default_file_io: tuple[Callable[[Path | str], FileIOProtocol]] | None = None

    @classmethod
    def register_custom_default(cls, function: Callable[[Path | str], FileIOProtocol]) -> None:
        """Register an alternative default for creating a Path-compatible instance for file IO operations.

        Args:
            function: Function that accepts a Path or string representing the file and returns an instance that behaves
                      like pathlib.Path()
        """
        # use a tuple to prevent python from considering it a bound method
        cls.custom_default_file_io = (function,)

    @staticmethod
    def pysweepme_default_fileio(file: Path | str) -> FileIOProtocol:
        """Create a pathlib.Path instance.

        Args:
            file: Path or string representing the file.

        Returns:
            Path instance for the requested argument.
        """
        # Path has more sophisticated signatures than the FileIOProtocol, so we need to cast the type
        return cast(FileIOProtocol, Path(file))

    @staticmethod
    def default_fileio(file: Path | str) -> FileIOProtocol:
        """Create a pathlib.Path() compatible instance for the requested file.

        If the application did not register an alternative default, a pathlib.Path() instance will be returned.

        Args:
            file: Path or string representing the file.

        Returns: An instance that behaves like pathlib.Path()

        """
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
        """Create a Config instance.

        The Config instance should always be created directly before it is used, to make use of the incremental write
        capabilities that reduce conflicts when using multiple instances of the application. That way, the Config class
        will read the current config ini file, apply the requested changes only to the respective section and key, and
        write those changes without overwriting other sections/keys that might have been modified by another program.

        Args:
            file_name: The path (Path object or string) to the config file.
                       Deprecated: A string containing the contents of an ini file.
            custom_reader_writer: If this argument is not provided (recommended), the file operations will be performed
                                  using python's pathlib.Path() (unless the application registered another default).
                                  This argument can be a function returning another instance of a pathlib.Path()
                                  compatible class that shall be used for file IO operations only for this config
                                  instance.
        """
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
            elif isinstance(self.file_name, str):
                # apparently the Config instance is not a valid, existing file, so we try to read it as the content
                # of an ini file
                self.read_string(self.file_name)
            else:
                msg = f"The config file {self.file_name!s} does not exist and thus cannot be read."
                ValueError(msg)
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
