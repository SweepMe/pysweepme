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


from __future__ import annotations

import contextlib
import inspect
import os
from configparser import ConfigParser
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar

from pysweepme._utils import deprecated
from pysweepme.UserInterface import message_balloon, message_box, message_info, message_log

from .FolderManager import getFoMa

_config = ConfigParser()


class EmptyDevice:
    actions: list[
        str
    ] = []  # static variable that can be used in a driver to define a list of function names that can be used as action

    _device_communication: ClassVar[dict[str, Any]] = {}
    _parameter_store: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        self.variables: list[str] = []
        self.units: list[str] = []
        self.plottype: list[bool] = []  # True if plotted
        self.savetype: list[bool] = []  # True if saved

        self.shortname = ""
        self.idlevalue = None  # deprecated, remains for compatibility reasons
        self.stopvalue = None  # deprecated, remains for compatibility reasons
        self.value = None

        self.abort = ""  # deprecated, remains for compatibility reasons
        self.stopMeasurement = ""  # deprecated, remains for compatibility reasons, use raise Exception(...) instead

        # variable that can be overwritten by SweepMe! to indicate that the user requested a stop
        self._is_run_stopped = False

        self.port_manager = False
        self.port_types: list[str] = []
        self.port_identifications: list[str] = [""]
        self.port_properties: dict[str, Any] = {}

        self.DeviceClassName = str(self.__class__)[8:-2].split(".")[0]

        # deprecated, remains for compatibility reasons
        # one should always ask the FolderManager regarding the actual path
        self.tempfolder = self.get_folder("TEMP")

        self._latest_parameters: dict[str, Any] | None = None

    @property
    def device_communication(self) -> dict[str, Any]:
        """Single (global) dictionary where drivers can store their information that can be shared across instances."""
        return EmptyDevice._device_communication

    @device_communication.setter
    def device_communication(self, _: object) -> None:
        msg = (
            "Changing the device_communication dictionary is not allowed.\n"
            "Please only work on specific indices, e.g. \n"
            ">>> self.device_communication[<your index>] = <your value>"
        )
        raise TypeError(msg)

    @staticmethod
    def clear_device_communication() -> None:
        """Clear all information that have been stored in the device_communication dictionary."""
        EmptyDevice._device_communication = {}

    def list_functions(self):
        """Returns a list of all function names that are individually defined by the driver, e.g. get/set functions.

        These functions can be be used in python projects when using pysweepme to directly access instrument properties.
        """
        all_functions = [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith("_")]
        empty_device_functions = [func for func in dir(EmptyDevice) if callable(getattr(EmptyDevice, func))]

        return list(set(all_functions) - set(empty_device_functions))

    def store_parameter(self, key: str, value: object) -> None:
        """Stores a value in the ParameterStore for a given key.

        Drivers can use the ParameterStore to store information and restore the same information later even in
        a new instance.

        Args:
            key: The key under which the information is stored. It should be unique and not conflicting with
                 other drivers.
            value: The information to be stored.
        """
        self._parameter_store[key] = value

    def restore_parameter(self, key: str) -> Any:  # noqa: ANN401  # The type of the information is up to the user
        """Restores a parameter from the ParameterStore for a given key.

        Args:
            key: The key under which the information was stored before.

        Returns:
            The stored information, or None if no information can be found under the given key.
        """
        if key in self._parameter_store:
            return self._parameter_store[key]
        return None

    def _on_run(self):
        """Called by SweepMe! at the beginning of the run to indicate the start. Do not overwrite it."""
        self._is_run_stopped = False

    def _on_stop(self):
        """Called by SweepMe! in case the user requests a stop of the run. Do not overwrite it."""
        self._is_run_stopped = True

    def is_run_stopped(self):
        """This function can be used in a driver to figure out whether a stop of the run was requested by the user
        It is helpful if a driver function is caught in a while-loop.
        """
        return self._is_run_stopped

    @deprecated("1.5.7", "Use get_folder() instead.")
    def get_Folder(self, identifier):
        """Easy access to a folder without the need to import the FolderManager."""
        return self.get_folder(identifier)

    def get_folder(self, identifier):
        """Easy access to a folder without the need to import the FolderManager."""
        if identifier == "SELF":
            return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))
        return getFoMa().get_path(identifier)

    @deprecated("1.5.7", "Use is_configfile() instead.")
    def isConfigFile(self):
        """deprecated: remains for compatibility reasons."""
        return self.is_configfile()

    def is_configfile(self):
        """This function checks whether a driver related config file exists."""
        # if config file directory is changed it must also be changed in version manager!
        if os.path.isfile(getFoMa().get_path("CUSTOMFILES") + os.sep + self.DeviceClassName + ".ini"):
            _config.read(getFoMa().get_path("CUSTOMFILES") + os.sep + self.DeviceClassName + ".ini")
            return True
        return False

    @deprecated("1.5.7", "Use get_configsections() instead.")
    def getConfigSections(self):
        """deprecated: remains for compatibility reasons."""
        return self.get_configsections()

    def get_configsections(self):
        """This function returns all sections of the driver related config file.

        If not file exists, an empty list is returned.

        Returns:
            List of Strings
        """
        if self.is_configfile():
            return _config.sections()
        return []

    @deprecated("1.5.7", "Use get_configoptions() instead.")
    def getConfigOptions(self, section):
        """deprecated: remains for compatibility reasons."""
        return self.get_configoptions(section)

    def get_configoptions(self, section):
        """This functions returns all key-value options of a given section of the driver related config file.

        If the file does not exist, an empty dictionary is returned.

        Args:
            section: str, a config file section

        Returns:
            dict with pairs of key-value options
        """
        vals = {}
        if self.is_configfile() and section in _config:
            for key in _config[section]:
                vals[key] = _config[section][key]
        return vals

    @deprecated("1.5.7", "Use get_config() instead.")
    def getConfig(self):
        """deprecated: remains for compatibility reasons."""
        return self.get_config()

    def get_config(self):
        """This function returns a representation of the driver related config file by means of a nested dictionary
        that contains for each section a dictionary with the options.
        """
        return {section: self.get_configoptions(section) for section in self.get_configsections()}

    def get_GUIparameter(self, parameter: dict[str, Any]):
        """Is overwritten by Device Class to retrieve the GUI parameter selected by the user."""

    def set_GUIparameter(self) -> dict[str, Any]:
        """Is overwritten by Device Class to set the GUI parameter a user can select."""
        return {}

    def update_gui_parameters_with_defaults(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Update the driver's current parameters with the given values and return the parameters.

        This is a helper function that ensures compatibility with simple drivers. When the GUI parameters
        passed to the update_gui_parameters function don't cover all parameters required by simple drivers,
        the driver might raise an Exception because a required key is not found. This helper solves the issue
        by enhancing any missing GUI parameter with the respective default of the driver.
        For advanced drivers, this helper may also add fields, but the advanced driver should be intelligent
        enough to only extract the values that are required.

        Drivers should not overwrite this function.

        Args:
            parameters: A dictionary where keys correspond to the GUI parameter name and the value is
                        the value as specified in the GUI.
                        When parameters is None, nothing shall be updated and instead only the defaults shall
                        be returned.

        Returns:
            A dictionary where the keys are the fields that shall be shown in the GUI and the values are
            the default value. Simple drivers will always return the same defaults.
        """
        # Note to developers:
        # The "enhance with defaults" is necessary, because when switching the driver in SweepMe!,
        # SweepMe! will pass the GUI parameters of the previous driver to the new driver, which
        # obviously doesn't match. Once this behaviour is fixed, this function won't be needed any longer.
        # This behaviour does not impact the correctness of the operation, as a second call to update the
        # GUI parameters will pass the correct parameters to the driver anyway.
        if parameters is not None:
            default_parameters = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                                  for k, v in self.update_gui_parameters().items()}
            parameters = default_parameters | parameters
        return self.update_gui_parameters(parameters)

    def update_gui_parameters(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Update the driver's current parameters with the given values and return the parameters.

        The driver's parameters are updated with the values that are passed to this function.
        The function will then return a dictionary with keys and defaults that correspond to
        the current parameter state. Most (simple) drivers will always return the default
        GUI parameters. More advanced drivers might return different GUI fields depending on
        certain conditions, like other GUI parameters or instrument identification / capabilities.

        Args:
            parameters: A dictionary where keys correspond to the GUI parameter name and the value is
                        the value as specified in the GUI. Advanced drivers (where GUI fields can change)
                        must be able to handle incomplete dictionaries (i.e. only certain keys are provided)
                        and complete them to a valid configuration.
                        When parameters is None, nothing shall be updated and instead only the defaults shall
                        be returned.

        Returns:
            A dictionary where the keys are the fields that shall be shown in the GUI and the values are
            the default value. Simple drivers will always return the same defaults.
        """
        if parameters:
            self.get_GUIparameter(parameters)
        return self.set_GUIparameter()

    def reset_latest_parameters(self) -> None:
        """Initialize or reset the saved parameters to their default.

        The parameters will be set to their default values. If Port / Device were already set, these properties
        are retained.

        """
        previous_parameters = self._latest_parameters or {}
        # we need to do a deepcopy. If the driver has it's defaults in a dictionary, we do not want to change it
        self._latest_parameters = deepcopy(self.update_gui_parameters())

        # if the default for a property is a list (user shall choose one), we use the first element as the default
        for key, default in self._latest_parameters.items():
            if isinstance(default, list):
                self._latest_parameters[key] = default[0]

        # copy previous Device and Port, if they exist, because they are never part of the defaults
        properties_to_copy = ["Device", "Port"]
        for property_to_copy in properties_to_copy:
            with contextlib.suppress(KeyError):
                self._latest_parameters[property_to_copy] = previous_parameters[property_to_copy]

    def set_parameters(self, parameters: dict[str, Any] | None = None) -> None:
        """Overwrite GUI parameters.

        Args:
            parameters: Dictionary mapping from keys-to-overwrite to the new values.

        """
        if self._latest_parameters is None:
            self.reset_latest_parameters()

        if TYPE_CHECKING:
            # the reset_latest_parameters() will set self._latest_parameters, so it can't be None any longer
            # This assert is used to give that information to type checkers
            assert self._latest_parameters is not None

        supported_parameters = [*self._latest_parameters.keys(), "Port", "Label", "Channel", "Device"]
        if parameters:
            for key, value in parameters.items():
                if key in supported_parameters:
                    self._latest_parameters[key] = value
                else:
                    msg = (
                        f"Keyword '{key}' not supported as parameter. "
                        f"Supported parameters are: {', '.join(supported_parameters)}"
                    )
                    raise ValueError(msg)

            self.update_gui_parameters(self._latest_parameters)

    def get_parameters(self) -> dict[str, Any]:
        """Retrieve the parameters that are currently saved for the device.

        Returns:
            Mapping of parameter keys to their current values.
        """
        if self._latest_parameters is None:
            self.reset_latest_parameters()

        if TYPE_CHECKING:
            # the reset_latest_parameters() will set self._latest_parameters, so it can't be None any longer
            # This assert is used to give that information to type checkers
            assert self._latest_parameters is not None

        return self._latest_parameters

    def set_port(self, port):
        self.port = port

    def get_port(self):
        return self.port

    ## can be used by device class to be triggered by button find_Ports
    # def find_Ports(self):

    ## not needed anymore here
    ## the module checks whether the functions exists
    # def get_CalibrationFile_properties(self, port = ""):

    def connect(self):
        """Function to be overridden if needed and not using the port manager."""

    def disconnect(self):
        """Function to be overridden if needed."""

    def initialize(self):
        """Function to be overridden if needed."""

    def deinitialize(self):
        """Function to be overridden if needed."""

    def reconfigure(self, parameters={}, keys=[]):
        """Function to be overridden if needed.

        if a GUI parameter changes after replacement with global parameters, the device needs to be reconfigure.
        Default behavior is that all parameters are set again and 'configure' is called.
        The device class maintainer can redefine/overwrite 'reconfigure' with a more individual procedure.
        """
        self.update_gui_parameters(parameters)
        self.configure()

    def configure(self):
        """Function to be overridden if needed."""

    def unconfigure(self):
        """Function to be overridden if needed."""
        ## TODO: should be removed in future as these lines are anyway not performed if the function is overridden
        if self.idlevalue is not None:
            self.value = self.idlevalue

    def poweron(self):
        """Function to be overridden if needed."""

    def poweroff(self):
        """Function to be overridden if needed."""

    def signin(self):
        """Function to be overridden if needed."""

    def signout(self):
        """Function to be overridden if needed."""

    def _transfer(self):
        """Function to be overridden if needed."""

    def start(self):
        """Function to be overridden if needed."""

    def apply(self):
        """Function to be overridden if needed."""

    def reach(self) -> None:
        """Actively wait until the applied value is reached.

        Optional, can be overriden by the device class if needed.
        """

    def adapt(self):
        """Function to be overridden if needed."""

    def adapt_ready(self):
        """Function to be overridden if needed."""

    def trigger_ready(self):
        """Function to be overridden if needed."""

    def measure(self):
        """Function to be overridden if needed."""

    def request_result(self):
        """Function to be overridden if needed."""

    def read_result(self):
        """Function to be overridden if needed."""

    def process_data(self):
        """Function to be overridden if needed."""

    def call(self):
        """Function to be overridden if needed."""
        return [float("nan") for x in self.variables]

    def finish(self):
        """Function to be overridden if needed."""

    # def set_Parameter(self,feature,value): # not used yet
    # pass

    # def get_Parameter(self,feature): # not used yet
    # pass

    def stop_Measurement(self, text):
        """deprecated: use 'raise Exception(...)' instead
        sets flag to stop a measurement, not supported in pysweepme standalone.
        """
        self.stopMeasurement = text
        return False

    def stop_measurement(self, text):
        """deprecated: use 'raise Exception(...)' instead
        sets flag to stop a measurement, not supported in pysweepme standalone.
        """
        self.stopMeasurement = text
        return False

    def write_Log(self, msg):
        """deprecated, remains for compatibility reasons."""
        self.message_log(msg)

    def write_log(self, msg):
        """deprecated, remains for compatibility reasons."""
        self.message_log(msg)

    def message_log(self, msg):
        """Writes message to logbook file."""
        message_log(msg)

    def message_Info(self, msg):
        """Command is deprecated, use 'message_info' instead."""
        self.message_info(msg)

    def message_info(self, msg):
        """Write to info box."""
        message_info(msg)

    def message_Box(self, msg):
        """Command is deprecated, use 'message_box' instead."""
        self.message_box(msg)

    def message_box(self, msg, blocking=False):
        """Creates a message box with given message."""
        message_box(msg, blocking)

    def message_balloon(self, msg):
        """Creates a message balloon with given message."""
        message_balloon(msg)

    """  convenience functions  """

    def get_variables(self):
        """Returns a list of strings being the variable of the Device Class."""
        return self.variables

    def get_units(self):
        """Returns a list of strings being the units of the Device Class."""
        return self.units

    def get_variables_units(self):
        variable_units = {}

        for var, unit in zip(self.variables, self.units):
            variable_units[var] = unit

        return variable_units

    def set_value(self, value):
        self.value = value

    def apply_value(self, value):
        """Convenience function for user to apply a value, mainly for use with pysweepme."""
        self.value = value
        self.apply()

    def write(self, value):
        """Applies and reaches the given value as new sweep value for the selected SweepMode."""
        self.start()
        self.apply_value(value)

        if hasattr(self, "reach"):
            self.reach()

    def read(self):
        """\
        returns a list of values according to functions 'get_variables' and 'get_units'
        convenience function for pysweepme to quickly retrieve values by calling several semantic standard functions.
        """
        self.adapt()
        self.adapt_ready()
        self.trigger_ready()
        self.measure()
        self.request_result()
        self.read_result()
        self.process_data()
        return self.call()
