# pysweepme

[SweepMe!](https://sweep-me.net) is a program to create measurement procedures in short time. The communication with the
instruments is handled via instrument drivers ("Device Classes"), that are python based code snippets. To use these drivers in independent python projects, you can use pysweepme to load them including the creation of interface ports. The package pysweepme outsources parts of SweepMe! as open source MIT licensed code to allow loading drivers in your own scripts.

## Installation
So far, only Windows is supported. Other systems might work as well but probably some modifications are needed.
Use the command line (cmd) to install/uninstall:

### install
    pip install pysweepme 

### install with force version
    pip install pysweepme==1.5.5.46

### uninstall
    pip uninstall pysweepme
    
### upgrade
    pip install pysweepme --upgrade

## Usage

1. copy the drivers to a certain folder in your project folder, e.g "Devices" or to the public folder "CustomDevices"
2. import pysweepme to your project
3. use 'get_device' to load a device class
4. see the source code of the device classes to see which commands are available

## Example

```python

import pysweepme

# find a certain folder that is used by SweepMe!
custom_devices_folder = pysweepme.get_path("CUSTOMDEVICES")

mouse = pysweepme.get_device("Logger-PC_Mouse", folder = ".", port = "")
# folder is a path from which instrument drivers will be loaded
# port is a string, e.g. "COM1" or "GPIB0::24::INSTR"

print(mouse.read())
```
    
## Version number
The version number of pysweepme correlates with the version number of SweepMe!. For example, pysweepme 1.5.5.x is
related to SweepMe! 1.5.5.x, but the last digit of the version number can differ.

## Source code
The source code can be found on github.

## Instrument drivers
* Instrument drivers might depend on further python packages that are part of SweepMe! but are not shipped with 
pysweepme. In this case, these packages have to be installed using pip by solving the ImportErrors. 
* Some Instrument drivers only work with Windows and will not work with other systems, e.g. due to dll files or certain 
third-party packages.
* Instrument drivers can be downloaded from https://sweep-me.net/devices or using the version manager in SweepMe!.
* SweepMe! instrument drivers have two purposes. They have semantic standard function to be used in SweepMe! but also 
wrap communication commands to easily call them with pysweepme. Not all SweepMe! instrument drivers come with wrapped
communication commands, yet.

## Changelog
* 1.5.5.46 
  * new submodule "UserInterface"
  * bugfix in get_device with handing over port string
  * GPIB, USBTMC and TCPIP ports do not use clear() during open and close 
  * Find TCPIP ports only lists ports registered in visa runtime
  * Drivers have method 'is_run_stopped'
  * FolderManager: 'addFolderToPATH' does not add subfolders of libs folder to sys.path
* 1.5.5.45 minor fixes
* 1.5.5.44 bugfix: SweepMe! user data folder is not created like in portable mode if pysweepme is used standalone
* 1.5.5.33 first release of pysweepme on pypi after release of SweepMe! 1.5.5

## License
MIT License

Copyright (c) 2021 - 2022 SweepMe! GmbH (sweep-me.net)

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

The WinFolder package has a separate license not covered in this document and
which can be found in the header of the WinFolder.py file.