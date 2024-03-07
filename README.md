# pysweepme

[SweepMe!](https://sweep-me.net) is a program to create measurement procedures in short time. The communication with the
instruments is handled via instrument drivers ("Device Classes"), that are python based code snippets. To use these drivers in independent python projects, you can use pysweepme to load them including the creation of interface ports. The package pysweepme outsources parts of SweepMe! as open source MIT licensed code to allow loading drivers in your own scripts.

## Installation
So far, only Windows is supported. Other systems might work as well but probably some modifications are needed.
Use the command line (cmd) to install/uninstall:

### install
    pip install pysweepme 

### install with force version
    pip install pysweepme==1.5.5.45

### uninstall
    pip uninstall pysweepme
    
### upgrade
    pip install pysweepme --upgrade

## Usage

1. Copy the drivers to a certain folder in your project folder, e.g "Devices" or to the public folder "CustomDevices".
2. Import pysweepme to your project.
3. Use 'get_driver' to load a driver.
4. See the source code of the driver to see which commands are available.  
   A general overview of the semantic functions of a driver can be found in the [SweepMe! wiki](https://wiki.sweep-me.net/wiki/Sequencer_procedure).

## Example

```python

import pysweepme

# find a certain folder that is used by SweepMe!
custom_devices_folder = pysweepme.get_path("CUSTOMDEVICES")

# folder is a path from which instrument drivers will be loaded
# port is a string, e.g. "COM1" or "GPIB0::24::INSTR"
mouse = pysweepme.get_driver("Logger-PC_Mouse", folder=".", port_string="")
mouse.connect()

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
  Developers can also find the source code of the drivers in our [instrument driver repository on github](https://github.com/SweepMe/instrument-drivers).
* SweepMe! instrument drivers have two purposes. They have semantic standard function to be used in SweepMe! but also 
wrap communication commands to easily call them with pysweepme. Not all SweepMe! instrument drivers come with wrapped
communication commands, yet.

## Changelog
You can find the list of changes on the [releases page on github](https://github.com/SweepMe/pysweepme/releases).

The changelog for pysweepme 1.5.5 is still available in the [README of the 1.5.5 branch](https://github.com/SweepMe/pysweepme/blob/v1.5.5.x/README.md#changelog).
