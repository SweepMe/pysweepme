# The MIT License

# Copyright (c) 2021 - 2022 SweepMe! GmbH

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
import glob
import shutil
import inspect

from .ErrorMessage import error, debug


# global variable that saves a temporarily set path that could be added to PATH in case addFolderToPATH is called
# the variable was introduced with SweepMe! 1.5.4 to set a path during loading Modules as modules are not directly loaded
TemporaryFolderForPATH = None

FolderManager_initialized = False

def addFolderToPATH(path_to_add = ""):
    """ used by DeviceClasses and CustomFunctions to add their path to PATH. If no argument is given, the path of the calling file is used."""

    if path_to_add != "":
    
        if os.path.exists(path_to_add):
            main_path = path_to_add
        else:
            return False
    else:
    
        main_file = inspect.stack()[1][1]    
        main_path = os.path.dirname(os.path.realpath(main_file))
        
    # print(main_path)
    
    if not main_path in sys.path:
        sys.path = [main_path] + sys.path
        
    if not main_path in os.environ["PATH"].split(os.pathsep):
        os.environ["PATH"] = main_path + os.pathsep + os.environ["PATH"] 
    
    subfolders = [x[0] for x in os.walk(main_path) if not x[0].endswith('__pycache__')]  
    # print(subfolders)
        
    # add also library.zip to subdirectories if it exists
    for folder in subfolders:
        if os.path.exists(folder + os.sep + "library.zip"):
            subfolders.append(folder + os.sep + "library.zip")

    
    for folder in subfolders:
        if not folder in sys.path:
            sys.path = [folder] + sys.path
            
        if not folder in os.environ["PATH"].split(os.pathsep):
            os.environ["PATH"] = folder + os.pathsep + os.environ["PATH"] 
    
    return True
    
    
def addModuleFolderToPATH(path_to_add = ""):
    """ used by Modules to add their path to PATH. If no argument is given, the path of the calling Module is used."""

    if path_to_add != "":
    
        if os.path.exists(path_to_add):
            main_path = path_to_add
        else:
            return False
            
    else:
        if TemporaryFolderForPATH != None and os.path.exists(TemporaryFolderForPATH):
            main_path = TemporaryFolderForPATH
    
        else:
            main_file = inspect.stack()[1][1]    
            main_path = os.path.dirname(os.path.realpath(main_file))
        
    # print(main_path)
    
    if not main_path in sys.path:
        sys.path = [main_path] + sys.path
        
    if not main_path in os.environ["PATH"].split(os.pathsep):
        os.environ["PATH"] = main_path + os.pathsep + os.environ["PATH"] 
    
    subfolders = [x[0] for x in os.walk(main_path) if not x[0].endswith('__pycache__')]  
    # print(subfolders)
        
    # add also library.zip to subdirectories if it exists
    for folder in subfolders:
        if os.path.exists(folder + os.sep + "library.zip"):
            subfolders.append(folder + os.sep + "library.zip")

    
    for folder in subfolders:
        if not folder in sys.path:
            sys.path = [folder] + sys.path
            
        if not folder in os.environ["PATH"].split(os.pathsep):
            os.environ["PATH"] = folder + os.pathsep + os.environ["PATH"] 
    
    return True
    
    
def setTemporaryFolderForPATH(path_to_set):
    global TemporaryFolderForPATH
    TemporaryFolderForPATH = path_to_set


def unsetTemporaryFolderForPATH():
    global TemporaryFolderForPATH
    TemporaryFolderForPATH = None
    
         
def get_path(identifier):
    """ returns a path for a given identifier, such as 'CUSTOMDEVICES', 'DEVICES', ... """
    
    if not "FoMa" in globals():       
        FoMa = FolderManager(create = False)

    if identifier in FoMa.folders:
        return FoMa.get_path(identifier)
    else:
        debug("FolderManager: Folder %s unknown" % identifier)
        return False
    
def set_path(identifier, path):
    """ sets a path for a given identifier, such as 'CUSTOMDEVICES', 'DEVICES', ... """

    if not "FoMa" in globals():         
        FoMa = FolderManager(create = False)
     
    if identifier in FoMa.folders:
        FoMa.set_path(identifier, path)
    else:
        debug("FolderManager: Folder %s unknown" % identifier)
        return False
    
            
def get_file(identifier):

    if not "FoMa" in globals():           
        FoMa = FolderManager(create = False)
                
    if identifier in FoMa.files:
        return FoMa.get_file(identifier)
    else:
        debug("FolderManager: File %s unknown" % identifier)
        return False
            
