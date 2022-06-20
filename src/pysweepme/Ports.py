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


import time
from .ErrorMessage import error, debug
import subprocess  # needed for TCPIP to find IP addresses

try:
    import serial
    import serial.tools.list_ports
    import serial.rs485
except:
    pass

try:
    import pyvisa
    import visa  # needed to make sure that DeviceClasses using 'import visa' work
except:
    pass
    
def get_debug_info():
    return pyvisa.util.get_debug_info(to_screen=False)

def get_porttypes():
    """ returns a list of all supported port types """ 

    return list(port_types.keys())

def get_resources(keys):
    """ returns all resource strings for the given list of port type string """ 

    resources = []

    for key in keys:
        resources += port_types[key].find_resources()
        
    return resources()

def open_resourcemanager(visafile_path = ""):
    """ returns an open resource manager instance """

    rm = None
    
    if visafile_path == "":
    
        possible_visa_paths = [
                               "",  # default path
                               "C:\\Windows\\System32\\visa32.dll",  # standard forwarding visa dll
                               "C:\\Program Files (x86)\\IVI Foundation\\VISA\\WinNT\\agvisa\\agbin\\visa32.dll",  #Agilent visa runtime
                               "C:\\Program Files (x86)\\IVI Foundation\\VISA\\WinNT\\RsVisa\\bin\\visa32.dll",  #RSvisa runtime
                              ]
    
        for visa_path in possible_visa_paths:
        
            try:
                rm = pyvisa.ResourceManager(visa_path)
                break
            except:
                continue
              
    else:
        try:
            rm = pyvisa.ResourceManager(visafile_path)
        except:
            error("Creating resource manager from visa dll file '%s' failed." % visafile_path)

    return rm

   
def close_resourcemanager():
    """ closes the current resource manager instance """
    
    try:
        # print("close ressource manager", rm.session)
        if not rm is None:
            rm.close()
    except:
        error()
        
    
    # if get_resourcemanager():
        # rm.close()
      
def get_resourcemanager():
    """ returns and open resource manager object"""

    # first, we have to figure out whether rm is open or closed
    # of open session is a handle, otherwise an error is raised
    # if rm is closed, we have to renew the resource manager
    # to finally return a useful object

    global rm
    
    try:
        rm.session # if object exists the resource manager is open
                
    except pyvisa.errors.InvalidSession:        
        rm = open_resourcemanager()
        
    except AttributeError: # if rm is not defined
        return False
        
    except:
        return False
        
    # print("get ressource manager", rm.session)
    # print("get visalib", rm.visalib)
 
    return rm

def is_resourcemanager():
    """ check whether there is a resource manager instance """

    if "rm" in globals():
        return True
    else:
        return False

def get_port(ID, properties={}):
    """returns an open port object for the given ID and port properties"""

    port = None

    for key in _ports:
        if ID.startswith(key):
            try:
                port = _ports[key](ID)
            except:
                error("Ports: Cannot create %s port object for %s" % (key, ID))
                return False

            break

    if not port:
        error("Ports: Cannot create port object for %s as port type is not defined." % ID)
        return False  

    # make sure the initial parameters are set
    port.initialize_port_properties()

    # here default properties are overwritten by specifications given in the DeviceClass
    # only overwrite by the DeviceClass which opens the port to allow to alter the properties further in open()
    port.port_properties.update(properties)             
                         
    # port is checked if being open and if not, port is opened
    if port.port_properties["open"] == False:
        
        # in open(), port_properties can further be changed by global PortDialog settings 
        port.open()
        
    # print(port.port_properties)    
        
    return port

def close_port(port): 
    """close the given port object"""
    # port is checked if being open and if so port is closed    
    if port.port_properties["open"] == True:
        port.close()
        
        
