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

from collections import OrderedDict

from pysweepme import Config
from pysweepme import Ports
from pysweepme.ErrorMessage import error, debug
from pysweepme.FolderManager import getFoMa
from pysweepme.Ports import Port, PortProperties


try:
    import clr  # pythonnet for loading external DotNet DLLs
except ModuleNotFoundError:
    error("Package clr/pythonnet not installed. Use 'pip install pythonnet' in command line.")
except ImportError:
    error("Cannot import clr package. Please check whether your Microsoft .NET Framework is up to date.")


class PortManager(object):

    _instance = None

    def __init__(self) -> None:

        if not hasattr(self, "initialized"):

            # Adding Prologix controllers
            ProgramConfig = Config.Config(getFoMa().get_file("CONFIG"))
            prologix_controller = ProgramConfig.getConfigOptions("PrologixController")
            for port in prologix_controller.values():
                self.add_prologix_controller(port)

            # stores all available ports in a dictionary
            self._ports: OrderedDict[str, Port] = OrderedDict([])

            self.initialized = True

    def __new__(cls, *args, **kwargs):
        # create singleton
        if not isinstance(cls._instance, cls):
            cls._instance = object.__new__(cls)
        return cls._instance

    def startup(self) -> None:
        """ function is called by SweepMe! """
        pass

    def on_load_setting(self) -> None:
        """ function is called by SweepMe! """
        self.clear_portmanager_dialog()

    def prepareRun(self) -> None:
        """ function is called by SweepMe! """
        self.open_resourcemanager()

    def prepareStop(self) -> None:
        """ function is called by SweepMe! """
        self.close_all_ports()
        self.close_resourcemanager()

    def clear_portmanager_dialog(self) -> None:
        """ to be overwritten by PortManagerDialog """
        pass

    def get_resources_available(self, port_types: list[str], port_identification: list[str] | None = None) -> list[str]:
        """Returns a list of resources for given port types.

        Called by SweepMe! to get resources for GUI when using 'Find Ports'.
        Attention: port identification is not properly implemented. Only works for USBTMC and if identification was
        already retrieved beforehand

        Args:
            port_types: list of port types, e.g. ['COM', 'GPIB']
            port_identification: list of identification strings

        Returns:
            List of resource strings
        """
        port_list = []

        for port_type in port_types:

            if port_type == "USB":
                port_type = "USBTMC"

            if port_type in Ports.port_types:
                resources = Ports.port_types[port_type].find_resources()

                port_list += resources

        for port in self._ports:
            if self._ports[port].port_properties["type"] in port_types:
                self._ports[port].port_properties["active"] = False

        # removing all inactive ports
        ports_to_delete = []

        for port in self._ports:
            if self._ports[port].port_properties["type"] in port_types:
                if self._ports[port].port_properties["active"] is False:
                    ports_to_delete.append(port)

        for port in ports_to_delete:
            del self._ports[port]

        # list all active ports of appropriate type
        for port in self._ports:
            _port_properties = self._ports[port].port_properties
            if _port_properties["type"] in port_types:
            
                if _port_properties["identification"] is not None and _port_properties["type"] in ["USB", "USBTMC"]:
                    if port_identification is not None:
                        for identification_string in port_identification:
                            if identification_string in str(_port_properties["identification"]):
                                port_list.append(str(_port_properties["resource"]))
                                break
                else:
                    port_list.append(str(_port_properties["resource"]))
        
        return port_list
               
    def get_port(self, resource: str, properties: PortProperties | None = None) -> Port | bool:
        """Returns a port object for a given resource name and properties.

        If the port already exists, it is updated with the given properties and returned. If the port does not exist, it
        is created with the given properties and returned. In both cases, the port is opened if it is not already open.

        Args:
            resource: str, name of resource to open, e.g., "COM1"
            properties: dictionary of with port properties

        Returns:
            pysweepme Port object
        """
        # check whether properties actually exist
        # we have to check it for all possible port types that are supported so far
        all_port_properties: dict[str, object] = {}
        for port_type in Ports.port_types.values():
            all_port_properties.update(port_type.properties)
        if properties is not None:
            for key in properties:
                if key not in all_port_properties:
                    debug("PortManager: property '%s' of port '%s' is unknown by any port type. Please check the "
                          "wiki (F1) which keywords are supported." % (key, resource))

        # the properties of the driver are overwritten by the properties of the port dialog
        # we add the port dialog properties after checking the use of proper keywords as the port dialog might introduce
        # some keywords like 'debug' that are not static properties of the port types
        portdialog_properties = self.get_port_properties_from_dialog(resource)
        if properties is None:
            properties = portdialog_properties
        else:
            properties.update(portdialog_properties)

        # depending on whether the port already exists or not, we have to create one or use the old one and refresh it.
        if resource not in self._ports:
            try:
                port = Ports.get_port(resource, properties)
                
                if not isinstance(port, Port):
                    debug("PortManager: port '%s' cannot be created. Please check the port troubleshooting "
                          "guide in the wiki (F1)." % resource)
                    return False    
                else:
                    self._ports[resource] = port
                    
            except:
                error()
                return False
                
        else:        
            # make sure the initial parameters are set, because the properties of the device class and the port dialog
            # should always be used on top of a fresh set of initialized parameters
            self._ports[resource].initialize_port_properties()
            self._ports[resource].update_properties(properties)

        # port is checked if being open and if not, port is opened
        self.open_port(resource)

        return self._ports[resource]

    def get_port_properties_from_dialog(self, resource: str) -> PortProperties:
        """
        function can be overwritten by a dialog in SweepMe! to return custom port properties for a given resource
        that are overwrite the port properties of the driver
        Args:
            resource: str

        Returns:
            dict: port properties
        """
        # no port properties are returned here as default
        # however, this changes when get_port_properties_from_dialog is overwritten by SweepMe! or any other app
        return {}

    def remove_port(self, resource: str) -> None:
        """Removes a port by resource name from the list of ports.

        Args:
            resource: str, resource name, e.g. "COM1"
        """
        if resource in self._ports:
            del self._ports[resource]

    @staticmethod
    def find_resources(port_types: list[str] | None = None) -> dict[str, list[str]]:
        """
        finds resources for given port types. If no port types are given, all possible port types are searched for
        resources
        Args:
            port_types: List of port types

        Returns:
            Dictionary containing a list of resource for each port type key
        """
        # all ports if not types are not specified
        if port_types is None:
            port_types = list(Ports.port_types.keys())

        resources = {}
        for port_type in port_types:
            if port_type == "USB":
                port_type = "USBTMC"
            try:
                resources[port_type] = Ports.port_types[port_type].find_resources()
            except:
                error("Unable to find ports for %s." % port_type)

        return resources

    @staticmethod
    def get_port_types() -> list[str]:
        """Returns a list of port types supported by pysweepme.Ports"""
        return Ports.get_porttypes()
        
    def set_port_logging(self, resource: str, state: bool) -> None:
        """
        change logging state by resource name

        Args:
            resource: str, name of the resource such as "COM1"
            state: bool
        """
        if resource not in self._ports:
            port = Ports.get_port(resource)
            if not isinstance(port, Port):
                return
            self._ports[resource] = port

        self._ports[resource].set_logging(state)
        
    def get_identification(self, resource: str) -> str:
        """
        returns identification string
        Args:
            resource: str, resource name, e.g. "GPIB0::1::INSTR"

        Returns:
            str -> Identification string
        """
        if resource not in self._ports:
            port = Ports.get_port(resource)
            if not isinstance(port, Port):
                return ""
            self._ports[resource] = port

        self.open_port(resource)
        identification = self._ports[resource].get_identification()
        self._ports[resource].close()
        self.close_resourcemanager()
        return identification

    def open_port(self, resource: str) -> None:
        """Opens port by resource name.

        Args:
            resource: str, name of resource e.g. "COM1"
        """
        if self._ports[resource].port_properties["open"] is False:
            self._ports[resource].open()

            if self._ports[resource].port_properties["clear"]:
                self._ports[resource].clear()

    def close_port(self, resource: str) -> None:
        """Closes port by resource name.

        Args:
            resource: str, name of resource e.g. "COM1"
        """
        if self._ports[resource].port_properties["open"] is True:
            self._ports[resource].close()

    @staticmethod
    def open_resourcemanager() -> None:
        """Creates a VISA resource manager, forwards the method from pysweepme.Ports"""
        Ports.get_resourcemanager()

    @staticmethod
    def close_resourcemanager() -> None:
        """Closes the VISA resource manager, forwards the method from pysweepme.Ports."""
        Ports.close_resourcemanager()

    @staticmethod
    def is_resourcemanager() -> bool:
        """Return True if the VISA resource manager is created, False otherwise."""
        return Ports.is_resourcemanager()
        
    def close_all_ports(self) -> None:
        """Closes all open ports."""
        for resource in self._ports:
            try:
                self.close_port(resource)
            except:
                error()

    @staticmethod
    def add_prologix_controller(port: str) -> None:
        """Add a Prologix controller by using a COM port.

        Args:
            port: str, COM port
        """
        Ports.add_prologix_controller(port)

    @staticmethod
    def remove_prologix_controller(port: str) -> None:
        """Removes a prologix controller by using a COM port.

        Args:
            port: str, COM port
        """
        Ports.remove_prologix_controller(port)
