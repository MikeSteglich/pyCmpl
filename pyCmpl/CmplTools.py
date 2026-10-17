#***********************************************************************
 #  This code is part of pyCMPL 
 #
 #  Copyright (C) 
 #  Mike Steglich - Technical University of Applied Sciences
 #  Wildau, Germany 
 #
 #  pyCMPL is a project of the Technical University of 
 #  Applied Sciences Wildau and the Institute for Operations Research 
 #  and Business Management at the Martin Luther University 
 #  Halle-Wittenberg.
 #  Please visit the project homepage <www.coliop.org>
 # 
 #  pyCMPL is free software; you can redistribute it and/or modify it 
 #  under the terms of the GNU Lesser General Public License as published by 
 #  the Free Software Foundation; either version 3 of the License, or 
 #  (at your option) any later version.
 # 
 #  pyCMPL is distributed in the hope that it will be useful, but WITHOUT
 #  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 #  or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public 
 #  License for more details.
 #  
 #  You should have received a copy of the GNU Lesser General Public License
 #  along with this program; if not, see <http://www.gnu.org/licenses/>.
 #
 #**********************************************************************

import re
import math
import os
import signal
import subprocess
import time


class CmplTools(object):

    @staticmethod
    def stringContainsWhitespace(string):
        regex = re.compile('[\t\n\x0b\x0c\r ]+')
        if regex.search(string):
            return True
        else:
            return False

    @staticmethod
    def strIsNumber(str):
        r = re.compile(r'[^\-\+0-9.]+')
        if  r.search(str):
            return False
        else:
            return True

    @staticmethod
    def strIsValidIndex(str):
        r = re.compile(r'[^0-9a-zA-Z\-_.]+')
        if  r.search(str):
            return False
        else:
            return True

    @staticmethod
    def strContains(str0, str1):
        return str1 in str0


def stopProcessTree(process, timeout=2):
    """ stops a process started with subprocess.Popen and all its descendants (cmpl -> solver)

        Like stopProcessTree in the cmpl start script: the descendants are collected before the
        process is stopped - otherwise they get the parent 1 and keep running (e.g. HiGHS after a cancel).
        First SIGTERM, after timeout seconds SIGKILL. On Windows taskkill /T stops the whole tree.
    """
    if process is None or process.poll() is not None:
        return

    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        pids = _descendants(process.pid) + [process.pid]
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for pid in pids:
                try:
                    os.kill(pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass
            endTime = time.time() + timeout
            while time.time() < endTime and _isRunning(process, pids):
                time.sleep(0.05)
            if not _isRunning(process, pids):
                break

    try:
        process.wait(timeout)
    except subprocess.TimeoutExpired:
        process.kill()

def _descendants(pid):
    """ all descendants of a process, children first """
    try:
        out = subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return []
    pids = []
    for child in (int(p) for p in out.split()):
        pids += _descendants(child) + [child]
    return pids

def _isRunning(process, pids):
    if process.poll() is None:
        return True
    for pid in pids:
        if pid == process.pid:
            continue
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            pass
    return False