class PortType(object):
    """ base class for any port type such as GPIB, COM, USBTMC, etc. """

    GUIproperties = {}
    
    properties = {                                                          
                        "VID": None,
                        "PID": None,
                        "RegID": None,
                        "Manufacturer": None,
                        "Product": None,
                        "Description": None,
                        "identification": None, # String returned by the instrument
                        "query": None,
                        "Exception": True, # throws exception if no response by port
                        "EOL": "\n",
                        "EOLwrite": None,
                        "EOLread": None,
                        "timeout": 2,
                        "delay": 0.0,
                        "rstrip": True,
                }

    def __init__(self):
        
        self.ports = {}
       
        
    def find_resources(self):
        
        resources = self.find_resources_internal()
        return resources
        
    def find_resources_internal(self):
        return []
        
        
    def add_port(self, ID):
        pass
        

class COM(PortType):

    GUIproperties = {
                    "baudrate": ["50", "75", "110", "134", "150", "200", "300", "600", "1200", "1800", "2400", "4800", "9600", "19200", "38400", "57600", "115200"][::-1],
                    "terminator": [r"\n", r"\r", r"\r\n", r"\n\r"],
                    "parity": ["N", "O", "E", "M", "S"],
                    }
                    
                    
    properties = PortType.properties                
                   
    properties.update({
                        "baudrate": 9600,
                        "bytesize": 8,
                        "parity": 'N',
                        "stopbits": 1,
                        "xonxoff": False,
                        "rtscts": False,
                        "dsrdtr": False,
                        "rts": True,
                        "dtr": True, 
                        "raw_write": False,
                        "raw_read": False,
                        "encoding": "latin-1",
                        })
                    
    def __init__(self):
        super().__init__()

    def find_resources_internal(self):
    
        resources = []
        
        # we list all prologix com port addresses to exclude them from the com port resources
        prologix_addresses = []
        for controller in get_prologix_controllers():
            prologix_addresses.append(controller.get_address())
    
        try:
            for ID in serial.tools.list_ports.comports():

                ID = str(ID.device).split(' ')[0]
                
                if not ID in prologix_addresses:
                    resources.append(ID)
                
        except:
            error("Error during finding COM ports.")
        
        return resources

        
class GPIB(PortType):

    properties = PortType.properties                
                   
    properties.update({
                        "GPIB_EOLwrite": None,
                        "GPIB_EOLread": None,
                        })

    def __init__(self):
        super().__init__()
        
    
    def find_resources_internal(self):
    
        resources = []
        
        # check whether Prologix controller is used
        for controller in get_prologix_controllers():
            resources += controller.list_resources()
        
        # get visa resources
        if get_resourcemanager():
        
            resources += rm.list_resources("GPIB?*")
            
            ## one has to remove Interfaces such as ('GPIB0::INTFC',)
            resources = [x for x in resources if not "INTFC" in x]
        
        return resources
        
        
class PXI(PortType):

    properties = PortType.properties                
                   
    properties.update({
                        })

    def __init__(self):
        super().__init__()
        
    
    def find_resources_internal(self):
    
        resources = []
        
        # get visa resources
        if get_resourcemanager():
        
            resources += rm.list_resources("PXI?*")
            
            ## one has to remove Interfaces such as ('GPIB0::INTFC',)
            resources = [x for x in resources if not "INTFC" in x]
        
        return resources
       
       
class ASRL(PortType):

    properties = PortType.properties                
                   
    properties.update({
                        "baudrate"     : 9600,
                        "bytesize"     : 8,
                        "stopbits"     : 1,
                        "parity"       : "N",
                        # "flow_control" : 2,
                        })

    def __init__(self):
        super().__init__()
        
    
    def find_resources_internal(self):
    
        resources = []
        
        if get_resourcemanager():
        
            resources += rm.list_resources("ASRL?*")
                    
        return resources

               
        
class USBdevice(object):
    # created in order to collect all properties in one object
    
    def __init__(self):
    
        self.properties = {}
        
        for name in ('Availability', 'Caption', 'ClassGuid', 'ConfigManagerUserConfig',
             'CreationClassName', 'Description','DeviceID', 'ErrorCleared', 'ErrorDescription',
             'InstallDate', 'LastErrorCode', 'Manufacturer', 'Name', 'PNPDeviceID', 'PowerManagementCapabilities ',
             'PowerManagementSupported', 'Service', 'Status', 'StatusInfo', 'SystemCreationClassName', 'SystemName'):
             
            self.properties[name] = None
        
        
