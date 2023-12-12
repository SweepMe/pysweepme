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

import os
from configparser import ConfigParser

from pysweepme.ErrorMessage import error
from pysweepme.FolderManager import getFoMa


def is_nonprimary_instance() -> bool:
    return bool(getFoMa().get_instance_id())


def get_write_mode() -> str:
    """The write mode overwrite 'w' for file operations, except when this pysweepme instance is not the only / first
    instance. In that case it returns 'r' so that no conflicting write operations can occur.

    Returns:
        The write mode for file operations.
    """
    if getFoMa().get_instance_id():
        return "r"
    else:
        return "w"


class Config(ConfigParser):
    """Convenience wrapper around ConfigParser to quickly access config files."""

    def __init__(self, file_name=None) -> None:
        super().__init__()

        self.optionxform = str  # type: ignore

        self.file_name = file_name

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

    def load_file(self):
        try:
            if self.is_file():
                if os.path.exists(self.file_name):
                    with open(self.file_name, "r", encoding="utf-8") as cf:
                        self.read_file(cf)
                return True
            else:
                self.read_string(self.file_name)
                return True
        except:
            error()

        return False

    def makeConfigFile(self):
        """Deprecated."""
        return self.create_file()

    def create_file(self):
        try:
            if not self.is_file():
                if is_nonprimary_instance():
                    msg = "Config File cannot be created in multi-instance mode. Please close all SweepMe! instances and start a single SweepMe! instance first."
                    raise Exception(
                        msg,
                    )
                if not os.path.exists(os.path.dirname(self.file_name)):
                    os.mkdir(os.path.dirname(self.file_name))
                with open(self.file_name, get_write_mode(), encoding="utf-8") as cf:
                    self.write(cf)

                return True
        except:
            error()

        return False

    def setConfigSection(self, section):
        """Deprecated."""
        return self.set_section(section)

    def set_section(self, section):
        try:
            if self.load_file():
                if is_nonprimary_instance():
                    msg = "Cannot save config in multi-instance mode. Please change the configuration in the primary SweepMe! instance."
                    raise Exception(
                        msg,
                    )
                with open(self.file_name, get_write_mode(), encoding="utf-8") as cf:
                    if not self.has_section(section):
                        self.add_section(section)
                    self.write(cf)
            return True

        except:
            error()

        return False

    def setConfigOption(self, section, option, value):
        """Deprecated."""
        return self.set_option(section, option, value)

    def set_option(self, section, option, value):
        try:
            if is_nonprimary_instance():
                msg = "Cannot save config in multi-instance mode. Please change the configuration in the primary SweepMe! instance."
                raise Exception(
                    msg,
                )

            self.set_section(section)

            self.set(section, option, value)

            with open(self.file_name, get_write_mode(), encoding="utf-8") as cf:
                self.write(cf)
            return True
        except:
            error()

        return False

    def removeConfigOption(self, section, option):
        try:
            if self.load_file() and self.has_section(section) and self.has_option(section, option):
                if is_nonprimary_instance():
                    msg = "Cannot save config in multi-instance mode. Please change the configuration in the primary SweepMe! instance."
                    raise Exception(
                        msg,
                    )
                self.remove_option(section, option)

                with open(self.file_name, get_write_mode(), encoding="utf-8") as cf:
                    self.write(cf)

                return True
            return False
        except:
            error()

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
