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


from traceback import print_exc
from time import localtime

import os, sys


def error(*args):

    year, month, day, hour, min, sec = localtime()[:6]
    print("-"*60)
    print('Time: %s.%s.%s %02d:%02d:%02d' % (day, month, year, hour, min, sec))
    if len(args) > 0:
        print('Message:', *args)
    print('Python Error:')
    print_exc()
    print('-'*60)
    
    
def debug(*args):

    if len(args) > 0:
    
        year, month, day, hour, min, sec = localtime()[:6]
        print("-"*60)
        print('Debug: %s.%s.%s %02d:%02d:%02d\t' % (day, month, year, hour, min, sec), *args)
    
    