class USBTMC(PortType):

    properties = PortType.properties

    def __init__(self):
        super().__init__()
        
     
    def find_resources_internal(self):     
    
        resources = []
        
        if get_resourcemanager():
                    
            resources += rm.list_resources("USB?*")
            
        return resources
        
              

class TCPIP(PortType):

    def __init__(self):
        super().__init__()

    def find_resources_internal(self):
    
        resources = []

        if get_resourcemanager():
    
            resources += list(rm.list_resources("TCPIP?*"))
            # resources += ["TCPIP::xxx.xxx.xxx.xxx::port::SOCKET", "TCPIP::xxx.xxx.xxx.xxx::SOCKET", "TCPIP::www.example.com::INSTR"]
            # return resources

            """
            try:
            
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                process = subprocess.Popen("arp -a", shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, startupinfo=startupinfo)

                for line in iter(process.stdout.readline, b''):
                
                    try:
                        

                        for encoding in ["utf-8", "cp1251", "ascii"]:
                        
                            try:
                                text = line.decode(encoding) 
                                break
                            except:
                                pass
                    
                        try:
                            text = text.replace("\r", "").replace("\n", "")   
                        except:
                            continue
                    
                        if len(text) > 0:
                                
                            if text[0:2] == "  ":
                                
                                if not text.replace(" ", "").isalpha():
                                
                                    ip_addr, mac_addr, addr_type = text.split()
                                    
                                    # print(ip_addr, mac_addr, addr_type)
                                    
                                    if mac_addr != "ff-ff-ff-ff-ff-ff":
                                    
                                        resource = "TCPIP::"+ip_addr+"::INSTR"
                                        
                                        if not resource in resources:                            
                                            resources.append(resource)
                                            
                                        resource = "TCPIP::"+ip_addr+"::SOCKET"
                                        
                                        if not resource in resources:                            
                                            resources.append(resource)

                    except:
                        error()
                
            except:
                error()
                
            """
                
        # print(resources)            
        return resources

        
        """
        from pyVisa project page:
        
        TCPIP::dev.company.com::INSTR	
        -> A TCP/IP device using VXI-11 or LXI located at the specified address. This uses the default LAN Device Name of inst0.
        TCPIP0::1.2.3.4::999::SOCKET
        -> Raw TCP/IP access to port 999 at the specified IP address.
        """


