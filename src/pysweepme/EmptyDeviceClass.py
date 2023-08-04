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


import inspect
import os
from configparser import ConfigParser
from typing import Any

from pysweepme.UserInterface import message_balloon, message_box, message_info, message_log

from .FolderManager import getFoMa

_config = ConfigParser()


class EmptyDevice:
    actions: list[
        str
    ] = []  # static variable that can be used in a driver to define a list of function names that can be used as action

    def __init__(self) -> None:
        # here to make sure that it is known, later it is overwritten by SweepMe!
        self.device_communication: dict[str, Any] = {}

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

        self._parameters: dict[Any, Any] = {}

        # ParameterStore
        # needs to be defined here in case the device class is used standalone with pysweepme
        # Otherwise, the object is handed over by the module during create_Device
        # The ParameterStore can then be used to store and restore some parameters after re-instantiating.
        self._ParameterStore: dict[Any, Any] = {}

    def list_functions(self):
        """Returns a list of all function names that are individually defined by the driver, e.g. get/set functions.

        These functions can be be used in python projects when using pysweepme to directly access instrument properties.
        """
        all_functions = [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith("_")]
        empty_device_functions = [func for func in dir(EmptyDevice) if callable(getattr(EmptyDevice, func))]

        return list(set(all_functions) - set(empty_device_functions))

    def store_parameter(self, key, value):
        """Stores a value in the ParameterStore for a given key."""
        self._ParameterStore[key] = value

    def restore_parameter(self, key):
        """Restores a parameter from the ParameterStore for a given key."""
        if key in self._ParameterStore:
            return self._ParameterStore[key]
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

    def get_Folder(self, identifier):
        """Easy access to a folder without the need to import the FolderManager."""
        if identifier == "SELF":
            return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))
        return getFoMa().get_path(identifier)

    def get_folder(self, identifier):
        """Same function like get_Folder but more python style."""
        return self.get_Folder(identifier)

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

    def getConfigSections(self):
        """deprecated: remains for compatibility reasons."""
        return self.get_configsections()

    def get_configsections(self):
        """This function returns all sections of the driver related config file. If not file exists, an empty list
        is returned.

        Returns:
            List of Strings
        """
        if self.isConfigFile():
            return _config.sections()
        return []

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
        if self.isConfigFile() and section in _config:
            for key in _config[section]:
                vals[key] = _config[section][key]
        return vals

    def getConfig(self):
        """deprecated: remains for compatibility reasons."""
        return self.get_config()

    def get_config(self):
        """This function returns a representation of the driver related config file by means of a nested dictionary
        that contains for each section a dictionary with the options.
        """
        return {section: self.getConfigOptions(section) for section in self.getConfigSections()}

    def get_GUIparameter(self, parameter):
        """Is overwritten by Device Class to retrieve the GUI parameter selected by the user."""

    def set_GUIparameter(self):
        """Is overwritten by Device Class to set the GUI parameter a user can select."""
        return {}

    def set_parameters(self, parameter={}):
        standard_parameter = self.set_GUIparameter()

        for key in standard_parameter:
            if isinstance(standard_parameter[key], list):
                standard_parameter[key] = standard_parameter[key][0]  # take the first value from list as default value

        for key in parameter:
            if key in standard_parameter or key in ["Port", "Label", "Channel"]:
                standard_parameter[key] = parameter[key]
            else:
                msg = (
                    f"Keyword '{key}' not supported as parameter. "
                    f"Supported parameters are: {'), '.join(list(standard_parameter.keys()))}"
                )
                raise Exception(msg)

        self.update_parameters(standard_parameter)

        self.get_GUIparameter(standard_parameter)

    def update_parameters(self, parameter={}):
        self._parameters.update(parameter)

    def get_parameters(self):
        return self._parameters

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
        """Function to be overloaded if needed."""

    def disconnect(self):
        """Function to be overloaded if needed."""

    def initialize(self):
        """Function to be overloaded if needed."""

    def deinitialize(self):
        """Function to be overloaded if needed."""

    def poweron(self):
        """Function to be overloaded if needed."""

    def poweroff(self):
        """Function to be overloaded if needed."""

    def reconfigure(self, parameters={}, keys=[]):
        """Function to be overloaded if needed.

        if a GUI parameter changes after replacement with global parameters, the device needs to be reconfigure.
        Default behavior is that all parameters are set again and 'configure' is called.
        The device class maintainer can redefine/overwrite 'reconfigure' with a more individual procedure.
        """
        self.get_GUIparameter(parameters)
        self.configure()

    def configure(self):
        """Function to be overloaded if needed."""

    def unconfigure(self):
        """Function to be overloaded if needed."""
        ## TODO: should be removed in future as these lines are anyway not performed if the function is overloaded
        if self.idlevalue is not None:
            self.value = self.idlevalue

    def signin(self):
        """Function to be overloaded if needed."""

    def signout(self):
        """Function to be overloaded if needed."""

    def _transfer(self):
        """Function to be overloaded if needed."""

    def start(self):
        """Function to be overloaded if needed."""

    def apply(self):
        """Function to be overloaded if needed."""

    def reach(self) -> None:
        """Actively wait until the applied value is reached.

        Optional, can be overriden by the device class if needed.
        """

    def adapt(self):
        """Function to be overloaded if needed."""

    def adapt_ready(self):
        """Function to be overloaded if needed."""

    def trigger_ready(self):
        """Function to be overloaded if needed."""

    def trigger(self):  # deprecated
        pass

    def measure(self):
        """Function to be overloaded if needed."""

    def request_result(self):
        """Function to be overloaded if needed."""

    def read_result(self):
        """Function to be overloaded if needed."""

    def process_data(self):
        """Function to be overloaded if needed."""

    def call(self):
        """Function to be overloaded if needed."""
        return [float("nan") for x in self.variables]

    def process(self):
        """Function to be overloaded if needed."""

    def finish(self):
        """Function to be overloaded if needed."""

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
