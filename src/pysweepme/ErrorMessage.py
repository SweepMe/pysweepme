# The MIT License
#
# Copyright (c) 2021-2022 SweepMe! GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import os

from time import localtime
from traceback import print_exc
from typing import Callable


def try_to_print_traceback() -> None:
    """Print a traceback for the most recent python exception.

    If there is a UnicodeDecodeError while trying to print the exception, e.g.
    because a Python source file containing an error is using non UTF-8 encoding,
    the function tries to monkey patch the traceback module to skip reading lines
    from the file and still try to print as many error details as possible.
    """
    try:
        print_exc()
    except UnicodeDecodeError:
        import traceback
        # monkeypatching the linecache module
        # so UnicodeDecodeErrors while trying to read a file don't lead to an
        # uncaught Exception but only "empty" lines in the traceback
        original_updatecache: Callable[[str, dict[str, object] | None], list[str]] = traceback.linecache.updatecache
        def try_updatecache(filename: str, module_globals:dict[str, object] | None = None) -> list[str]:
            try:
                return original_updatecache(filename, module_globals)
            except Exception:  # noqa: BLE001 - error handling should also catch any unexpected errors
                print("<Failed to read file contents>")  # noqa: T201
                return []
        traceback.linecache.updatecache = try_updatecache
        print_exc()


def error(*args: object) -> None:
    """Print arguments to the debug log including an exception stacktrace.

    Args:
        *args: The arguments to print to the debug log.
    """
    year, month, day, hour, min, sec = localtime()[:6]
    print("-"*60)
    print('Time: %s.%s.%s %02d:%02d:%02d' % (day, month, year, hour, min, sec))
    if len(args) > 0:
        print('Message:', *args)
    print('Python Error:')
    try_to_print_traceback()
    print('-'*60)
    
    
def debug(*args: object, debugmode_only: bool = False) -> None:
    """Print arguments to the debug log.

    Args:
        *args: The arguments to print to the debug log.
        debugmode_only: True if the arguments shall be printed only when debug mode is on.
    """
    if "SWEEPME_DEBUGMODE" in os.environ:
        debug_mode = os.environ["SWEEPME_DEBUGMODE"] == "True"
    else:
        debug_mode = False

    if not debugmode_only or debug_mode:

        if len(args) > 0:
            
            year, month, day, hour, min, sec = localtime()[:6]
            print("-"*60)
            print('Debug: %s.%s.%s %02d:%02d:%02d\t' % (day, month, year, hour, min, sec), *args)


def debug_only(*args: object) -> None:
    """Print arguments to the debug log if debug mode is on.

    Args:
        *args: The arguments to print to the debug log.
    """
    debug(*args, debugmode_only=True)