class Port(object):
    """ base class for any port """
    
    def __init__(self, ID):
    
        self.port = None
        
        self.port_ID = ID
        self.port_properties = {
                                "type" : type(self).__name__[:-4],  # removeing port from the end of the port
                                "active": True,
                                "open": False,
                                "Name": None,
                                "NrDevices": 0,
                                "debug": False,
                                "ID": self.port_ID,  # String to open the device 'COM3', 'GPIB0::1::INSTR', ...
                                }
        
        
        self.initialize_port_properties()
                                    
        self.actualwritetime = time.perf_counter() 
        

    def __del__(self):
        pass
        
    def initialize_port_properties(self):
        
        # we need to know the PortType Object
        self.port_type = type(port_types[self.port_properties["type"]])
        
        # we have to overwrite with the properties of the Port_type
        self.update_properties(self.port_type.properties)
                                    
        # in case any port like to do something special, it has the chance now
        self.initialize_port_properties_internal()

    def initialize_port_properties_internal(self):
        pass
        
    def update_properties(self, properties = {}):
    
        self.port_properties.update(properties)
        
    def set_logging(self, state):
        self.port_properties["debug"] = bool(state)
        
    def get_logging(self, state):
        return self.port_properties["debug"]

    def get_identification(self):
        return "not available"

    def open(self):
              
        self.open_internal()           

        self.port_properties["open"] = True
        
    def open_internal(self):
        pass
        
    def close(self):  
    
        self.close_internal()
            
        self.port_properties["open"] = False
        
    def close_internal(self):
        pass

    def clear(self):
        """ clears the port, can be have different meaning depending on each port"""
        self.clear_internal()

    def clear_internal(self):
        """ function to be overwritten by each port to device what is done during clear"""
        pass
        
    def write(self, cmd):
        """ write a command via a port"""
        
        if self.port_properties["debug"]:
            debug(" ".join([self.port_properties["ID"], "write:", repr(cmd)]))
        
        if cmd != "":
            self.write_internal(cmd)
        
        
    def write_internal(self, cmd):
        pass
        
    def write_raw(self, cmd):
        """ write a command via a port without encoding"""
        
        if cmd != "":
            self.write_raw_internal(cmd)
            
    def write_raw_internal(self, cmd):
        # if this function is not overwritten, it defines a fallback to write()
        self.write(cmd)
        
    def read(self, digits=0):
        """ read a command from a port"""
    
        answer = self.read_internal(digits)
                              
        if self.port_properties["rstrip"] and not self.port_properties["raw_read"]:  # with 'raw_read', everything should be returned.
            answer = answer.rstrip()
            
        if self.port_properties["debug"]:
            debug(" ".join([self.port_properties["ID"], "read:", repr(answer)]))
            
        ## each port must decide on its own whether an empty string is a timeout error or not    
        # if answer == "" and self.port_properties["Exception"] == True:
            # self.close()
            # raise Exception('Port \'%s\' with ID \'%s\' does not respond. Check port properties, e.g. timeout, EOL,..' % (self.port_properties["type"],self.port_properties["ID"]) )

        return answer
        
    def read_internal(self, digits):
        # has to be overwritten by each Port
        return ""

    def read_raw(self, digits = 0):
        """ write a command via a port without encoding"""
        
        return self.read_raw_internal(digits)
            
    def read_raw_internal(self, digits):
        # if this function is not overwritten, it defines a fallback to read()
        return self.read(digits)
      

class GPIBport(Port):
    
    def __init__(self, ID):
        
        super(__class__,self).__init__(ID)

    def open_internal(self):
  
        ## differentiate between visa GPIB and prologix_controller
        if "Prologix" in self.port_properties["ID"]:
            
            com_port = self.port_properties["ID"].split("::")[-1][9:]  # we take the last part of the ID and cutoff 'Prologix@' to get the COM port
            
            # the prologix controller behaves like a port object and has all function like open, close, clear, write, read
            self.port = prologix_controller[com_port]
            
            # we give the prologix GPIB port the chance to setup
            self.port.open(self.port_properties)  
            
        else:
        
            if get_resourcemanager() ==  False:
                return False

            self.port = rm.open_resource(self.port_properties["ID"])
            self.port.timeout = self.port_properties["timeout"]*1000 # must be in ms now

            if self.port_properties["GPIB_EOLwrite"] != None:
                self.port.write_termination = self.port_properties["GPIB_EOLwrite"]
                
            if self.port_properties["GPIB_EOLread"] != None:
                self.port.read_termination = self.port_properties["GPIB_EOLread"]

    def close_internal(self):
        self.port.close()

    def clear_internal(self):
        self.port.clear()
        
    def get_identification(self):
        
        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):

        while time.perf_counter() - self.actualwritetime < self.port_properties["delay"]:
            time.sleep(0.01)
                                      
        if "Prologix" in self.port_properties["ID"]:
            self.port.write(cmd, self.port_properties["ID"].split("::")[1])
        
        else:
            self.port.write(cmd)
        
        self.actualwritetime = time.perf_counter()

    def read_internal(self, digits = 0):
             
        if "Prologix" in self.port_properties["ID"]:
            answer = self.port.read(self.port_properties["ID"].split("::")[1])
        else:
            answer = self.port.read()
            
        return answer      
    

