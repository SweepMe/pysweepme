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
import functools
import inspect
import os
from configparser import ConfigParser
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar

from pysweepme.UserInterface import message_balloon, message_box, message_info, message_log
from pysweepme.Ports import Port

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
        self.value: Any = None

        self.abort = ""  # deprecated, remains for compatibility reasons
        self.stopMeasurement: str = ""  # deprecated, remains for compatibility reasons, use raise Exception(...) instead

        # variable that can be overwritten by SweepMe! to indicate that the user requested a stop
        self._is_run_stopped = False

        self.port_manager = False
        self.port_types: list[str] = []
        self.port_identifications: list[str] = [""]
        self.port_properties: dict[str, Any] = {}
        self.port: Port | Any | None = None

        self.DeviceClassName = str(self.__class__)[8:-2].split(".")[0]

        # deprecated, remains for compatibility reasons
        # one should always ask the FolderManager regarding the actual path
        self.tempfolder = self.get_folder("TEMP")

        self._latest_parameters: dict[str, Any] | None = None

    def is_function_overwritten(self, function: str) -> bool:
        """Test if a given function is overwritten in a child class of EmptyDevice.

        Args:
            function: The name of the function to check.

        Returns:
            True, if the function is overwritten in a child class, False otherwise.
        """
        overwrites = False
        # Get the class and a list of all base classes in the order python would resolve functions
        # using getmro(). If function is element of the classes dictionary and a function, BEFORE looking into
        # the EmptyDevice class, then function was obviously overridden by a subclass.
        for cls in inspect.getmro(self.__class__):
            if cls is EmptyDevice:
                break
            if function in cls.__dict__ and callable(getattr(cls, function, None)):
                overwrites = True
                break

        return overwrites

    @functools.cached_property
    def uses_update_gui_parameters(self) -> bool:
        """Boolean that tells if the driver uses the new update_gui_parameters function."""
        return self.is_function_overwritten(self.update_gui_parameters.__name__)

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

    @classmethod
    def get_device_communication(cls) -> dict[str, Any]:
        """Single (global) dictionary where drivers can store their information that can be shared across instances."""
        return cls._device_communication

    @staticmethod
    def clear_device_communication() -> None:
        """Clear all information that have been stored in the device_communication dictionary."""
        EmptyDevice._device_communication = {}

    def list_functions(self) -> list[str]:
        """Returns a list of all function names that are individually defined by the driver, e.g. get/set functions.

        These functions can be used in python projects when using pysweepme to directly access instrument properties.
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

    def _on_run(self) -> None:
        """Called by SweepMe! at the beginning of the run to indicate the start. Do not overwrite it."""
        self._is_run_stopped = False

    def _on_stop(self) -> None:
        """Called by SweepMe! in case the user requests a stop of the run. Do not overwrite it."""
        self._is_run_stopped = True

    def is_run_stopped(self) -> bool:
        """This function can be used in a driver to figure out whether a stop of the run was requested by the user
        It is helpful if a driver function is caught in a while-loop.
        """
        return self._is_run_stopped

    def get_folder(self, identifier: str) -> str | bool:
        """Easy access to a folder without the need to import the FolderManager."""
        if identifier == "SELF":
            return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))
        return getFoMa().get_path(identifier)

    def is_configfile(self) -> bool:
        """This function checks whether a driver related config file exists."""
        # if config file directory is changed it must also be changed in version manager!
        if os.path.isfile(getFoMa().get_path("CUSTOMFILES") + os.sep + self.DeviceClassName + ".ini"):
            _config.read(getFoMa().get_path("CUSTOMFILES") + os.sep + self.DeviceClassName + ".ini")
            return True
        return False

    def get_configsections(self) -> list[str]:
        """This function returns all sections of the driver related config file.

        If not file exists, an empty list is returned.

        Returns:
            List of Strings
        """
        if self.is_configfile():
            return _config.sections()
        return []

    def get_configoptions(self, section: str) -> dict[str, Any]:
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

    def get_config(self) -> dict[str, dict[str, Any]]:
        """This function returns a representation of the driver related config file by means of a nested dictionary
        that contains for each section a dictionary with the options.
        """
        return {section: self.get_configoptions(section) for section in self.get_configsections()}

    def get_GUIparameter(self, parameter: dict[str, Any]) -> None:
        """Is overwritten by Device Class to retrieve the GUI parameter selected by the user."""
        # Used for compatibility with old code that still uses get_GUIparameter
        if self.uses_update_gui_parameters:
            if parameter:
                self.apply_gui_parameters(parameter)
            self.update_gui_parameters(parameter)

    def set_GUIparameter(self) -> dict[str, Any]:
        """Is overwritten by Device Class to set the GUI parameter a user can select."""
        # Used for compatibility with old code that still uses set_GUIparameter
        if self.uses_update_gui_parameters:
            return self.update_gui_parameters({})
        return {}

    def get_gui_parameters_and_default_values(self) -> dict[str, Any]:
        """Get the default parameters and values of the driver.

        The default values explicitly mean a single value that shall be applied by default,
        e.g. in case of lists the first element. This value can thus directly be used as the
        default to show in the GUI, or as a fallback value for the driver when the value from
        the GUI was None.

        Returns:
            A mapping of parameter names to their default value.
        """
        if self.uses_update_gui_parameters:
            driver_parameters = self.update_gui_parameters({})
        else:
            driver_parameters = self.set_GUIparameter()
        return {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                for k, v in driver_parameters.items()}

    def enhance_parameters_with_defaults(self, parameters: dict[str, Any] | None) -> dict[str, Any]:
        """Enhance the parameters dictionary with values from the driver's default parameter values.

        Any parameters in the default driver parameters that are not included in the passed dictionary or which are
        None, are set to the value given by the drivers default parameters.

        Args:
            parameters: The dictionary mapping parameters to their values from the GUI, or None.

        Returns:
            A mapping of parameters to their values from the GUI with default values as fallback.
        """
        default_parameters = self.get_gui_parameters_and_default_values()
        if parameters is None:
            return default_parameters
        return default_parameters | {k: v for k, v in parameters.items() if v is not None}

    def update_gui_parameters_with_fallback(
            self, reading_mode: bool, parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the driver's current parameters with the given values and return the parameters.

        This is a helper function that ensures compatibility with simple drivers. When the GUI parameters
        passed to the update_gui_parameters function don't cover all parameters required by simple drivers,
        the driver might raise an Exception because a required key is not found. This helper solves the issue
        by enhancing any missing GUI parameter with the respective default of the driver.
        For advanced drivers, this helper may also add fields, but the advanced driver should be intelligent
        enough to only extract the values that are required.
        Additionally, None-Type parameters (e.g. from the Parameter Syntax) are replaced with the defaults
        as well.

        Drivers should not overwrite this function.

        Args:
            reading_mode: When True, the purpose of this call is to get the default parameters of the driver.
                          This means this function should call set_GUIparameter for old drivers, and
                          update_gui_parameters for new drivers.
                          When False, the purpose of this call is to apply the parameters passed to this function
                          to the driver. This means this function should call get_GUIparameter for old drivers, and
                          update_gui_parameters for new drivers.
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
        if not self.uses_update_gui_parameters:
            if reading_mode:
                return self.set_GUIparameter()  # set_GUIparameter will actually get the parameters from the driver
            enhanced_parameters = self.enhance_parameters_with_defaults(parameters)
            self.get_GUIparameter(enhanced_parameters)  # get_GUIparameter will actually apply the parameters
            return {}

        if parameters is None:
            return self.update_gui_parameters({})
        enhanced_parameters = self.enhance_parameters_with_defaults(parameters)
        if enhanced_parameters:
            self.apply_gui_parameters(enhanced_parameters)
        return self.update_gui_parameters(enhanced_parameters)

    def apply_gui_parameters(self, parameters: dict[str, Any]) -> None:
        """Apply the given parameters to the driver instance.

        Args:
            parameters: A dictionary where keys correspond to the GUI parameter name and the value is
                        the value as specified in the GUI. Drivers
                        must be able to handle incomplete or invalid dictionaries (i.e. only certain keys are provided)
                        and complete them to a valid configuration.
        """

    def update_gui_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002 - defines signature
        """Determine the new GUI parameters of the driver depending on the current parameters.

        The available driver's parameters are updated depending on the values that are passed to this function.
        The function will then return a dictionary with keys and defaults that correspond to
        the current parameter state. Most (simple) drivers will always return the default
        GUI parameters. More advanced drivers might return different GUI fields depending on
        certain conditions, like other GUI parameters or instrument identification / capabilities.

        Args:
            parameters: A dictionary where keys correspond to the GUI parameter name and the value is
                        the value as specified in the GUI. Drivers
                        must be able to handle incomplete or invalid dictionaries (i.e. only certain keys are provided)
                        and complete them to a valid configuration.
                        When parameters is an empty dictionary, nothing shall be updated
                        and instead only the defaults shall be returned.

        Returns:
            A dictionary where the keys are the fields that shall be shown in the GUI and the values are
            the default value. Simple drivers will always return the same defaults.
        """
        msg = ("This driver does not implement the update_gui_parameters function. "
               "use either set_GUIparameter and get_GUIparameter, "
               "or call the update_gui_parameters_with_fallback function.")
        raise NotImplementedError(msg)

    def reset_latest_parameters(self) -> None:
        """Initialize or reset the saved parameters to their default.

        The parameters will be set to their default values. If Port / Device were already set, these properties
        are retained.

        """
        previous_parameters = self._latest_parameters or {}
        # we need to do a deepcopy. If the driver has it's defaults in a dictionary, we do not want to change it
        if self.uses_update_gui_parameters:
            self._latest_parameters = deepcopy(self.update_gui_parameters({}))
        else:
            self._latest_parameters = deepcopy(self.set_GUIparameter())

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

            if self.uses_update_gui_parameters:
                if self._latest_parameters:
                    self.apply_gui_parameters(self._latest_parameters)
                self.update_gui_parameters(self._latest_parameters)
            else:
                self.get_GUIparameter(self._latest_parameters)

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

    def set_port(self, port: Any) -> None:
        """Set the port of the device."""
        self.port = port

    def get_port(self) -> Any:
        """Get the port of the device."""
        return self.port

    ## can be used by device class to be triggered by button find_Ports
    # def find_Ports(self):

    ## not needed anymore here
    ## the module checks whether the functions exists
    # def get_CalibrationFile_properties(self, port = ""):

    def connect(self) -> None:
        """Function to be overridden if needed and not using the port manager."""

    def disconnect(self) -> None:
        """Function to be overridden if needed."""

    def initialize(self) -> None:
        """Function to be overridden if needed."""

    def deinitialize(self) -> None:
        """Function to be overridden if needed."""

    def reconfigure(self, parameters: dict[str, Any] | None = None, keys: list[str] | None = None) -> None:
        """Function to be overridden if needed.

        If a GUI parameter changes after replacement with global parameters, the device needs to be reconfigured.
        Default behavior is that all parameters are set again and 'configure' is called.
        The device class maintainer can redefine/overwrite 'reconfigure' with a more individual procedure.

        Args:
            parameters: Dictionary of all current GUI parameters.
            keys: List of parameter keys that changed. Ignored in the base implementation, but available
                  for subclasses that want to reconfigure only the affected parameters.
        """
        if parameters is None:
            parameters = {}
        if self.uses_update_gui_parameters:
            if parameters:
                self.apply_gui_parameters(parameters)
            self.update_gui_parameters(parameters)
        else:
            self.get_GUIparameter(parameters)
        self.configure()

    def configure(self) -> None:
        """Function to be overridden if needed."""

    def unconfigure(self) -> None:
        """Function to be overridden if needed."""
        # TODO: should be removed in future as these lines are anyway not performed if the function is overridden
        if self.idlevalue is not None:
            self.value = self.idlevalue

    def poweron(self) -> None:
        """Function to be overridden if needed."""

    def poweroff(self) -> None:
        """Function to be overridden if needed."""

    def signin(self) -> None:
        """Function to be overridden if needed."""

    def signout(self) -> None:
        """Function to be overridden if needed."""

    def _transfer(self) -> None:
        """Function to be overridden if needed."""

    def start(self) -> None:
        """Function to be overridden if needed."""

    def apply(self) -> None:
        """Function to be overridden if needed."""

    def reach(self) -> None:
        """Actively wait until the applied value is reached.

        Optional, can be overridden by the device class if needed.
        """

    def adapt(self) -> None:
        """Function to be overridden if needed."""

    def adapt_ready(self) -> None:
        """Function to be overridden if needed."""

    def trigger_ready(self) -> None:
        """Function to be overridden if needed."""

    def measure(self) -> None:
        """Function to be overridden if needed."""

    def request_result(self) -> None:
        """Function to be overridden if needed."""

    def read_result(self) -> None:
        """Function to be overridden if needed."""

    def process_data(self) -> None:
        """Function to be overridden if needed."""

    def call(self) -> Any:
        """Function to be overridden if needed."""
        return [float("nan") for _ in self.variables]

    def finish(self) -> None:
        """Function to be overridden if needed."""

    # def set_Parameter(self,feature,value): # not used yet
    # pass

    # def get_Parameter(self,feature): # not used yet
    # pass

    def stop_Measurement(self, text: str) -> bool:
        """deprecated: use 'raise Exception(...)' instead
        sets flag to stop a measurement, not supported in pysweepme standalone.
        """
        self.stopMeasurement = text
        return False

    def stop_measurement(self, text: str) -> bool:
        """deprecated: use 'raise Exception(...)' instead
        sets flag to stop a measurement, not supported in pysweepme standalone.
        """
        self.stopMeasurement = text
        return False

    def write_Log(self, msg: str) -> None:
        """deprecated, remains for compatibility reasons."""
        self.message_log(msg)

    def write_log(self, msg: str) -> None:
        """deprecated, remains for compatibility reasons."""
        self.message_log(msg)

    def message_log(self, msg: str) -> None:
        """Writes message to logbook file."""
        message_log(msg)

    def message_Info(self, msg: str) -> None:
        """Command is deprecated, use 'message_info' instead."""
        self.message_info(msg)

    def message_info(self, msg: str) -> None:
        """Write to info box."""
        message_info(msg)

    def message_Box(self, msg: str) -> None:
        """Command is deprecated, use 'message_box' instead."""
        self.message_box(msg)

    def message_box(self, msg: str, blocking=False) -> None:
        """Creates a message box with given message."""
        message_box(msg, blocking)

    def message_balloon(self, msg: str) -> None:
        """Creates a message balloon with given message."""
        message_balloon(msg)

    """  convenience functions  """

    def get_variables(self) -> list[str]:
        """Returns a list of strings being the variable of the Device Class."""
        return self.variables

    def get_units(self) -> list[str]:
        """Returns a list of strings being the units of the Device Class."""
        return self.units

    def get_variables_units(self) -> dict[str, str]:
        """Returns a dictionary with variable names as keys and their corresponding units as values."""
        variable_units = {}

        for var, unit in zip(self.variables, self.units):
            variable_units[var] = unit

        return variable_units

    def set_value(self, value: Any) -> None:
        """Set self.value, which is the value that is applied to the device when calling 'apply'."""
        self.value = value

    def apply_value(self, value: Any) -> None:
        """Convenience function for user to apply a value, mainly for use with pysweepme."""
        self.value = value
        self.apply()

    def write(self, value: Any) -> None:
        """Applies and reaches the given value as new sweep value for the selected SweepMode."""
        self.start()
        self.apply_value(value)

        if hasattr(self, "reach"):
            self.reach()

    def read(self) -> Any:
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
