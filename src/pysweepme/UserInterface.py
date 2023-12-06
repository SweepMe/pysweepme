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

import time
from typing import Callable

from .FolderManager import getFoMa


class UIHandler:
    """Manages calls to user interface functions and allows applications to register alternative functions."""

    _get_input: Callable[[str], str] | None = None
    _message_box: Callable[[str, bool], None] | None = None
    _message_info: Callable[[str], None] | None = None
    _message_balloon: Callable[[str], None] | None = None

    @classmethod
    def register_get_input(cls, get_input_function: Callable[[str], str]) -> None:
        """Register a handler for the get_input() function.

        Args:
            get_input_function: Function that shall handle calls to get_input().

        """
        cls._get_input = get_input_function

    @classmethod
    def get_input(cls, msg: str) -> str:
        """Ask the user for input.

        This function can be used by drivers or CustomFunction scripts to ask the user for input. If used with SweepMe!,
        this function will be overwritten by SweepMe! to create a graphical user interface.

        Args:
            msg: String of the message that is displayed to the user.

        Returns:
            str: response message
        """
        if callable(cls._get_input):
            return cls._get_input(msg)

        return input(str(msg))

    @classmethod
    def register_message_box(cls, message_box_function: Callable[[str, bool], None]) -> None:
        """Register a handler for the message_box() function.

        Args:
            message_box_function: Function that shall handle calls to message_box().
        """
        cls._message_box = message_box_function

    @classmethod
    def message_box(cls, msg: str, blocking: bool) -> None:
        """Show a message to the user.

        This function can be used by drivers or CustomFunction scripts to show a message to the user.
        If used with SweepMe!, this function will be overwritten by SweepMe! to create a graphical message box.
        By default, it will be just printed to the console.

        Args:
            msg: String of the message that is displayed to the user.
            blocking: True to require the user to acknowledge the message.
        """
        if callable(cls._message_box):
            cls._message_box(msg, blocking)
            return

        if blocking:
            # This makes sure that the use needs to accept the dialog before the measurement continues
            input(f"Message (confirm with enter): {msg!s}")
        else:
            # The message is just shown with a print which should work in every application that uses pysweepme
            print(f"Message: {msg!s}")  # noqa: T201

    @classmethod
    def register_message_info(cls, message_info_function: Callable[[str], None]) -> None:
        """Register a handler for the message_info() function.

        Args:
            message_info_function: Function that shall handle calls to message_info().
        """
        cls._message_info = message_info_function

    @classmethod
    def message_info(cls, msg: str) -> None:
        """Show an info to the user.

        This function can be used by drivers or CustomFunction scripts to show a message to the user.
        If used with SweepMe!, this function will be overwritten by SweepMe! to add an entry in the general tab
        of the main window. By default, it will be just printed to the console.

        Args:
            msg: String of the message that is displayed to the user.
        """
        if callable(cls._message_info):
            cls._message_info(msg)
            return

        # The message is just shown with a print which should work in every application that uses pysweepme
        print("Info:", msg)  # noqa: T201

    @classmethod
    def register_message_balloon(cls, message_balloon_function: Callable[[str], None]) -> None:
        """Register a handler for the message_balloon() function.

        Args:
            message_balloon_function: Function that shall handle calls to message_balloon().
        """
        cls._message_balloon = message_balloon_function

    @classmethod
    def message_balloon(cls, msg: str) -> None:
        """Show a message balloon to the user.

        This function can be used by drivers or CustomFunction scripts to show a message to the user.
        If used with SweepMe!, this function will be overwritten by SweepMe! to create a message balloon in the
        system tray. By default, it will be just printed to the console.

        Args:
            msg: String of the message that is displayed to the user.
        """
        if callable(cls._message_balloon):
            cls._message_balloon(msg)
            return

        # The message is just shown with a print which should work in every application that uses pysweepme
        print("Balloon message:", msg)  # noqa: T201


get_input = UIHandler.get_input
message_box = UIHandler.message_box
message_info = UIHandler.message_info
message_balloon = UIHandler.message_balloon


def message_log(msg, logfilepath=None):
    if not logfilepath:
        logfilepath = getFoMa().get_file("LOGBOOK")

    with open(logfilepath, "a") as logfile:
        year, month, day, hour, min, sec = time.localtime()[:6]
        logfile.write("%02d/%02d/%04d %02d:%02d:%02d" % (day, month, year, hour, min, sec) + " - " + str(msg) + "\n")
