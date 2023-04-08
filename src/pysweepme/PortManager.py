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
import sys

if __name__ == "__main__":
    pysweepme_repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # print("pysweepme path:", pysweepme_repo_path)
    sys.path.insert(0, pysweepme_repo_path)

from collections import OrderedDict

from pysweepme.ErrorMessage import error, debug
from pysweepme import Ports
from pysweepme import FolderManager
from pysweepme import ConfigurationManager

try:
    import clr  # pythonnet for loading external DotNet DLLs
except ModuleNotFoundError:
    error("Package clr/pythonnet not installed. Use 'pip install pythonnet' in command line.")
except ImportError:
    error("Cannot import clr package. Please check whether your Microsoft .NET Framework is up to date.")

FoMa = FolderManager.FolderManager()


class PortManager(object):

    _instance = None

    def __init__(self):

        if not hasattr(self, "initialized"):

            # Adding Prologix controllers
            ProgramConfig = ConfigurationManager.Config(FoMa.get_file("CONFIG"))
            prologix_controller = ProgramConfig.getConfigOptions("PrologixController")
            for port in prologix_controller.values():
                self.add_prologix_controller(port)

            # stores all available ports in a dictionary
            self._ports = OrderedDict([])

            self.initialized = True

    def __new__(class_, *args, **kwargs):
        # create singleton
        if not isinstance(class_._instance, class_):
            class_._instance = object.__new__(class_)
        return class_._instance

    def startup(self):
        pass

    def get_resources_available(self, port_types, update=False, port_identification=[]):
        # called by SweepMe! to get resources for GUI when using Find Ports
        # port_types is a list of Port types (string), e.g. ['COM', 'GPIB']

        update = True
        port_list = []

        if update:
        
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
            if self._ports[port].port_properties["type"] in port_types:
            
                if not self._ports[port].port_properties["identification"] is None and self._ports[port].port_properties["type"] in ["USB", "USBTMC"]:
                    
                    for identification_string in port_identification:
                        if identification_string in self._ports[port].port_properties["identification"]:
                            port_list.append(self._ports[port].port_properties["resource"])
                            break
                else:
                    port_list.append(self._ports[port].port_properties["resource"])
        
        return port_list
               
    def get_port(self, resource, properties={}):

        # check whether properties actually exist
        # we have to check it for all possible port types that are supported so far
        all_port_properties = {}
        for port_type in Ports.port_types.values():
            all_port_properties.update(port_type.properties)
        for key in properties:
            if key not in all_port_properties:
                debug("PortManager: property '%s' of port '%s' is unknown by any port type. Please check the "
                      "wiki (F1) which keywords are supported." % (key, resource))

        # the properties of the driver are overwritten by the properties of the port dialog
        # we add the port dialog properties after checking the use of proper keywords as the port dialog might introduce
        # some keywords like 'debug' that are not static properties of the port types
        portdialog_properties = self.get_port_properties_from_dialog(resource)
        properties.update(portdialog_properties)

        # depending on whether the port already exists or not, we have to create one or use the old one and refresh it.
        if resource not in self._ports:
            try:
                port = Ports.get_port(resource, properties)
                
                if port is False:
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
        if self._ports[resource].port_properties["open"] is False:
            self._ports[resource].open()
                  
        # print("Port properties after:", self._ports[resource].port_properties)

        return self._ports[resource]

    def get_port_properties_from_dialog(self, resource):
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

    def remove_port(self, resource):
        
        if resource in self._ports:
            del self._ports[resource]

    def find_resources(self, port_types=None):

        # all ports if not types are not specified
        if port_types is None:
            port_types = Ports.port_types

        resources = {}
        for port_type in port_types:
            if port_type == "USB":
                port_type = "USBTMC"
            try:
                resources[port_type] = Ports.port_types[port_type].find_resources()
            except:
                error("Unable to find ports for %s." % port_type)

        return resources
        
    def get_port_types(self):
        return Ports.port_types.keys()
        
    def set_port_logging(self, resource, state):
    
        if resource not in self._ports:
            self._ports[resource] = Ports.get_port(resource)

        self._ports[resource].set_logging(state)
        
    def get_identification(self, resource):

        if resource not in self._ports:
            self._ports[resource] = Ports.get_port(resource)
        
        self._ports[resource].open()
        identification = self._ports[resource].get_identification()
        self._ports[resource].close()
        self.close_Resourcemanager()
        return identification

    def close_port(self, resource):
        # port is checked if being open and if so port is closed    
        if self._ports[resource].port_properties["open"] is True:
            self._ports[resource].close()

    def prepareRun(self):
        self.open_resourcemanager()

    def prepareStop(self):
        self.close_all_ports()
        self.close_resourcemanager()

    def open_resourcemanager(self):
        # we have to open the resourcemanager again as we close it after each run
        Ports.get_resourcemanager()
 
    def close_resourcemanager(self):
        # we close the resourcemanager so that other computers/interfaces can access the equipment
        Ports.close_resourcemanager()
        
    def close_all_ports(self):
        
        for ID in self._ports:
            if self._ports[ID].port_properties["open"] is True:
                try:
                    self._ports[ID].close()
                except:
                    error()
        
    def add_prologix_controller(self, port):
        Ports.add_prologix_controller(port)

    def remove_prologix_controller(self, port):
        Ports.remove_prologix_controller(port)


if __name__ == "__main__":

    PM1 = PortManager()
    print("First PortManager:", PM1, id(PM1))

    PM2 = PortManager()
    print("Second PortManager:", PM2, id(PM2))

    print(PM1.find_resources(["COM"]))

    ser1 = PM2.get_port("COM8")
    ser2 = PM1.get_port("COM9")

    ser1.write("Test")
    msg = ser2.read()
    print("Returned message", msg)

    ser1 = PM1.get_port("COM8")
    ser1.write("Test")
    msg = ser2.read()
    print("Returned message", msg)

    ser1.close()
    ser2.close()
