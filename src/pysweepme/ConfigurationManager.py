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
from pysweepme.ErrorMessage import error
from configparser import ConfigParser


class Config(ConfigParser):

    def __init__(self, file_name = None):
    
        super(__class__, self).__init__()
        
        self.optionxform = str 
    
        self.file_name = file_name

    def setFileName(file_name):
        self.file_name = file_name

    def isConfigFile(self):
    
        try:
            if os.path.isfile(self.file_name):
                return True
            else:                        
                return False
        except:
            error()
            
        return False
            
    def readConfigFile(self):
    
        try:
            if self.isConfigFile():
            
                if os.path.exists(self.file_name):
                    with open(self.file_name , 'r', encoding='utf-8') as cf:
                        self.read_file(cf)
                return True
            else:
                self.read_string(self.file_name)
                return True
        except:
            error()
            
        return False

    def makeConfigFile(self):
        try:
            if not self.isConfigFile():
                if not os.path.exists(os.path.dirname(self.file_name)):
                    os.mkdir(os.path.dirname(self.file_name))
                with open(self.file_name , 'w', encoding='utf-8') as cf:
                    self.write(cf)
                    
                return True
        except:
            error()

        return False
            
    def setConfigSection(self, section):
    
        try:
            if self.readConfigFile():
                with open(self.file_name , 'w', encoding='utf-8') as cf:
                    if not self.has_section(section):
                        self.add_section(section)
                    self.write(cf)
            return True
                   
        except:
            error()
            
        return False
                 
    def setConfigOption(self, section, option, value):
          
        try:
            self.setConfigSection(section)
            
            self.set(section, option, value)
            
            with open(self.file_name , 'w', encoding='utf-8') as cf:
                self.write(cf)
            return True
        except:
            error()
            
        return False
        
    def removeConfigOption(self, section, option):
        try:
            if self.readConfigFile():
                if self.has_section(section):
                   if self.has_option(section, option):
                        self.remove_option(section, option)
                        
                        with open(self.file_name , 'w', encoding='utf-8') as cf:
                            self.write(cf)
                            
                        return True
            return False
        except:
            error()

    def getConfigSections(self):
        if self.readConfigFile():
            return self.sections()
        else:
            return []
            
    def getConfigOption(self, section, option):
        vals = {}
        if self.readConfigFile():
            if section in self:
                if option.lower() in self[section]:
                    return self[section][option.lower()]     
                elif option in self[section]:
                    return self[section][option]                    
        return False
            
    def getConfigOptions(self, section):
        vals = {}
        if self.readConfigFile():
            if section in self:
                for key in self[section]:
                    vals[key] = self[section][key]
        return vals
        
    def getConfig(self):
        config = {section : self.getConfigOptions(section) for section in self.getConfigSections()}
        return config