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
from pysweepme.FolderManager import FolderManager

FoMa = FolderManager()
logbook_path = FoMa.get_file("LOGBOOK")


def get_input(msg) -> str:
    """
    This function can be used by drivers or CustomFunction scripts to ask the user for input. If used with SweepMe!,
    this function will be overwritten by SweepMe! to create a graphical user interface.
    
    Args:
        msg: String of the message that is displayed to the user

    Returns:
        str: response message

    """

    return input(str(msg))


def message_box(msg, blocking: bool = False):
    """
    This function can be used by drivers or CustomFunction scripts to show a message to the user. If used with SweepMe!,
    this function will be overwritten by SweepMe! to create a graphical user interface. Otherwise, it will be just
    printed to the console. Any application can redefine this function to redirect the message to the user.

    Args:
        msg: String of the message that is displayed to the user

    Returns:
        None

    """
    if blocking:
        # This makes sure that the use needs to accept the dialog before the measurement continues
        input(f"Message (confirm with enter): {str(msg)}")
    else:
        # The message is just shown with
        print(f"Message: {str(msg)}")


def message_info(msg):
    """
    This function can be used by drivers or CustomFunction scripts to show a message to the user. If used with SweepMe!,
    this function will be overwritten by SweepMe! to create a graphical user interface. Otherwise, it will be just
    printed to the console. Any application can redefine this function to redirect the message to the user.

    Args:
        msg: String of the message that is displayed to the user

    Returns:
        None

    """

    print("Info:", msg)


def message_balloon(msg):
    """
    This function can be used by drivers or CustomFunction scripts to show a message to the user. If used with SweepMe!,
    this function will be overwritten by SweepMe! to create a graphical user interface. Otherwise, it will be just
    printed to the console. Any application can redefine this function to redirect the message to the user.

    Args:
        msg: String of the message that is displayed to the user

    Returns:
        None

    """

    print("Balloon message:", msg)

def message_log(msg, logfilepath=None):

    if not logfilepath:
        logfilepath = logbook_path

    with open(logfilepath, "a") as logfile:
        year, month, day, hour, min, sec = time.localtime()[:6]
        logfile.write(("%02d/%02d/%04d %02d:%02d:%02d" % (day, month, year, hour, min, sec) + " - " + str(msg) + "\n"))
