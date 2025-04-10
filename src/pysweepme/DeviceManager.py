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
import types
from pathlib import Path

from ._utils import deprecated
from .Architecture import version_info
from .EmptyDeviceClass import EmptyDevice
from .ErrorMessage import error
from .FolderManager import addFolderToPATH
from .PortManager import PortManager


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


def get_driver_module(folder: str, name: str) -> types.ModuleType:
    """Load the module containing the requested driver.

    Args:
        folder: The folder containing the drivers.
        name: The name of the driver

    Returns:
        The loaded module containing the requested driver.
    """
    if folder == "":
        folder = "."
    name = name.strip(r"\/")

    try:
        # Loads .py file as module
        module = imp.load_source(name, get_main_py_path(folder + os.sep + name))
    except Exception as e:  # noqa: BLE001
        # We don't know what could go wrong, so we catch all exceptions, log the error, and raise an Exception again
        error()
        msg = f"Cannot load Driver '{name}' from folder {folder}."
        if isinstance(e, FileNotFoundError):
            msg += " Please change folder or copy Driver to your project."
        raise ImportError(msg) from e

    return module


def get_driver_class(folder: str, name: str) -> type[EmptyDevice]:
    """Get the class (not an instance) of the requested driver.

    Args:
        folder: The folder containing the drivers.
        name: The name of the driver

    Returns:
        The class of the requested driver.
    """
    module = get_driver_module(folder, name)
    driver: type[EmptyDevice] = module.Device
    return driver


def get_driver_instance(folder: str, name: str) -> EmptyDevice:
    """Create a bare driver instance.

    Create a bare driver instance without input cleanup and without setting GUI parameters.

    Args:
        folder: General folder in which to look for drivers.
        name: Name of the driver being the name of the driver folder.

    Returns:
        Device object of the driver.
    """
    driver_class = get_driver_class(folder, name)

    # Add the libs or library folder to the path before instantiating the driver
    driver_path = Path(folder) / name
    addFolderToPATH(str(driver_path))

    return driver_class()


def setup_driver(driver: EmptyDevice, name: str, port_string: str) -> None:
    """Set port and device.

    The GUI parameters Device and Port (if provided) are set.
    When using the Port Manager, the port object is attached to the driver.

    Args:
        driver: The driver instance.
        name: The name of the driver.
        port_string: The string defining the port to use for the driver.
    """
    if port_string != "":
        if driver.port_manager:
            port_manager = PortManager()
            port = port_manager.get_port(port_string, driver.port_properties)
            driver.set_port(port)

        driver.set_parameters({"Port": port_string, "Device": name})

    else:
        driver.set_parameters({"Device": name})


def get_driver(name: str, folder: str = ".", port_string: str = "") -> EmptyDevice:
    """Create a driver instance.

    When the driver uses the port manager, the port will already be opened, but the connect() function of
    the driver must be called in any case.

    Args:
        name: Name of the driver being the name of the driver folder
        folder: (optional) General folder to look for drivers, If folder is not used or empty, the driver is loaded
            from the folder of the running script/project
        port_string: (optional) A port resource name as selected in SweepMe! such as 'COM1', 'GPIB0::1::INSTR', etc.
            It is required if the driver connects to an instrument and needs to open a specific port.

    Returns:
        Initialized Device object of the driver with port and default parameters set.
    """
    name = name.strip(r"\/")

    driver = get_driver_instance(folder, name)
    setup_driver(driver, name, port_string)

    return driver


get_device = deprecated("1.5.8", "Use get_driver() instead.", name="get_device")(get_driver)
