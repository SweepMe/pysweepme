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


import imp
import os
from pathlib import Path

from ._utils import deprecated
from .Architecture import version_info
from .EmptyDeviceClass import EmptyDevice
from .ErrorMessage import error
from .Ports import get_port


def get_main_py_path(path: str) -> str:
    """Find the main python file matching the current architecture best.

    In a given folder, look for the main<suffix>.py file that matches the running python version and bitness.
    Return the generic main.py path if the specific one does not exist.

    Args:
        path: Path to the folder that contains the main<suffix>.py file

    Returns:
        The path to the main<suffix>.py file.
    """
    test_file = path + os.sep + f"main_{version_info.python_suffix}.py"
    if Path(test_file).is_file():
        return test_file
    return path + os.sep + "main.py"


def instantiate_device(folder: str, name: str) -> EmptyDevice:
    """Create a bare driver instance.

    Create a bare driver instance without input cleanup and without setting GUI parameters.

    Args:
        folder: General folder in which to look for drivers.
        name: Name of the driver being the name of the driver folder.

    Returns:
        Device object of the driver.
    """
    try:
        # Loads .py file as module
        module = imp.load_source(name, get_main_py_path(folder + os.sep + name))
    except Exception as e:  # noqa: BLE001
        # We don't know what could go wrong, so we catch all exceptions, log the error, and raise an Exception again
        error()
        msg = f"Cannot load Driver '{name}' from folder {folder}. Please change folder or copy Driver to your project."
        raise ImportError(msg) from e

    device: EmptyDevice = module.Device()
    return device


def get_driver(name: str, folder: str = ".", port_string: str = "") -> EmptyDevice:
    """Create a driver instance.

    Args:
        name: Name of the driver being the name of the driver folder
        folder: (optional) General folder to look for drivers, If folder is not used or empty, the driver is loaded
            from the folder of the running script/project
        port_string: (optional) A port resource name as selected in SweepMe! such as 'COM1', 'GPIB0::1::INSTR', etc.
            It is required if the driver connects to an instrument and needs to open a specific port.

    Returns:
        Initialized Device object of the driver with port and default parameters set.
    """
    if folder == "":
        folder = "."
    if name.startswith(os.sep):
        name = name[1:]
    if name.endswith(os.sep):
        name = name[:-1]

    device = instantiate_device(folder, name)

    if port_string != "":
        if device.port_manager:
            port = get_port(port_string, device.port_properties)
            device.set_port(port)

        device.set_parameters({"Port": port_string, "Device": name})

    else:
        device.set_parameters({"Device": name})

    return device


get_device = deprecated("1.5.8", "Use get_driver() instead.", name="get_device")(get_driver)
