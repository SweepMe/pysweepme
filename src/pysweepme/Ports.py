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

import re
import socket
import time
from typing import Tuple, Any, Union

import psutil

from .ErrorMessage import debug, error

# import subprocess  # needed for TCPIP to find IP addresses

try:
    import serial
    import serial.rs485
    import serial.tools.list_ports
except:
    pass

try:
    import pyvisa
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

    return resources


def open_resourcemanager(visafile_path=""):
    """ returns an open resource manager instance """

    rm = None

    if visafile_path == "":

        possible_visa_paths = [
            # default path:
            "",
            # standard forwarding visa dll:
            "C:\\Windows\\System32\\visa32.dll",
            # Agilent visa runtime:
            "C:\\Program Files (x86)\\IVI Foundation\\VISA\\WinNT\\agvisa\\agbin\\visa32.dll",
            # RSvisa runtime:
            "C:\\Program Files (x86)\\IVI Foundation\\VISA\\WinNT\\RsVisa\\bin\\visa32.dll",
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
        # print("close resource manager", rm.session)
        if rm is not None:
            rm.close()
    except:
        error()


def get_resourcemanager():
    """ returns and open resource manager object"""

    # first, we have to figure out whether rm is open or closed
    # of open session is a handle, otherwise an error is raised
    # if rm is closed, we have to renew the resource manager
    # to finally return a useful object

    global rm

    try:
        rm.session  # if object exists the resource manager is open

    except pyvisa.errors.InvalidSession:
        rm = open_resourcemanager()

    except AttributeError:  # if rm is not defined
        return False

    except:
        return False

    # print("get resource manager", rm.session)
    # print("get visalib", rm.visalib)

    return rm


def is_resourcemanager():
    """ check whether there is a resource manager instance """

    if "rm" in globals():
        return True
    else:
        return False


def is_IP(port_str) -> Tuple[bool, str, int]:
    error_response = (False, "", -1)
    port_str = port_str.strip()
    result = re.search(r"(\d{1,3}).(\d{1,3}).(\d{1,3}).(\d{1,3}):(\d{1,5})", port_str)

    if not result:
        return error_response

    for i in range(1, 5):
        if int(result.group(i)) <= 255:
            continue
        else:
            return error_response

    if not 0 < int(result.group(5)) <= 65535:
        return error_response

    ip = ".".join([result.group(i) for i in range(1, 5)])
    host = int(result.group(5))

    return True, ip, host


def get_port(ID, properties={}):
    """returns an open port object for the given ID and port properties"""

    port: Port

    if ID.startswith("GPIB"):

        try:
            port = GPIBport(ID)
        except:
            error("Ports: Cannot create GPIB port object for %s" % ID)
            return False
    # TODO: Prologix can be removed here, if ID does not start with Prologix anymore
    elif ID.startswith("PXI"):

        try:
            port = PXIport(ID)
        except:
            error("Ports: Cannot create PXI port object for %s" % ID)
            return False

    elif ID.startswith("ASRL"):

        try:
            port = ASRLport(ID)
        except:
            error("Ports: Cannot create ASRL port object for %s" % ID)
            return False

    elif ID.startswith("TCPIP"):

        try:
            port = TCPIPport(ID)
        except:
            error("Ports: Cannot create TCPIP port object for %s" % ID)
            return False

    elif ID.startswith("COM"):

        try:
            port = COMport(ID)
        except:
            error("Ports: Cannot create COM port object for %s" % ID)
            return False

    elif ID.startswith("SOCKET") or is_IP(ID)[0]:
        # actually, the ID must not start with SOCKET, it only works for IPv4 addresses
        try:
            port = SOCKETport(ID)
        except Exception:
            error("Ports: Cannot create Socket port object for %s" % ID)

    elif ID.startswith("USB") or ID.startswith("USBTMC"):

        try:
            port = USBTMCport(ID)
        except:
            error("Ports: Cannot create USBTMC port object for %s" % ID)
            return False

    else:
        error("Ports: Cannot create port object for %s as port type is not defined." % ID)
        return False

    # make sure the initial parameters are set
    port.initialize_port_properties()

    # here default properties are overwritten by specifications given in the DeviceClass
    # only overwrite by the DeviceClass which opens the port to allow to alter the properties further in open()
    port.port_properties.update(properties)

    # port is checked if being open and if not, port is opened
    if port.port_properties["open"] is False:

        # in open(), port_properties can further be changed by global PortDialog settings
        port.open()

    if port.port_properties["clear"]:
        port.clear()

    return port


def close_port(port):
    """close the given port object"""
    # port is checked if being open and if so port is closed
    if port.port_properties["open"] is True:
        port.close()


class PortType(object):
    """ base class for any port type such as GPIB, COM, USBTMC, etc. """

    GUIproperties: dict[str, Any] = {}

    properties = {
        "VID": None,
        "PID": None,
        "RegID": None,
        "Manufacturer": None,
        "Product": None,
        "Description": None,
        "identification": None,  # String returned by the instrument
        "query": None,
        "Exception": True,  # throws exception if no response by port
        "EOL": "\n",
        "EOLwrite": None,
        "EOLread": None,
        "timeout": 2,
        "delay": 0.0,
        "rstrip": True,
        "debug": False,
        "clear": True,
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
        "baudrate": [
            "50", "75", "110", "134", "150", "200", "300", "600", "1200", "1800", "2400", "4800", "9600", "19200",
            "38400", "57600", "115200"
        ][::-1],
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

                id_str = str(ID.device).split(' ')[0]

                if id_str not in prologix_addresses:
                    resources.append(id_str)

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

            # one has to remove Interfaces such as ('GPIB0::INTFC',)
            resources = [x for x in resources if "INTFC" not in x]

        return resources


class PXI(PortType):

    properties = PortType.properties

    properties.update({})

    def __init__(self):
        super().__init__()

    def find_resources_internal(self):

        resources = []

        # get visa resources
        if get_resourcemanager():

            resources += rm.list_resources("PXI?*")

            # one has to remove Interfaces such as ('GPIB0::INTFC',)
            resources = [x for x in resources if "INTFC" not in x]

        return resources


class ASRL(PortType):

    properties = PortType.properties

    properties.update({
        "baudrate": 9600,
        "bytesize": 8,
        "stopbits": 1,
        "parity": "N",
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

        self.properties: dict[str, Any] = {}

        for name in ('Availability', 'Caption', 'ClassGuid', 'ConfigManagerUserConfig', 'CreationClassName',
                     'Description', 'DeviceID', 'ErrorCleared', 'ErrorDescription', 'InstallDate', 'LastErrorCode',
                     'Manufacturer', 'Name', 'PNPDeviceID', 'PowerManagementCapabilities', 'PowerManagementSupported',
                     'Service', 'Status', 'StatusInfo', 'SystemCreationClassName', 'SystemName'):

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
    properties = PortType.properties

    properties.update({
        "TCPIP_EOLwrite": None,
        "TCPIP_EOLread": None,
    })

    def __init__(self):
        super().__init__()

    def find_resources_internal(self):

        resources = []

        if get_resourcemanager():

            resources += list(rm.list_resources("TCPIP?*"))

        return resources


class SOCKET(PortType):

    properties = PortType.properties
    properties.update({
        "encoding": "latin-1",
        "SOCKET_EOLwrite": None,
        "SOCKET_EOLread": None,
    })

    def find_resources_internal(self):
        """ find IPv4 addresses"""
        connections = psutil.net_connections()
        # For UNIX type sockets, conn.laddr will contain a path tuple instead of IP / Port.
        # Therefore we must ensure that conn.laddr is actually of the type psutil._common.addr
        connection_strings = [
            f"{conn.laddr.ip}:{conn.laddr.port}" for conn in connections
            if conn.status == "LISTEN" and isinstance(conn.laddr, psutil._common.addr)  # noqa: SLF001
            and conn.laddr.ip != "0.0.0.0" and not conn.laddr.ip.startswith("::")  # noqa: S104 (false positive)
        ]
        return connection_strings


class Port(object):
    """ base class for any port """

    def __init__(self, ID):

        self.port = None
        self.port_ID = ID
        self.port_properties = {
            # The Port Type, e.g. "COM", "GPIB"
            "type": type(self).__name__[:-4],  # removing "port" from the end of the port
            # Do not use active
            "active": True,
            # Whether the port is currently opened
            "open": False,
            # If the port shall be cleared at the beginning of a measurement (after it is opened)
            "clear": True,
            # Do not use Name
            "Name": None,
            # Deprecated, use device_communication instead
            "NrDevices": 0,
            # Enable debugging output for the port
            "debug": False,
            # String identifying the port to open 'COM3', 'GPIB0::1::INSTR', ...
            "ID": self.port_ID,
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

    def update_properties(self, properties={}):

        self.port_properties.update(properties)

    def set_logging(self, state):
        self.port_properties["debug"] = bool(state)

    def get_logging(self):
        return self.port_properties["debug"]

    def get_identification(self) -> str:
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

    def clear(self) -> None:
        """Clears the port, can have different meaning depending on each port."""
        self.clear_internal()

    def clear_internal(self) -> None:
        """Function to be overwritten by each port to device what is done during clear."""

    def write(self, cmd: str) -> None:
        """Write a command via a port."""
        if self.port_properties["debug"]:
            debug(" ".join([self.port_properties["ID"], "write:", repr(cmd)]))

        if cmd != "":
            self.write_internal(cmd)

    def write_internal(self, cmd: str) -> None:
        """Function to be overwritten by each port to define how to write a command."""

    def write_raw(self, cmd) -> None:
        """Write a command via a port without encoding."""
        if cmd != "":
            self.write_raw_internal(cmd)

    def write_raw_internal(self, cmd) -> None:
        """Function to be overwritten by each port to define how to write a command without encoding."""
        # if this function is not overwritten, it defines a fallback to write()
        self.write(cmd)

    def read(self, digits=0) -> str:
        """Read a command from a port."""
        answer = self.read_internal(digits)

        # with 'raw_read', everything should be returned.
        if self.port_properties["rstrip"] and not self.port_properties["raw_read"]:
            answer = answer.rstrip()

        if self.port_properties["debug"]:
            debug(" ".join([self.port_properties["ID"], "read:", repr(answer)]))

        # each port must decide on its own whether an empty string is a timeout error or not
        # if answer == "" and self.port_properties["Exception"] == True:
        # self.close()
        # raise Exception('Port \'%s\' with ID \'%s\' does not respond. Check port properties, e.g. '
        #                 'timeout, EOL,..' % (self.port_properties["type"],self.port_properties["ID"]) )

        return answer

    def read_internal(self, digits: int) -> str:
        """Function to be overwritten by each port to define how to read a command."""
        return ""

    def read_raw(self, digits: int = 0) -> str:
        """Write a command via a port without encoding"""
        return self.read_raw_internal(digits)

    def read_raw_internal(self, digits: int) -> str:
        """Function to be overwritten by each port to define how to read a command without encoding."""
        # if this function is not overwritten, it defines a fallback to read()
        return self.read(digits)

    def query(self, cmd: str, digits: int = 0) -> str:
        """Write a command to the port and read the response."""
        self.write(cmd)
        return self.read(digits=digits)


class GPIBport(Port):

    port: Union[pyvisa.resources.GPIBInstrument, PrologixGPIBcontroller]

    def __init__(self, ID):

        super().__init__(ID)

    def open_internal(self):

        # differentiate between visa GPIB and prologix_controller
        if "Prologix" in self.port_properties["ID"]:
            # we take the last part of the ID and cutoff 'Prologix@' to get the COM port
            com_port = self.port_properties["ID"].split("::")[-1][9:]

            # the prologix controller behaves like a port object
            # and has all function like open, close, clear, write, read
            self.port = prologix_controller[com_port]

            # we give the prologix GPIB port the chance to setup
            self.port.open(self.port_properties)

        else:
            if get_resourcemanager() is False:
                return
            self.port: pyvisa.resources.Resource

            self.port = rm.open_resource(self.port_properties["ID"])
            if isinstance(self.port, PrologixGPIBcontroller):
                raise TypeError("Prologix port resource found within non-prologix port object.")

            self.port.timeout = self.port_properties["timeout"] * 1000  # must be in ms now

            if self.port_properties["GPIB_EOLwrite"] is not None:
                self.port.write_termination = self.port_properties["GPIB_EOLwrite"]

            if self.port_properties["GPIB_EOLread"] is not None:
                self.port.read_termination = self.port_properties["GPIB_EOLread"]

    def close_internal(self):
        self.port.close()

    def clear_internal(self) -> None:
        """Clear the port."""
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

    def read_internal(self, digits=0):

        if "Prologix" in self.port_properties["ID"]:
            answer = self.port.read(self.port_properties["ID"].split("::")[1])
        else:
            if isinstance(self.port, PrologixGPIBcontroller):
                raise TypeError("Prologix port resource found within non-prologix port object.")
            answer = self.port.read()

        return answer


class PXIport(Port):

    port: pyvisa.resources.PXIInstrument

    def __init__(self, ID):

        super().__init__(ID)

    def open_internal(self):

        if get_resourcemanager() is False:
            return

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"] * 1000  # must be in ms now

    def close_internal(self):
        self.port.close()

    def clear_internal(self) -> None:
        """Clear the port."""
        self.port.clear()

    def get_identification(self):

        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):

        while time.perf_counter() - self.actualwritetime < self.port_properties["delay"]:
            time.sleep(0.01)

        self.actualwritetime = time.perf_counter()
        exc_msg = ("Writing to PXIInstruments has not been implemented yet "
                   "and needs to be handled by the driver itself.")
        raise NotImplementedError(exc_msg)

    def read_internal(self, digits=0):
        exc_msg = ("Reading from PXIInstruments has not been implemented yet "
                   "and needs to be handled by the driver itself.")
        raise NotImplementedError(exc_msg)


class ASRLport(Port):

    port: pyvisa.resources.SerialInstrument

    def __init__(self, ID):

        super().__init__(ID)

        from pyvisa.constants import Parity, StopBits

        self.parities = {
            "N": Parity.none,
            "O": Parity.odd,
            "E": Parity.even,
            "M": Parity.mark,
            "S": Parity.space,
        }

        self.stopbits = {
            1: StopBits.one,
            1.5: StopBits.one_and_a_half,
            2: StopBits.two,
        }

    # def initialize_port_properties_internal(self):

    # self.port_properties.update({
    #                             "baudrate"     : 9600,
    #                             "bytesize"     : 8,
    #                             "stopbits"     : 1,
    #                             "parity"       : "N",
    #                             "flow_control" : 2,
    #                             })

    def open_internal(self):

        if get_resourcemanager() is False:
            return

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = int(self.port_properties["timeout"]) * 1000  # must be in ms now
        self.port.baud_rate = int(self.port_properties["baudrate"])
        self.port.data_bits = int(self.port_properties["bytesize"])
        self.port.stop_bits = self.stopbits[float(self.port_properties["stopbits"])]
        self.port.parity = self.parities[str(self.port_properties["parity"])]
        # self.port.flow_control = self.parities[str(self.port_properties["parity"])]

    def close_internal(self):
        self.port.close()
        self.port_properties["open"] = False

    def clear_internal(self) -> None:
        """Clear the port."""
        self.port.clear()

    def write_internal(self, cmd):

        self.port.write(cmd)
        time.sleep(self.port_properties["delay"])

    def read_internal(self, digits=0):

        answer = self.port.read()

        return answer


class USBTMCport(Port):

    port: pyvisa.resources.USBInstrument

    def __init__(self, ID):

        super().__init__(ID)

    def open_internal(self):

        if get_resourcemanager() is False:
            return

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"] * 1000  # must be in ms now

    def close_internal(self):
        self.port.close()

    def clear_internal(self) -> None:
        """Clear the port."""
        self.port.clear()

    def get_identification(self):

        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):

        self.port.write(cmd)

    def read_internal(self, digits=0):

        answer = self.port.read()
        return answer


class TCPIPport(Port):

    port: pyvisa.resources.TCPIPInstrument

    def __init__(self, ID):

        super().__init__(ID)

    def open_internal(self):

        if get_resourcemanager() is False:
            return

        self.port = rm.open_resource(self.port_properties["ID"])
        self.port.timeout = self.port_properties["timeout"] * 1000  # must be in ms now

        if self.port_properties["TCPIP_EOLwrite"] is not None:
            self.port.write_termination = self.port_properties["TCPIP_EOLwrite"]

        if self.port_properties["TCPIP_EOLread"] is not None:
            self.port.read_termination = self.port_properties["TCPIP_EOLread"]

    def close_internal(self):
        self.port.close()

    def clear_internal(self) -> None:
        """Clear the port."""
        self.port.clear()

    def get_identification(self):

        self.write("*IDN?")
        return self.read()

    def write_internal(self, cmd):

        self.port.write(cmd)
        time.sleep(self.port_properties["delay"])

    def read_internal(self, digits=0):
        answer = self.port.read()

        return answer


class SOCKETport(Port):

    port: socket.socket

    def __init__(self, ID):

        super().__init__(ID)

        self.buffer: str = ""
        """A buffer to store the incoming data."""

    def open_internal(self):
        # Clear buffer
        self.buffer = ""

        port_ID = self.port_properties["ID"]
        ok, HOST, PORT = is_IP(port_ID)
        if not ok:
            # this can happen if HOST is no IPv4 address but a domain or localhost
            HOST, PORT = port_ID.split(":")

        self.port = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port.settimeout(0.1)
        self.port.connect((HOST, int(PORT)))

        if self.port_properties["SOCKET_EOLwrite"] is not None:
            self.write_termination = self.port_properties["SOCKET_EOLwrite"]
        else:
            self.write_termination = ""

        if self.port_properties["SOCKET_EOLread"] is not None:
            self.read_termination = self.port_properties["SOCKET_EOLread"]
        else:
            self.read_termination = ""

        self.last_writetime = time.time()

    def close_internal(self):
        self.port.close()

    def get_identification(self):

        self.write("*IDN?")
        return self.read()

    def clear_internal(self) -> None:
        """Clear the buffer."""
        # workaround: read until the buffer is empty
        while True:
            try:
                self.read_chunk(4096)
            except socket.timeout:
                break
        self.buffer = ""

    def write_internal(self, cmd: str) -> None:
        """Write the command to the port and wait for the delay time."""
        if time.time() - self.last_writetime < self.port_properties["delay"]:
            time.sleep(
                self.port_properties["delay"] - (time.time() - self.last_writetime)
            )

        encoding = self.port_properties["encoding"]
        self.port.sendall((cmd + self.write_termination).encode(encoding))

        self.last_writetime = time.time()

    def read_internal(self, digits: int = 0) -> str:
        """Read until EOL character or for a given number of digits."""
        start_t = time.time()
        eol = self.write_termination

        while True:
            if digits > 0:
                if digits > len(self.buffer):
                    # If the buffer is smaller than the requested number of digits, read more
                    missing_bytes = digits - len(self.buffer)
                    answer = self.buffer + self.read_chunk(missing_bytes)
                    self.buffer = ""
                else:
                    # If the buffer is long enough, return the answer
                    answer = self.buffer[:digits]
                    self.buffer = self.buffer[digits:]

                return answer

            if eol is not None:
                # If EOL is set, read until EOL
                if eol in self.buffer:
                    # If the EOL is in the buffer, return the answer
                    idx = self.buffer.find(eol)
                    answer = self.buffer[: idx + len(eol)]
                    self.buffer = self.buffer[idx + len(eol) :]
                    return answer.rstrip(eol)

                # If the EOL is not in the buffer, read more
                self.buffer += self.read_chunk()

            if time.time() - start_t > float(self.port_properties["timeout"]):
                msg = "Socket could not be read"
                raise TimeoutError(msg)

            time.sleep(0.01)

    def read_chunk(self, digits: int = 1024) -> str:
        """Read a chunk of data from the socket."""
        encoding = self.port_properties["encoding"]
        return self.port.recv(digits).decode(encoding)


class COMport(Port):

    port: serial.Serial

    def __init__(self, ID):

        super().__init__(ID)

        self.port = serial.Serial()

    # def initialize_port_properties_internal(self):

    # self.port_properties.update({
    #                             "baudrate": 9600,
    #                             "bytesize": 8,
    #                             "parity": 'N',
    #                             "stopbits": 1,
    #                             "xonxoff": False,
    #                             "rtscts": False,
    #                             "dsrdtr": False,
    #                             "rts": True,
    #                             "dtr": True,
    #                             "raw_write": False,
    #                             "raw_read": False,
    #                             "encoding": "latin-1",
    #                             })

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

        if not self.port.is_open:
            self.port.open()
        else:
            self.port.close()
            self.port.open()

    def close_internal(self):
        self.port.close()
        self.port_properties["open"] = False

    def clear_internal(self) -> None:
        """Clear the port."""
        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

    def write_internal(self, cmd):

        while time.perf_counter() - self.actualwritetime < self.port_properties["delay"]:
            time.sleep(0.01)

        if self.port_properties["EOLwrite"] is not None:
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

    def read_internal(self, digits=0):

        if digits == 0:
            answer, EOLfound = self.readline()

            if not self.port_properties["raw_read"]:
                try:
                    answer = answer.decode(self.port_properties["encoding"])
                except:
                    error("Unable to decode the reading from %s. Please check whether the baudrate "
                          "and the terminator are correct (Ports -> PortManager -> COM). "
                          "You can get the raw reading by setting the key 'raw_read' of "
                          "self.port_properties to True" % (self.port_properties["ID"]))
                    raise

        else:
            answer = self.port.read(digits)

            EOLfound = True

            if not self.port_properties["raw_read"]:
                try:
                    answer = answer.decode(self.port_properties["encoding"])
                except:
                    error("Unable to decode the reading from %s. Please check whether the baudrate "
                          "and the terminator are correct (Ports -> PortManager -> COM). "
                          "You can get the raw reading by setting the key 'raw_read' of "
                          "self.port_properties to True" % (self.port_properties["ID"]))
                    raise

        if answer == "" and not EOLfound and self.port_properties["Exception"] is True:
            self.close()
            raise Exception("Port '%s' with ID '%s' does not respond.\n"
                            "Check port properties, e.g. timeout, EOL,.. via Port -> PortManager -> COM" %
                            (self.port_properties["type"], self.port_properties["ID"]))

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

        if not self.port_properties["EOLread"] is None:
            EOL = self.port_properties["EOLread"].encode(self.port_properties["encoding"])
        else:
            EOL = self.port_properties["EOL"].encode(self.port_properties["encoding"])

        leneol = len(EOL)
        line = bytearray()

        eol_found = False

        while True:
            c = self.port.read(1)
            if c:
                line += c
                if line[-leneol:] == EOL:
                    eol_found = True
                    break

            else:
                break

        return bytes(line[:-leneol]), eol_found

    def get_identification(self) -> str:
        """Get details of the COM port.

        In contrast to the other get_identification functions which return instrument identifications, this
        function returns details about the COM Port (or USB-COM adapter if one is used) itself.
        Therefore this should be considered an unstable feature that might be changed in the future.

        Returns:
            The hwid of the COM port.
        """
        ports = serial.tools.list_ports.comports()

        port_info = "No info available"
        for port in ports:
            if port.device == self.port_ID:
                debug("Identification for COM ports is an experimental feature and will probably change in the future.")
                port_info = port.hwid
                break

        return port_info


class PrologixGPIBcontroller:

    def __init__(self, address):

        # basically the address could be used for COM ports but also for Ethernet
        # at the moment, only COM is supported, but Ethernet could be added later
        self.set_address(address)

        self._current_gpib_ID = None

        self.ID_port_properties = {}

        self.port = serial.Serial()
        self.port.port = self.get_address()
        self.port.baudrate = 115200  # fixed, Prologix adapter automatically recognize the baudrate (tested with v6.0)

        self.terminator_character = {
            "\r\n": 0,
            "\r": 1,
            "\n": 2,
            "": 3,
        }

    def set_address(self, address):
        self._address = str(address)

    def get_address(self):
        return self._address

    def list_resources(self):
        if self._address is not None:
            return ["GPIB::%i::Prologix@%s" % (i, self._address) for i in range(1, 31, 1)]
        else:
            return []

    def open(self, port_properties):

        ID = port_properties["ID"].split("::")[1]

        self.ID_port_properties[ID] = port_properties

        if not self.port.is_open:
            self.port.open()

        self.port.timeout = self.ID_port_properties[ID]["timeout"]
        self.port.timeout = 0.1

        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

        self.set_controller_in_charge()  # Controller in Charge CIC

        self.set_mode(1)  # 1 = controller mode

        terminator = "\r\n"

        if not self.ID_port_properties[ID]["GPIB_EOLwrite"] is None:
            terminator = self.ID_port_properties[ID]["GPIB_EOLwrite"]

        if not self.ID_port_properties[ID]["GPIB_EOLread"] is None:
            terminator = self.ID_port_properties[ID]["GPIB_EOLread"]

        if terminator in self.terminator_character:
            terminator_index = self.terminator_character[terminator]
        else:
            debug("Terminator '%s' cannot be set for Prologix adapter at %s. "
                  "Fallback to CR/LF." % (repr(terminator), str(ID)))
            terminator_index = 0  # CR/LF

        self.set_eos(terminator_index)  # see self.terminator_character for all options

        self.set_eoi(1)  # 1 = eoi at end

        self.set_auto(0)  # 0 =  no read-after-write

        self.set_read_timeout(0.05)  # read timeout in s
        # self.set_readtimeout(self.ID_port_properties[ID]["timeout"])  # read timeout in s

        # print("mode to listenonly set")

    def clear(self):
        if self.port.is_open:
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()

    def close(self):
        if self.port.is_open:
            self.port.close()

    def write(self, cmd="", ID=""):
        """ sends a non-empty command string to the prologix controller
        and changes the GPIB address if needed beforehand
        """

        if cmd != "":

            if ID == "" or cmd.startswith("++"):
                msg = (cmd + "\n").encode('latin-1')

            else:

                if ID != self._current_gpib_ID:

                    self._current_gpib_ID = str(ID)

                    # set to current GPIB address
                    # calls 'write' again, but as the command starts with '++' will not lead to an endless iteration
                    self.write("++addr %s" % self._current_gpib_ID)

                # some special characters need to be escaped before sending
                # we start to replace ESC as it will be added by other commands as well
                # and would be otherwise replaced again
                cmd.replace(chr(27), chr(27) + chr(27))  # ESC (ASCII 27)
                cmd.replace(chr(13), chr(27) + chr(13))  # CR  (ASCII 13)
                cmd.replace(chr(10), chr(27) + chr(10))  # LF  (ASCII 10)
                cmd.replace(chr(43), chr(27) + chr(43))  # ‘+’ (ASCII 43)

                msg = (cmd + "\n").encode(self.ID_port_properties[ID]["encoding"])

            # print("write:", msg)
            self.port.write(msg)

    def read(self, ID):
        """ requests an answer from the instruments and returns it """

        # needed to make sure that there is a short delay since the last write
        # time.sleep(self.ID_port_properties[ID]["delay"])

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
        self.write("++eoi %s" % str(eoi))  # 0 = no eoi at end, 1 = eoi at end

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

        # conversion from s to ms, maximum is 3000, minimum is 1
        self.write("++read_tmo_ms %i" % int(max(1, min(3000, float(readtimeout) * 1000))))

    def get_readtimeout(self):
        self.write("++read_tmo_ms")
        return float(self.port.readline().rstrip().decode()) / 1000.0  # conversion from ms to s

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


prologix_controller: dict[str, PrologixGPIBcontroller] = {}
# add_prologix_controller("COM23")

rm = open_resourcemanager()

port_types = {
    "COM": COM(),
    # "MODBUS": MODBUS(),
    "GPIB": GPIB(),
    "PXI": PXI(),
    # "ASRL": ASRL(), # Serial communication via visa runtime, just used for testing at the moment
    "USBTMC": USBTMC(),
    "TCPIP": TCPIP(),
    "SOCKET": SOCKET()
    # "VB": VirtualBench(), # no longer supported as finding ports can be done in Device Class / Driver
}
