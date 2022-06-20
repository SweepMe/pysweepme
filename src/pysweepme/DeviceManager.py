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
import time
import os

from .ErrorMessage import error, debug
from .Ports import get_port
    
def get_device(name, folder = ".", port = ""):
    """returns a Device object as defined by the Device Class to be loaded"""
    
    # if no folder is given, the device class is loaded from the project folder

    if folder == "":
        folder = "."
    if name.startswith(os.sep):
        name = name[1:]
    if name.endswith(os.sep):
        name = name[:-1]

    try:
        Module = imp.load_source(name, folder + os.sep + name + os.sep + "main.py") # Loads .py file
    except:
        raise Exception("Cannot load Device Class '%s' from folder %s. Please change folder or copy Device Class to your project." % (name, folder))
 
    device = Module.Device()
    device._import_path = Module.__file__
    
    if port != "":
        if device.port_manager:
            port = get_port(port, device.port_properties)
            device.port = port

        device.set_parameters({"Port":port})
        
    else:
        device.set_parameters()

    return device
    

def get_driver(name, folder = ".", port = ""):
    """same function as get_device: returns a Device object as defined by the Device Class to be loaded"""

    # function is introduced because of a possible later renaming of DeviceClasses to Drivers

    return self.get_device(name, folder, port)
    
            