class PXIport(Port):
    
    def __init__(self, ID):
        
        super(__class__,self).__init__(ID)
                                    
                                    
    def open_internal(self):

        if get_resourcemanager() ==  False:
            return False

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"]*1000 # must be in ms now

    def close_internal(self):
        self.port.close()

    def clear_internal(self):
        self.port.clear()
        
    def get_identification(self):
        
        self.write("*IDN?")
        return self.read()
        
        
    def write_internal(self, cmd):

        while time.perf_counter() - self.actualwritetime < self.port_properties["delay"]:
            time.sleep(0.01)

        self.port.write(cmd)
        
        self.actualwritetime = time.perf_counter()
        
        
    def read_internal(self, digits = 0):
             
        answer = self.port.read()
        return answer          
        
class ASRLport(Port):
    
    def __init__(self, ID):
        
        super(__class__,self).__init__(ID)

        from pyvisa.constants import StopBits, Parity

        self.parities = {
                    "N": Parity.none,
                    "O": Parity.odd,
                    "E": Parity.even,
                    "M": Parity.mark,
                    "S": Parity.space,
                    }
                    
        self.stopbits = {
                            1   : StopBits.one,
                            1.5 : StopBits.one_and_a_half,
                            2   : StopBits.two,
                            }
   
    # def initialize_port_properties_internal(self):
    
        # self.port_properties.update({
                                    # "baudrate"     : 9600,
                                    # "bytesize"     : 8,
                                    # "stopbits"     : 1,
                                    # "parity"       : "N",
                                    ## "flow_control" : 2,
                                    # })
                                    

    def open_internal(self):       
    
        if get_resourcemanager() ==  False:
            return False
    
        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = int(self.port_properties["timeout"])*1000  # must be in ms now
        self.port.baud_rate = int(self.port_properties["baudrate"])
        self.port.data_bits = int(self.port_properties["bytesize"])
        self.port.stop_bits = self.stopbits[float(self.port_properties["stopbits"])]
        self.port.parity = self.parities[str(self.port_properties["parity"])]
        # self.port.flow_control = self.parities[str(self.port_properties["parity"])]
        self.port.clear()

    def close_internal(self):  

        self.port.clear()
        self.port.close()
        self.port_properties["open"] = False

    def clear_internal(self):
        self.port.clear()
        
    def write_internal(self, cmd):
                    
        self.port.write(cmd)
        time.sleep(self.port_properties["delay"])  
        
    def read_internal(self, digits = 0):
                
        answer = self.port.read()
 
        return answer      
                
        
class USBTMCport(Port):
    
    def __init__(self, ID):
        
        super().__init__(ID)

    def open_internal(self):
    
        if get_resourcemanager() ==  False:
            return False

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"]*1000 # must be in ms now
                
    def close_internal(self):  

        self.port.close()

    def clear_internal(self):

        self.port.clear()

    def get_identification(self):
        
        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):
            
        self.port.write(cmd)

    def read_internal(self, digits = 0):

        answer = self.port.read()            
        return answer
        
        
class TCPIPport(Port):
    
    def __init__(self, ID):
        
        super(__class__,self).__init__(ID)

    def open_internal(self):
    
        if get_resourcemanager() ==  False:
            return False
    
        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"]*1000 # must be in ms now
            
    def close_internal(self):
        self.port.close()

    def clear_internal(self):
        self.port.clear()
        
    def get_identification(self):
        
        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):
    
        self.port.write(cmd)
        time.sleep(self.port_properties["delay"])
                 
        
    def read_internal(self, digits = 0):
        answer = self.port.read()
                
        return answer


        
