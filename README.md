# pysweepme

[SweepMe!](https://sweep-me.net) is a program to create measurement procedures in short time. The communication with the instruments is handled via instrument drivers ("Device Classes"), that are python based code snippets. To use these drivers in independent python projects, you can use pysweepme to load them including the creation of interface ports. The package pysweepme outsources parts of SweepMe! as open source MIT licensed code to allow loading drivers in your own scripts.

## Installation
So far, only Windows is supported. Other systems might work as well but probably some modifications are needed.
Use the command line (cmd) to install/uninstall:

### install
    pip install pysweepme 

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
# folder is a path from which device classes will be loaded
# port is a string, e.g. "COM1" or "GPIB0::24::INSTR"

print(mouse.read())

```
    
## Version number
The version number of pysweepme correlates with the version number of SweepMe!. For example, pysweepme 1.5.5.33 is exactly the version that is shipped with SweepMe! 1.5.5.33 so that drivers working with SweepMe! 1.5.5.33 should also work with pysweepme 1.5.5.33.

## Source code
It is planned to publish the source code on github. At the moment, please use the files in the folder Lib/site-packages/pysweepme of your python installation.

## Information
* Device Classes might depend on further python packages that are part of SweepMe! but are not shipped with pysweepme. In this case, these packages have to be installed using pip by solving the ImportErrors. 
* Some Device Classes only work with Windows and will not work with other systems, e.g. due to dll files or certain third-party packages.

## Changelog
* 1.5.6.x
  * FolderManager: 'addFolderToPATH' does not add subfolders of libs folder to sys.path

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