def set_file(identifier, path):

    if not "FoMa" in globals():        
        FoMa = FolderManager(create = False)
            
    if identifier in FoMa.files:
        return FoMa.set_file(identifier, path)

# remains for compatibility 
def main_is_frozen():
    return is_main_frozen()
    
def is_main_frozen():
    return hasattr(sys, "frozen")
    
class FolderManager(object):

    _instance = None
    
    def __init__(self, create = False):
        
        """ create defines whether folders are created. When used with pysweepme, the default will not create folders """
    
        # this ensures that the FolderManager can be called multiple times without performing __init__ every time
        if not hasattr(self, "_is_init_complete"):
            self._is_init_complete = True
    
            # define variables for all folders   
            self.mainpath = self.get_main_dir() 
            
            mainpath_files = os.listdir(self.mainpath)
                        
            self.is_sweepme_executable = "SweepMe!.exe" in mainpath_files and self.main_is_frozen()
            self.is_portable_mode = not "installed.ini" in mainpath_files
        
            if sys.platform == "win32":
            
                from . import WinFolder # also needed for portable mode
                
                self.publicpath = os.path.join(WinFolder.get_path( WinFolder.FOLDERID.PublicDocuments ), 'SweepMe!' )
                self.roamingpath = os.path.join(WinFolder.get_path(WinFolder.FOLDERID.RoamingAppData, WinFolder.UserHandle.current ), 'SweepMe!' )
                self.localpath = os.path.join( WinFolder.get_path(WinFolder.FOLDERID.LocalAppData, WinFolder.UserHandle.current ), 'SweepMe!' )
                self.programdatapath = os.path.join( WinFolder.get_path(WinFolder.FOLDERID.ProgramData), 'SweepMe!' )
                self.programdatapath_variable = os.path.join( WinFolder.get_path(WinFolder.FOLDERID.ProgramData), 'SweepMe!' )
                
                self.tempfolder = self.localpath + os.sep + 'temp'
            
                    
                if self.is_sweepme_executable and self.is_portable_mode:  # portable mode -> we overwrite the default paths 
                    
                    self.portable_data_path = os.path.dirname(self.mainpath) + os.sep + "SweepMe! user data"
                    
                    if self.is_sweepme_executable:  # otherwise a folder is created if pysweepme is used standalone
                        if not os.path.exists(self.portable_data_path):
                            os.mkdir(self.portable_data_path)

                    self.publicpath = self.portable_data_path + os.sep + "public"
                    self.roamingpath = self.portable_data_path + os.sep + "roaming"
                    self.localpath = self.portable_data_path + os.sep + "local"
                    self.programdatapath = os.path.join(WinFolder.get_path(WinFolder.FOLDERID.ProgramData), 'SweepMe!')
                    self.programdatapath_variable = self.portable_data_path + os.sep + "programdata"
                    
                    self.tempfolder = WinFolder.get_path(WinFolder.FOLDERID.LocalAppData, WinFolder.UserHandle.current ) + os.sep + 'SweepMe!' + os.sep + 'temp'

                    
            
            elif sys.platform.startswith("linux"):
                ## not defined yet, tbd
                self.publicpath = "."
                self.roamingpath = "."
                self.localpath = "."
                self.programdatapath = "."

            
            self.libsfolder = self.mainpath + os.sep + "libs"
            
            self.resourcesfolder = self.mainpath + os.sep + 'resources'

            self.configfolder = self.programdatapath_variable + os.sep + 'configuration'
            self.serverfolder = self.configfolder + os.sep + 'server'
            self.profilesfolder = self.roamingpath + os.sep + 'profiles'
            self.SweepMeIcon = self.resourcesfolder + os.sep + 'icons' + os.sep + 'SweepMeS_icon.ico'
            self.settingfolder = self.publicpath + os.sep + 'Settings'
            self.roamingsetting = self.roamingpath + os.sep + 'Settings'
            self.examplesfolder = self.mainpath + os.sep + 'examples'
            self.measurementfolder = self.publicpath + os.sep + 'Measurement'
            self.DCfolder = self.mainpath + os.sep + 'Devices'
            self.shareddevicesfolder = self.programdatapath_variable + os.sep + 'Devices'
            self.versionsfolder = self.programdatapath_variable + os.sep + 'Versions'
            self.modulesfolder = self.mainpath + os.sep + 'Modules'
            self.sharedmodulesfolder = self.programdatapath_variable + os.sep + 'Modules'
            self.sweepscriptfolder = self.publicpath + os.sep + 'SweepScripts'
            self.extlibsfolder = self.publicpath + os.sep + 'ExternalLibraries'
            self.customfolder = self.publicpath + os.sep + 'CustomFiles'
            self.calibrationfolder = self.publicpath + os.sep + 'CalibrationFiles'
            self.customDCfolderold = self.publicpath + os.sep + 'CustomDeviceClasses'
            self.customDCfolder = self.publicpath + os.sep + 'CustomDevices'
            self.customMCfolder = self.publicpath + os.sep + 'CustomModules'
            self.DCDatafolder = self.publicpath + os.sep + 'DataDevices'
            self.MCDatafolder = self.publicpath + os.sep + 'DataModules'
            self.interfacesfolder = self.mainpath + os.sep + 'libs' + os.sep + 'interfaces'
            self.widgetsfolder = self.mainpath + os.sep + 'Widgets'
            self.customresourcesfolder = self.publicpath + os.sep + 'Resources'
            self.customcolormapsfolder = self.customresourcesfolder  + os.sep + 'colormaps'
            self.customstylesfolder = self.customresourcesfolder  + os.sep + 'styles'
            self.customiconsfolder = self.customresourcesfolder  + os.sep + 'icons'
           
            self.folders = {
                            "MAIN": self.mainpath,                  # Folder where SweepMe!.exe is
                            "TEMP": self.tempfolder,                # temporary measurement data in MAIN
                            "RESOURCES": self.resourcesfolder,      # Folder insider MAIN with icon, colormaps, etc.
                            "DATA": self.measurementfolder,         # Measurement data in PUBLIC
                            "SETTINGS": self.settingfolder,         # Settings in PUBLIC

                            "ROAMINGSETTINGS": self.roamingsetting, # Settings in ROAMING
                            "EXAMPLES": self.examplesfolder,        # Example settings in MAIN
                            "PROFILES": self.profilesfolder,        # Profile inis in ROAMING
                            
                            "PROGRAMDATA": self.programdatapath,    # ProgramData path for things that need be accessed by all user but should not be seen easily
                            
                            "DEVICES": self.DCfolder,               # Devices in MAIN
                            "MODULES": self.modulesfolder,          # Modules in MAIN
                            
                            "WIDGETS": self.widgetsfolder,          # WIDGETS in MAIN
                            "INTERFACES": self.interfacesfolder,    # INTERFACES in MAIN\libs
                            
                            "SHAREDDEVICES": self.shareddevicesfolder,  # Devices in ProgramData
                            "SHAREDMODULES": self.sharedmodulesfolder,  # Modules in ProgramData
                            "VERSIONS": self.versionsfolder,            # Versions in ProgramData
                            
                            "CONFIG": self.configfolder,             # Config folder in ProgramData
                            "SERVER": self.serverfolder,             # Server folder in ProgramData / Config folder
                                                    
                            "CUSTOMDEVICESOLD": self.customDCfolderold,# DeviceClasses in PUBLIC
                            "CUSTOMDEVICES": self.customDCfolder,   # Devices in PUBLIC
                            "CUSTOMMODULES": self.customMCfolder,   # Modules in PUBLIC
                            
                            "DATAMODULES": self.MCDatafolder,       # Folder for Module specific data in PUBLIC
                            "DATADEVICES": self.DCDatafolder,       # Folder for Device specific data in PUBLIC
                            
                            "LOCAL": self.localpath,                # Local windows user appdata
                            "ROAMING": self.roamingpath,            # Roaming windows user appdata
                            "PUBLIC": self.publicpath,              # Public documents folder for SweepMe!
                            # "SWEEPSCRIPTS": self.sweepscriptfolder, # Sweep script folder in PUBLIC
                            "CALIBRATIONS": self.calibrationfolder, # Calibration folder in PUBLIC
                            "CUSTOM": self.customfolder,            # Custom files in PUBLIC
                            "CUSTOMFILES": self.customfolder,       # Custom files in PUBLIC
                            "CUSTOMRESOURCES": self.customresourcesfolder, # Custom resources in PUBLIC
                            "CUSTOMCOLORMAPS": self.customcolormapsfolder, # Custom colormaps in PUBLIC
                            "CUSTOMSTYLES": self.customstylesfolder, # Custom styles in PUBLIC
                            "CUSTOMICONS": self.customiconsfolder, # Custom icons in PUBLIC
                            
                            
                            
                            # "SYSTEMUSER": self.systemuserpath,      # SweepMe! folder in system user folder
                            "EXTLIBS": self.extlibsfolder,          # External libraries such as dll in PUBLIC
                            }
              
            self.profileuserfile = None # because we do not know which profile will be selected
            self.systemuserfile = self.roamingpath + os.sep + 'OSuser.ini'
            self.userfile = self.mainpath + os.sep + 'user.txt'
            self.configfile = self.configfolder + os.sep + 'config.ini'
            self.texteditor = self.libsfolder + os.sep + "Pnotepad" + os.sep + "pn.exe"
            self.logbookfile = self.tempfolder + os.sep + "temp_logbook.txt"
            self.debugfile = self.publicpath + os.sep + "debug.log"
            self.debugfhfile = self.publicpath + os.sep + "debug_fh.log"
                          
            # print("FolderManager: self.files redefined")                
            self.files = {
                            "PROFILEINI": self.profileuserfile, # Configuration ini of Profile
                            "OSUSERINI": self.systemuserfile,   # System user config file in ROAMING
                            "CONFIG": self.configfile,          # Configuration folder in MAIN
                            
                            "SWEEPMEICON":self.SweepMeIcon,     # SweepMe! icon in resources 
                            "TEXTEDITOR": self.texteditor,      # Texteditor
                            "LOGBOOK": self.logbookfile,        # Logbook file in tempfolder
                            "DEBUG": self.debugfile,            # debug file in public folder
                            "DEBUGFH": self.debugfhfile,        # debug faulthandler file in public folder
                         }
                
        if create:
            self.create_folders()

        
    def __new__(class_, *args, **kwargs):
    
        # this ensures that the OptionManager can be called multiple times without creating a new instance
        if not isinstance(class_._instance, class_):
            class_._instance = object.__new__(class_)
             
        return class_._instance        


    def create_folders(self): 
        
        for folder in [self.publicpath, self.roamingpath, self.localpath, self.programdatapath_variable]:
        
            # Important: We don't want to make Progamdata folder here as this would result in a folder that can only be written
            # by the user that created it first time. 
            # we use os.path.abspath to make sure the folder format is the same
            if not os.path.abspath(folder) in os.path.abspath(self.folders["PROGRAMDATA"]):
                if not os.path.exists(folder):
                    os.mkdir(folder)
                
           
        ### add path if they do not exist
        for key in self.folders:
            
            # This folder is not used anymore and should not be used anymore
            if key == "CUSTOMDEVICESOLD":
                continue
                
            # Important: We don't want to make Progamdata folder here as this would result in a folder that can only be written
            # by the user that created it first time.    
            elif key == "PROGRAMDATA":
                continue

            if not os.path.exists(self.folders[key]):
                try:
                    os.mkdir(self.folders[key])
                except:
                    error()
                
            if not self.folders[key] in sys.path:
                sys.path.append(self.folders[key])
                
            if not self.folders[key] in os.environ["PATH"].split(os.pathsep):
                os.environ["PATH"] += os.pathsep + self.folders[key]
                
            if key == "EXTLIBS":
            
                for root, dirs, files in os.walk(self.folders[key], topdown=True):
           
                    if not root in sys.path:
                        sys.path.append(root)
                        
                    if not root in os.environ["PATH"].split(os.pathsep):
                        os.environ["PATH"] += os.pathsep + root

        

    def get_path(self, identifier):
        
        if identifier in self.folders:
            if not os.path.exists(self.folders[identifier]):
                try: 
                    os.mkdir(self.folders[identifier])
                except:
                    pass
            
            return self.folders[identifier]
            
        else:
            debug("FolderManager: Folder %s unknown" % identifier)
            return False
            
            
    def set_path(self, identifier, path):
        
        if identifier in self.folders:
            self.folders[identifier] = path
        else:
            debug("FolderManager: identifier '%s' unknown to set path" % identifier)
            
    def get_file(self, identifier):
    
        # print()
        # print("get_file")
        # print (identifier)
        # print (self.files)
        
        if identifier in self.files:
            return self.files[identifier]
        else:
            debug("FolderManager: File %s unknown" % identifier)
            return False
            
    def set_file(self, identifier, path):
                
        if identifier in self.files:
            self.files[identifier] = path
        else:
            debug("FolderManager: identifier '%s' unknown to set file" % identifier)
            
        # print()
        # print("set_file")
        # print (identifier)
        # print (self.files)
    
    
    def get_main_dir(self):
        if self.main_is_frozen():
            return os.path.dirname(sys.executable)
            
        return os.getcwd()

    def main_is_frozen(self):
        return self.is_main_frozen()
        
    def is_main_frozen(self):
        return hasattr(sys, "frozen")
        