class COMport(Port):
    
    def __init__(self, ID):
    
        
        super(__class__,self).__init__(ID)

        self.port = serial.Serial()

    # def initialize_port_properties_internal(self):
    
        # self.port_properties.update({
                                    # "baudrate": 9600,
                                    # "bytesize": 8,
                                    # "parity": 'N',
                                    # "stopbits": 1,
                                    # "xonxoff": False,
                                    # "rtscts": False,
                                    # "dsrdtr": False,
                                    # "rts": True,
                                    # "dtr": True, 
                                    # "raw_write": False,
                                    # "raw_read": False,
                                    # "encoding": "latin-1",
                                    # })
                                                     
   
    def refresh_port(self):
    
        self.port.port = str(self.port_properties["ID"])
        self.port.timeout = float(self.port_properties["timeout"])
        self.port.baudrate = int(self.port_properties["baudrate"])
        self.port.bytesize = int(self.port_properties["bytesize"])
        self.port.parity = str(self.port_properties["parity"])
        self.port.stopbits = self.port_properties["stopbits"]
        self.port.xonxoff = bool(self.port_properties["xonxoff"])
        self.port.rtscts = bool(self.port_properties["rtscts"])
        self.port.dsrdtr = bool(self.port_properties["dsrdtr"])
        self.port.rts = bool(self.port_properties["rts"])
        self.port.dtr = bool(self.port_properties["dtr"])
        
        
    def open_internal(self):

        self.refresh_port()
                            
        if not self.port.isOpen():
            self.port.open()
        else:
            self.port.close()
            self.port.open()

        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

    def close_internal(self):    
        self.port.close()
        self.port_properties["open"] = False

    def clear_internal(self):
        self.port.reset_input_buffer()
        self.port.reset_output_buffer()
        
    def write_internal(self, cmd):

        while time.perf_counter() - self.actualwritetime < self.port_properties["delay"]:
            time.sleep(0.01)
                            
        if self.port_properties["EOLwrite"] != None:    
            eol = self.port_properties["EOLwrite"]
        else: 
            eol = self.port_properties["EOL"]

        if not self.port_properties["raw_write"]:
            try:        
                cmd_bytes = (cmd + eol).encode(self.port_properties["encoding"])
            except:
                cmd_bytes = cmd + eol.encode(self.port_properties["encoding"])
                            
        else:
            cmd_bytes = cmd + eol.encode(self.port_properties["encoding"])
            # just send cmd as is without any eol/terminator because of raw_write
                            
        self.port.write(cmd_bytes)
            
        self.actualwritetime = time.perf_counter() 

    def read_internal(self, digits = 0):
                
        if digits == 0:
            answer, EOLfound = self.readline()
            
            if not self.port_properties["raw_read"]:
                try:
                    answer = answer.decode(self.port_properties["encoding"])
                except:
                    error("Unable to decode the reading from %s. Please check whether the baudrate and the terminator are correct (Ports -> PortManager -> COM). You can get the raw reading by setting the key 'raw_read' of self.port_properties to True" % (self.port_properties["ID"]))
                    raise
        else:
            answer = self.port.read(digits)
            
            EOLfound = True
            
            if not self.port_properties["raw_read"]:
                try:
                    answer = answer.decode(self.port_properties["encoding"])
                except:
                    error("Unable to decode the reading from %s. Please check whether the baudrate and the terminator are correct (Ports -> PortManager -> COM). You can get the raw reading by setting the key 'raw_read' of self.port_properties to True" % (self.port_properties["ID"]))
                    raise
                                    
        if answer == "" and not EOLfound and self.port_properties["Exception"] == True:
            self.close()
            raise Exception('Port \'%s\' with ID \'%s\' does not respond.\nCheck port properties, e.g. timeout, EOL,.. via Port -> PortManager -> COM' % (self.port_properties["type"],self.port_properties["ID"]) )
                    
        return answer
        
    def write_raw_internal(self, cmd):
    
        current = self.port_properties["raw_write"]
        self.port_properties["raw_write"] = True
        self.write(cmd)
        self.port_properties["raw_write"] = current
        
    def read_raw_internal(self, digits):
    
        current = self.port_properties["raw_read"]
        self.port_properties["raw_read"] = True
        answer = self.read(digits)
        self.port_properties["raw_read"] = current

        return answer

    def in_waiting(self):
        return self.port.in_waiting
        
    def readline(self):
        # this function allows to change the EOL, rewritten from pyserial
        
        if self.port_properties["EOLread"] != None:
            EOL = self.port_properties["EOLread"].encode(self.port_properties["encoding"])
        else:
            EOL = self.port_properties["EOL"].encode(self.port_properties["encoding"])
                        
        
        leneol = len(EOL)
        line = bytearray()
        
        EOL_found = False
        
        while True:
            c = self.port.read(1)
            if c:
                line += c
                if line[-leneol:] == EOL:
                    EOL_found = True
                    break
                    
            else:
                break
                
        return bytes(line[:-leneol]), EOL_found
        
        
