# The MIT License

# Copyright (c) 2021-2022 SweepMe! GmbH

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


__version__ = "1.6.1.2"

import sys

from . import Config, DeviceManager, EmptyDeviceClass, ErrorMessage, FolderManager, PortManager, Ports

if sys.platform == "win32":
    from . import WinFolder

from ._utils import load_source
from .DeviceManager import get_driver
from .EmptyDeviceClass import EmptyDevice
from .ErrorMessage import debug, error
from .FolderManager import addFolderToPATH, get_path, set_path
from .Ports import close_port, get_port

sys.modules["FolderManager"] = sys.modules["pysweepme.FolderManager"]
sys.modules["EmptyDeviceClass"] = sys.modules["pysweepme.EmptyDeviceClass"]
sys.modules["DeviceManager"] = sys.modules["pysweepme.DeviceManager"]
sys.modules["Ports"] = sys.modules["pysweepme.Ports"]
sys.modules["ErrorMessage"] = sys.modules["pysweepme.ErrorMessage"]
if sys.platform == "win32":
    sys.modules["WinFolder"] = sys.modules["pysweepme.WinFolder"]


__all__ = [
    "Config",
    "DeviceManager",
    "EmptyDevice",
    "EmptyDeviceClass",
    "ErrorMessage",
    "FolderManager",
    "PortManager",
    "Ports",
    "WinFolder",
    "addFolderToPATH",
    "close_port",
    "debug",
    "error",
    "get_driver",
    "get_path",
    "get_port",
    "load_source",
    "set_path",
]