class PrologixGPIBcontroller():
                
    def __init__(self, address):
    
        # basically the address could be used for COM ports but also for Ethernet
        # at the moment, only COM is supported, but Ethernet could be added later
        self.set_address(address)
        
        self._current_gpib_ID = None
        
        self.ID_port_properties = {}
        
        self.port = serial.Serial()
        self.port.port = self.get_address()
        self.port.baudrate = 115200  # fixed, Prologix adapter automatically recognize the baudrate (tested with v6.0)
        
        self.terminator_character =  {
                                        "\r\n":0,
                                        "\r": 1,
                                        "\n": 2, 
                                        "": 3,
                                        }
        
        
    def set_address(self, address):
        self._address = str(address)
    
    def get_address(self):
        return self._address

    def list_resources(self):
        if not self._address is None:
            return ["GPIB::%i::Prologix@%s" % (i, self._address) for i in range(1,31,1)]
        else:
            return []

    def open(self, port_properties):
    
        ID = port_properties["ID"].split("::")[1]

        self.ID_port_properties[ID] = port_properties
       
        if not self.port.isOpen():
            self.port.open()
        
        self.port.timeout = self.ID_port_properties[ID]["timeout"]        
        self.port.timeout = 0.1     
            
        self.port.reset_input_buffer()
        self.port.reset_output_buffer() 
        
        self.set_controller_in_charge()  # Controller in Charge CIC
           
        self.set_mode(1)  # 1 = controller mode
        
        terminator = "\r\n"
        
        if self.ID_port_properties[ID]["GPIB_EOLwrite"] != None:
            terminator = self.ID_port_properties[ID]["GPIB_EOLwrite"]
                
        if self.ID_port_properties[ID]["GPIB_EOLread"] != None:
            terminator = self.ID_port_properties[ID]["GPIB_EOLread"]

        if terminator in self.terminator_character:
            terminator_index = self.terminator_character[terminator]
        else:
            debug("Terminator '%s' cannot be set for Prologix adapter at %s. Fallback to CR/LF." % (repr(terminator), str(ID)))
            terminator_index = 0 #CR/LF

        self.set_eos(terminator_index)    # see self.terminator_character for all options
        
        self.set_eoi(1)   # 1 = eoi at end
        
        self.set_auto(0)  # 0 =  no read-after-write
        
        self.set_read_timeout(0.05)  # read timeout in s
        # self.set_readtimeout(self.ID_port_properties[ID]["timeout"])  # read timeout in s
        
        # print("mode to listenonly set")

    def clear(self):
        if self.port.isOpen():
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()    

    def close(self):
        if self.port.isOpen():
            self.port.close()
        

    def write(self, cmd = "", ID = ""):
        """ sends a non-empty command string to the prologix controller and changes the GPIB address if needed beforehand """
    
        if cmd != "":
    
            if ID == "" or cmd.startswith("++"):
                msg = (cmd+"\n").encode('latin-1')
                
            else:
          
                if ID != self._current_gpib_ID:
                    
                    self._current_gpib_ID = str(ID)
                    
                    ## set to current GPIB address
                    ## calls 'write' again, but as the command starts with '++' will not lead to an endless iteration
                    self.write("++addr %s" % self._current_gpib_ID)  
                
                ## some special characters need to be escaped before sending
                ## we start to replace ESC as it will be added by other commands as well and would be otherwise replaced again
                cmd.replace(chr(27), chr(27)+chr(27)) # ESC (ASCII 27)
                cmd.replace(chr(13), chr(27)+chr(13)) # CR  (ASCII 13)
                cmd.replace(chr(10), chr(27)+chr(10)) # LF  (ASCII 10)
                cmd.replace(chr(43), chr(27)+chr(43)) # ‘+’ (ASCII 43) 

                msg = (cmd+"\n").encode(self.ID_port_properties[ID]["encoding"])
                
            # print("write:", msg)
            self.port.write(msg)

        
    def read(self, ID):
        """ requests an answer from the instruments and returns it """

        # time.sleep(self.ID_port_properties[ID]["delay"])  # needed to make sure that there is a short delay since the last write     
    
        # print("in waiting:", self.port.in_waiting)
    
        starttime = time.perf_counter()
        
        msg = b""
        
        while time.perf_counter() - starttime < self.ID_port_properties[ID]["timeout"]:
                       
            self.write("++read eoi")  # requesting an answer
         
            msg += self.port.readline()
            # print("Prologix read message:", msg)

            if b'\n' in msg:
                break
            
        
        if self.ID_port_properties[ID]["rstrip"]:
            msg = msg.rstrip()
                        
        return msg.decode(self.ID_port_properties[ID]["encoding"])
        
        
    def set_controller_in_charge(self):
        self.write("++ifc")

    def set_mode(self, mode):
        self.write("++mode %s" % str(mode))
        
    def get_mode(self):
        self.write("++mode")
        return self.port.readline().rstrip().decode()
    
    def set_eos(self, eos):
        self.write("++eos %s" % str(eos))  # EOS terminator - 0:CR+LF, 1:CR, 2:LF, 3:None
           
    def get_eos(self):
        self.write("++eos")
        return self.port.readline().rstrip().decode()

    def set_eoi(self, eoi):
        self.write("++eoi %s" % str(eoi))  #  0 = no eoi at end, 1 = eoi at end
           
    def get_eoi(self):
        self.write("++eoi")
        return self.port.readline().rstrip().decode()

    def set_auto(self, auto):
        self.write("++auto %s" % str(auto))  # 0 not read-after-write, 1 = read-after-write

    def get_auto(self):
        self.write("++auto")
        return self.port.readline().rstrip().decode()
        
        
    def set_read_timeout(self, readtimeout):
        """ set the read timeout in s """
        
        self.write("++read_tmo_ms %i" % int(max(1, min( 3000,float(readtimeout)*1000 ) ) ) )  # conversion from s to ms, maximum is 3000, minimum is 1
        
    def get_readtimeout(self):
        self.write("++read_tmo_ms")
        return float(self.port.readline().rstrip().decode())/1000.0  # conversion from ms to s
        
    def set_listenonly(self, listenonly):
        """ set listen-only, only supported in mode = device! """
        self.write("++lon %s" % str(listenonly))  # 0 disable 'listen-only' mode, 1 enable 'listen-only' mode

    def get_listenonly(self):
        self.write("++lon")
        return self.port.readline().rstrip().decode()
        
    def get_version(self):
        self.write("++ver")
        return self.port.readline().rstrip().decode()


def add_prologix_controller(address):
    controller = PrologixGPIBcontroller(address) 
    prologix_controller[address] = controller
    
def remove_prologix_controller(address):
    if address in prologix_controller:
        del prologix_controller[address]
    
def get_prologix_controllers():
    return list(prologix_controller.values())
              
              
prologix_controller = {}
# add_prologix_controller("COM23")

rm = open_resourcemanager()

port_types = {
             "COM" : COM(),
             "GPIB": GPIB(),
             "PXI": PXI(),
             # "ASRL": ASRL(), # Serial communication via visa runtime, just used for testing at the moment
             "USBTMC": USBTMC(),
             "TCPIP": TCPIP(),
             }

_ports = {
    "COM": COMport,
    "GPIB": GPIBport,
    "PXI": PXIport,
    "USBTMC": USBTMCport,
    "USB": USBTMCport,
    "TCPIP": TCPIPport,
}
             

""" """