# ***********************************************************************
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
# **********************************************************************

__version__ = "3.0.0"

import os
import threading
import subprocess
import sys
import xmlrpc.client
import time
import tempfile
import io
import locale
import numbers
import pickle
import traceback
import shutil
import collections

import pathlib
import platform

from .CmplDefs import *
from .CmplException import *
from .CmplMsg import *
from .CmplTools import *
from .CmplSolution import *
from .CmplSet import *
from .CmplParameter import *
from .CmplInstance import *
from .CmplXlsData import *
from .CmplArgs import *
from .CmplSolutionReport import *


def cmplBinary():
    """ path of the CMPL binary

        1. $CMPLHOME/bin/cmpl - the layout of a CMPL installation (bin/cmpl, bin/*.opt, Thirdparty/...)
        2. binMac, binWin or binLinux in this package - platform wheels (tools/build_wheel.py)
           and apps that bundle CMPL this way

        The cmpl start script in the PATH is not used - it runs the precompiler and cmplStarter
        and does not accept the arguments of pyCmpl.
    """
    exe = 'cmpl.exe' if sys.platform == 'win32' else 'cmpl'

    cmplHome = os.environ.get('CMPLHOME')
    if cmplHome:
        binary = os.path.join(cmplHome, 'bin', exe)
    else:
        binDir = {'Windows': 'binWin', 'Linux': 'binLinux', 'Darwin': 'binMac'}.get(platform.system(), 'bin')
        binary = os.path.join(os.path.dirname(os.path.abspath(__file__)), binDir, exe)

    if not os.path.isfile(binary):
        raise CmplException("Can't find Cmpl binary: " + binary +
                            " - set CMPLHOME to the CMPL installation (CMPLHOME/bin/" + exe + ")")
    return binary

def _cmplIndex(v, symbol):
    """ index of a set or parameter in the cmpl data: integer or string

        CMPL accepts no real numbers as indices - integral floats (e.g. from Excel) become integers
    """
    if isinstance(v, str):
        return '"' + v + '"'
    if isinstance(v, numbers.Integral) and not isinstance(v, bool):
        return str(int(v))
    if isinstance(v, numbers.Real) and not isinstance(v, bool):
        if not float(v).is_integer():
            raise CmplException("set or parameter <" + symbol + ">: " + str(v) + " is not a valid index (only integers and strings)")
        return str(int(v))
    return '"' + str(v) + '"'

def _cmplValue(v):
    """ value of a parameter in the cmpl data """
    if isinstance(v, str):
        return '"' + v + '"'
    if isinstance(v, numbers.Integral) and not isinstance(v, bool):
        return str(int(v))
    if isinstance(v, numbers.Real) and not isinstance(v, bool):
        return str(float(v))
    return str(v)

def _cmplValueList(values):
    """ values of a (nested) list, one line per innermost list """
    if values and isinstance(values[0], list):
        return "".join(_cmplValueList(v) for v in values)
    return " ".join(_cmplValue(v) for v in values) + " \n"
def _indexKey(indices):
    """ key of an element of m.x[...] from the indices in its name, e.g. "1,a" -> (1, "a")

        CMPL writes the indices without quotes: numbers become int or float, other indices str
    """
    keys = tuple(_indexValue(i) for i in indices.split(","))
    return keys[0] if len(keys) == 1 else keys

def _indexValue(s):
    try:
        return int(s)
    except ValueError:
        pass
    if CmplTools.strIsNumber(s):
        try:
            return float(s)
        except ValueError:
            pass
    return s

_dataStdinSupport = {}

def supportsDataStdin(cmplBin):
    """ whether the CMPL binary can read the data via stdin (option -data-stdin)

        older CMPL versions read the data only from a file
    """
    if cmplBin not in _dataStdinSupport:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0
        try:
            res = subprocess.run([cmplBin, "-h"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, creationflags=flags, timeout=30)
            _dataStdinSupport[cmplBin] = b"-data-stdin" in res.stdout
        except (OSError, subprocess.SubprocessError):
            _dataStdinSupport[cmplBin] = False
    return _dataStdinSupport[cmplBin]


class Cmpl(threading.Thread):
#class Cmpl:

    # Constructor and destructor

    def __init__(self, model, cmplArgs=None):

        threading.Thread.__init__(self)

        self.__compatibility = COMPATIBILITY

        self.__runMode = PYCMPL

        if type(model) != str:
            raise CmplException(str(model) + " is not a valid file name for a Cmpl file")

        self.__cmplFile = model
        self.__tmpDir = None

        if not os.path.exists(model):
            raise CmplException("CMPL file " + model + " does not exist."  )

        self.__baseName = os.path.splitext(self.__cmplFile)[0]

        self.__cmplDataStr = io.StringIO()

        self.__setList = []
        self.__parameterList = []
        self.__optionsList = {}

        self.__xlsData = None
        self.__isXlsData = False
        self.__xlsDataFile = ""

        self.__status = None
        self.__solutions = None
        self.__solutionString = ""

        self.__remoteMode = False
        self.__remoteStatus = CMPL_UNKNOWN
        self.__remoteStatusMessage = ""

        self.__jobId = ""
        self.__instStr = ""
        self.__cmplInstance = None

        self.__solver = "highs"

        self.__cmplServer = None
        self.__cmplUrl = ""
        self.__cmplGridScheduler = None
        self.__cmplGridSchedulerUrl = ""
        self.__serverMode = SERVER_UNKNOWN

        self.__cmplServerRunning = False

        self.__maxCmplServerTries = 10
        self.__maxCmplServerQueuingTime = 5 * 60  # in seconds

        self.__cmplDataFile = None
        self.__cmplMsgFile = None
        self.__cmplSolFile = None

        self.__refreshTime = 0.1
        self.__printOutput = False

        self.__isCleaned = False
        self.__debug = False

        self.__cmplBinHandler = None
        self.__cmplBinName=""

        self.__cmplBinName = cmplBinary()

        if cmplArgs:
            self.__cmplArgs = cmplArgs
            self.__runMode = self.__cmplArgs.runMode
            # the solver of the cmpl command line (-solver) - otherwise the default is sent to a CmplServer
            self.__solver = self.__cmplArgs.solver
        else:
            self.__preCompAlias = "cmpl__"+next(tempfile._get_candidate_names())+"__"
            self.__cmplArgs = CmplArgs(self.__preCompAlias+".optcmpl")
            self.__cmplArgs.setRunMode(PYCMPL)

        self.__solReport = None

        self.__outputLeadString = os.path.basename(os.path.splitext(self.__cmplFile)[0]) + "> "
        self.__flushCounter=0

    def __del__(self):
        if self.__runMode in (PYCMPL, CMPL_LOCAL, CMPL_REMOTE_SOLVE, CMPL_REMOTE_RETRIEVE):
            try:
                self.__cleanUp()
                self.__cmplDataStr.close()
            except Exception:
                pass

    def __reduce__(self):
        return (self.__class__, (self.__cmplFile,))

    # public methods

    def dump(self, name=None):
        try:
            if name is not None:
                _dumpFileName = name
            else:
                _dumpFileName = tempfile.gettempdir() + os.sep + os.path.basename(self.__cmplFile) + ".dump"

            _dumpFile = open(_dumpFileName, 'wb')

            pickle.dump(self.__compatibility, _dumpFile)
            pickle.dump(self.__baseName, _dumpFile)
            pickle.dump(self.__setList, _dumpFile)
            pickle.dump(self.__parameterList, _dumpFile)
            pickle.dump(self.__optionsList, _dumpFile)
            pickle.dump(self.__status, _dumpFile)
            pickle.dump(self.__isXlsData, _dumpFile)
            pickle.dump(self.__xlsDataFile, _dumpFile)
            pickle.dump(self.__solutions, _dumpFile)
            pickle.dump(self.__solutionString, _dumpFile)
            pickle.dump(self.__remoteMode, _dumpFile)
            pickle.dump(self.__remoteStatus, _dumpFile)
            pickle.dump(self.__remoteStatusMessage, _dumpFile)
            pickle.dump(self.__jobId, _dumpFile)
            pickle.dump(self.__instStr, _dumpFile)
            pickle.dump(self.__solver, _dumpFile)
            pickle.dump(self.__cmplUrl, _dumpFile)
            pickle.dump(self.__cmplGridSchedulerUrl, _dumpFile)
            pickle.dump(self.__serverMode, _dumpFile)
            pickle.dump(self.__runMode, _dumpFile)
            pickle.dump(self.__cmplServerRunning, _dumpFile)
            pickle.dump(self.__maxCmplServerTries, _dumpFile)
            pickle.dump(self.__maxCmplServerQueuingTime, _dumpFile)
            pickle.dump(self.__cmplDataFile, _dumpFile)
            pickle.dump(self.__cmplMsgFile, _dumpFile)
            pickle.dump(self.__cmplSolFile, _dumpFile)
            pickle.dump(self.__cmplBinHandler, _dumpFile)
            pickle.dump(self.__refreshTime, _dumpFile)
            pickle.dump(self.__printOutput, _dumpFile)
            pickle.dump(self.__isCleaned, _dumpFile)
            pickle.dump(self.__debug, _dumpFile)
            pickle.dump(self.__cmplFile, _dumpFile)
            pickle.dump(self.__outputLeadString, _dumpFile)

            _dumpFile.close()
        except Exception:
            traceback.print_exc(file=sys.stdout)
            raise CmplException("Internal error, cannot write dump: " + str(sys.exc_info()[1]))

    def load(self, name=None):
        try:
            if name is not None:
                _dumpFileName = name
            else:
                _dumpFileName = tempfile.gettempdir() + os.sep + os.path.basename(self.__cmplFile) + ".dump"

            _dumpFile = open(_dumpFileName, 'rb')

            self.__compatibility = pickle.load(_dumpFile)
            self.__baseName = pickle.load(_dumpFile)
            self.__setList = pickle.load(_dumpFile)
            self.__parameterList = pickle.load(_dumpFile)
            self.__optionsList = pickle.load(_dumpFile)
            self.__status = pickle.load(_dumpFile)
            self.__isXlsData = pickle.load(_dumpFile)
            self.__xlsDataFile = pickle.load(_dumpFile)
            self.__solutions = pickle.load(_dumpFile)
            self.__solutionString = pickle.load(_dumpFile)
            self.__remoteMode = pickle.load(_dumpFile)
            self.__remoteStatus = pickle.load(_dumpFile)
            self.__remoteStatusMessage = pickle.load(_dumpFile)
            self.__jobId = pickle.load(_dumpFile)
            self.__instStr = pickle.load(_dumpFile)
            self.__solver = pickle.load(_dumpFile)
            self.__cmplUrl = pickle.load(_dumpFile)
            self.__cmplGridSchedulerUrl = pickle.load(_dumpFile)
            self.__serverMode = pickle.load(_dumpFile)

            if self.__serverMode == STANDALONE_SERVER:
                if self.__cmplUrl:
                    self.__cmplServer = xmlrpc.client.ServerProxy(self.__cmplUrl)
            if self.__serverMode == CMPL_GRID:
                if self.__cmplUrl:
                    self.__cmplServer = xmlrpc.client.ServerProxy(self.__cmplUrl, allow_none=False)
                if self.__cmplGridSchedulerUrl:
                    self.__cmplGridScheduler = xmlrpc.client.ServerProxy(self.__cmplGridSchedulerUrl)

            self.__runMode = pickle.load(_dumpFile)
            self.__cmplServerRunning = pickle.load(_dumpFile)
            self.__maxCmplServerTries = pickle.load(_dumpFile)
            self.__maxCmplServerQueuingTime = pickle.load(_dumpFile)
            self.__cmplDataFile = pickle.load(_dumpFile)
            self.__cmplMsgFile = pickle.load(_dumpFile)
            self.__cmplSolFile = pickle.load(_dumpFile)
            self.__cmplBinHandler = pickle.load(_dumpFile)
            self.__refreshTime = pickle.load(_dumpFile)
            self.__printOutput = pickle.load(_dumpFile)
            self.__isCleaned = pickle.load(_dumpFile)
            self.__debug = pickle.load(_dumpFile)
            self.__cmplFile = pickle.load(_dumpFile)
            self.__outputLeadString = pickle.load(_dumpFile)

            _dumpFile.close()

            os.remove(_dumpFileName)
        except Exception:
            raise CmplException("No CmplServer object exists. Please send your problem to a CmplServer before other actions.")

    @property
    def modelName(self):
        return self.__cmplFile

    @property
    def problem(self):
        return self.__baseName

    @property
    def refreshTime(self):
        return self.__refreshTime

    @property
    def cmplMessages(self):
        return self.__status.cmplMessageList if self.__status else []

    def __solutionInfo(self, attr, msg="No Solution found so far"):
        if self.__solutions is None:
            raise CmplException(msg)
        return getattr(self.__solutions, attr)

    @property
    def solutionPool(self):
        if self.__solutions is None or self.__solutions.nrOfSolutions == 0:
            raise CmplException("No Solution found so far")
        return self.__solutions.solutions

    @property
    def solution(self):
        if self.__solutions is None or self.__solutions.nrOfSolutions == 0:
            raise CmplException("No Solution found so far")
        return self.__solutions.solution

    @property
    def nrOfVariables(self):
        return self.__solutionInfo("nrOfVariables", "The model isn't generated yet.")

    @property
    def nrOfConstraints(self):
        return self.__solutionInfo("nrOfConstraints", "The model isn't generated yet.")

    @property
    def objectiveName(self):
        return self.__solutionInfo("objectiveName")

    @property
    def objectiveSense(self):
        return self.__solutionInfo("objectiveSense")

    @property
    def nrOfSolutions(self):
        return self.__solutionInfo("nrOfSolutions")

    @property
    def solver(self):
        return self.__solutionInfo("solver", "Since the model isn't solved the solver is not known.")

    @property
    def solverMessage(self):
        return self.__solutionInfo("solverMessage", "Since the model isn't solved the solver message is not known.")

    @property
    def varDisplayOptions(self):
        return self.__solutionInfo("varDisplayOptions", "Since the model isn't solved this option isn't known.")

    @property
    def conDisplayOptions(self):
        return self.__solutionInfo("conDisplayOptions", "Since the model isn't solved this option isn't known.")

    @property
    def cmplStatus(self):
        return self.__status.cmplStatus if self.__status else CMPL_UNKNOWN

    @property
    def cmplStatusText(self):
        if self.__remoteMode and self.__remoteStatus != CMPL_UNKNOWN:
            return CMPL_STATUS_TXT[self.__remoteStatus]
        return CMPL_STATUS_TXT[self.cmplStatus]

    @property
    def solverStatus(self):
        if self.__solutions is None or self.__solutions.nrOfSolutions == 0:
            return SOLVER_FAILED
        return SOLVER_OK

    @property
    def solverStatusText(self):
        return "SOLVER_OK" if self.solverStatus == SOLVER_OK else "SOLVER_FAILED"

    @property
    def jobId(self):
        return self.__jobId

    @property
    def isDebug(self):
        return self.__debug

    def setDataFile(self, dataFile):
        self.__cmplDataFile=dataFile

    def setXlsDataFile(self, xlsDataFile):
        self.__xlsData = CmplXlsData(xlsDataFile, self.__cmplArgs)
        self.__xlsDataFile=xlsDataFile
        self.__isXlsData=True

        if self.__xlsData:
            tmpSets,tmpPars = self.__xlsData.readXlsData()
            if tmpSets:
                self.setSets(tmpSets)
            if tmpPars:
                self.setParameters(tmpPars)

    def setRunMode(self, mode):
        self.__runMode = mode

    def setOutput(self, ok=False, lStr=None):
        self.__printOutput = ok
        if lStr is not None:
            self.__outputLeadString = lStr

    def setRefreshTime(self, rTime):
        self.__refreshTime = rTime

    def setSet(self, set):
        if not isinstance(set, CmplSet):
            raise CmplException(str(set) + " is not a CMPL set ")
        if len(set.valueList) == 0:
            raise CmplException("set " + set.name + " contains no elements ")
        self.__setList.append(set)
        self.__setModelAttr(set.name, set)

    def setSets(self, *set):
        for s in set:
            if type(s)==list:
                for e in s:
                    self.setSet(e)
            else:
                self.setSet(s)

    def setParameter(self, param):
        if not isinstance(param, CmplParameter):
            raise CmplException("Cmpl.setParameter: " + str(param) + " is not a CMPL parameter ")
        if len(param.values) == 0:
            raise CmplException("parameter " + param.name + " contains no elements ")
        self.__parameterList.append(param)
        self.__setModelAttr(param.name, param)

    def setParameters(self, *params):
        for p in params:
            if type(p)==list:
                for e in p:
                    self.setParameter(e)
            else:
                self.setParameter(p)

    def setOption(self, option):
        if type(option) != str:
            raise CmplException(str(option) + " is not a valid CMPL option ")
        else:
            if self.__cmplServerRunning:
                print("Option <"+option+"> is ignored, because problem has been connected with a CMPLServer before.")
            # a new position - len() could be the position of an existing option after delOption
            pos = max(self.__optionsList, default=-1) + 1
            self.__optionsList[pos] = option
        return pos

    def setOptionsList(self, optionList):
        if type(optionList) != dict:
            raise CmplException("Wrong option list ")
        else:
            if self.__cmplServerRunning:
                print("Options are ignored, because problem has been connected with a CMPLServer before.")
            self.__optionsList = optionList

    def delOption(self, pos):
        if pos not in self.__optionsList:
            raise CmplException(str(pos) + " is not a valid CMPL option ")
        else:
            del self.__optionsList[pos]

    def delOptions(self):
        self.__optionsList = {}

    def setMaxServerQueuingTime(self, qTime):
        self.__maxCmplServerQueuingTime = qTime

    @property
    def maxServerQueuingTime(self):
        return self.__maxCmplServerQueuingTime

    def setMaxServerTries(self, tries):
        self.__maxCmplServerTries = tries

    @property
    def maxServerTries(self):
        return self.__maxCmplServerTries

    def debug(self, mode=True):
        self.__debug = mode

    def getVarByName(self, name, solNr=0):
        if solNr < 0 or solNr > self.__solutions.nrOfSolutions - 1:
            raise CmplException("Solution with index " + str(solNr) + " doesn't exist.")
        s = self.__solByNr(solNr)
        return self.__getElementByName(name, s.variables)

    def getConByName(self, name, solNr=0):
        if solNr < 0 or solNr > self.__solutions.nrOfSolutions - 1:
            raise CmplException("Solution with index " + str(solNr) + " doesn't exist.")
        s = self.__solByNr(solNr)
        return self.__getElementByName(name, s.constraints)

    def varByName(self, solNr=0):
        if self.__solutions.nrOfSolutions >0:
            if solNr < 0 or solNr > self.__solutions.nrOfSolutions - 1:
                raise CmplException("Solution with index " + str(solNr) + " doesn't exist.")
            s = self.__solByNr(solNr)
            self.__elementByName(s.variables)

    def conByName(self, solNr=0):
        if self.__solutions.nrOfSolutions >0:
            if solNr < 0 or solNr > self.__solutions.nrOfSolutions - 1:
                raise CmplException("Solution with index " + str(solNr) + " doesn't exist.")
            s = self.__solByNr(solNr)
            self.__elementByName(s.constraints)

    def solve(self):
        self.__isCleaned=False

        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplServer")

            self.__status = CmplMessages()
            self.__solutions = CmplSolutions()

            tries = 0
            while True: # loop is intended for CMPLGrid
                self.__isCleaned = False
                try:
                    if self.__remoteStatus == CMPLSERVER_CLEANED:
                        self.connect(self.__cmplUrl)

                    if self.__serverMode == CMPL_GRID and self.__remoteStatus == CMPLSERVER_ERROR:
                        self.connect(self.__cmplUrl)

                    if self.__remoteStatus == CMPLGRID_SCHEDULER_BUSY:
                        startTime = time.time()
                        while self.__remoteStatus != CMPLGRID_SCHEDULER_OK:
                            time.sleep(self.__refreshTime)
                            self.__knockScheduler()

                            if (time.time() - startTime) >= self.__maxCmplServerQueuingTime:
                                self.__cleanUp()
                                raise CmplException("maximum CmplServer queuing time is exceeded.")

                    self.send()

                    if self.__debug:
                        instFile = self.__baseName + ".cinst"
                        try:
                            f = open(instFile, 'w')
                            f.write(self.__instStr)
                            f.close()
                        except IOError as e:
                            raise CmplException("IO error for file " + instFile + ": " + e.strerror)

                    if self.__remoteStatus == CMPLSERVER_BUSY:
                        startTime = time.time()

                    while self.__remoteStatus != PROBLEM_FINISHED:
                        self.knock()

                        time.sleep(self.__refreshTime)
                        if self.__remoteStatus == CMPLSERVER_BUSY and (
                                time.time() - startTime) >= self.__maxCmplServerQueuingTime:
                            raise CmplException("maximum CmplServer queuing time is exceeded.")

                    self.retrieve()
                    break

                except CmplException as e:
                    if self.__serverMode == CMPL_GRID and self.__remoteStatus == CMPLSERVER_ERROR and self.__cmplGridSchedulerUrl != "":
                        try:
                            self.__cmplServerExecute("cmplServerFailed")
                            self.__handleOutput(
                                "CmplServer failed <" + self.__cmplUrl + ">: Problem will be newly connected to CmplGridScheduler and commited to another CmplServer.")

                            self.__cmplUrl = self.__cmplGridSchedulerUrl
                            self.__cmplGridSchedulerUrl = ""
                            self.__cmplGridScheduler = None
                            self.__cmplServer = None
                        except  CmplException as e:
                            raise CmplException("CmplGridScheduler failed: " + e.msg)

                        tries += 1
                        if tries == self.__maxCmplServerTries:
                            raise CmplException(e.msg)

                        continue
                    else:
                        if self.__cmplArgs.msgFile:
                            self.saveCmplMessageFile(self.__cmplArgs.msgFile)
                        raise CmplException(e.msg)

        else:
            if self.__cmplArgs.runMode==PYCMPL:
                # temporary files in an own directory - the model directory stays untouched
                # and parallel runs of the same model don't interfere
                self.__tmpDir = tempfile.mkdtemp(prefix="cmpl_")
                tmpPrefix = os.path.join(self.__tmpDir, os.path.basename(self.__baseName))
                self.__cmplDataFile = tmpPrefix + ".cdat"
            else:
                tmpPrefix = self.__baseName
                if not self.__cmplDataFile:
                    self.__cmplDataFile = tmpPrefix + ".cdat"

            self.__cmplMsgFile = tmpPrefix + ".cmsg"
            self.__cmplSolFile = tmpPrefix + ".csol"

            self.__cmplDataElements()

            self.__status = CmplMessages(self.__cmplMsgFile)
            self.__solutions = CmplSolutions(self.__cmplSolFile)

            if self.__cmplArgs.runMode==PYCMPL:
                cmdList = [self.__cmplBinName, self.__cmplFile, "-solution", self.__cmplSolFile]
            else:
                cmdList = [self.__cmplBinName,  "-solution"]

            for opt in self.__optionsList:
                tmpOpt = self.__optionsList[opt].split()
                for o in tmpOpt:
                    cmdList.append(o)

            cmdList.append("-cmsg")
            cmdList.append(self.__cmplMsgFile)

            dataArgs, cmplData = self.__cmplDataArgs()
            cmdList += dataArgs

            self.__runCmpl(cmdList, cmplData)

            self.__solutions.readSolution()
            self.__solReport=CmplSolutionReport(self.__solutions)

            self.conByName()
            self.varByName()

            self.__writeSolToXls()

        self.__cleanUp()

    def run(self):
        try:
            self.solve()
        except CmplException as e:
            sys.stderr.write(e.msg + "\n")

    def connect(self, cmplUrl):
        if self.__remoteStatus != CMPL_UNKNOWN and self.__remoteStatus != CMPLSERVER_CLEANED and self.__serverMode != CMPL_GRID:
            raise CmplException("Problem is still connected with CMPLServer: at " + cmplUrl + " with jobId " + self.__jobId)

        self.__runCmplPreComp()
        self.setOption("-mark-used solutionAscii solutionCsv")

        tries = 0
        while True:
            self.__remoteMode = True
            self.__remoteStatus = CMPL_UNKNOWN
            self.__serverMode = STANDALONE_SERVER
            self.__cmplServer = None
            self.__cmplUrl = cmplUrl
            self.__cmplGridSchedulerUrl = ""
            self.__cmplGridScheduler = None

            try:
                self.__cmplServer = xmlrpc.client.ServerProxy(cmplUrl)
                ret = self.__cmplServer.getJobId(os.path.basename(escape(self.__cmplFile)), self.__solver,self.__compatibility)
                self.__remoteStatus = ret[0]

                if self.__remoteStatus == CMPLSERVER_OK or self.__remoteStatus == CMPLGRID_SCHEDULER_OK or self.__remoteStatus == CMPLGRID_SCHEDULER_BUSY:
                    self.__jobId = ret[2]

                if self.__remoteStatus == CMPLSERVER_OK or self.__remoteStatus == CMPLSERVER_ERROR:
                    self.__serverMode = STANDALONE_SERVER

                elif self.__remoteStatus == CMPLGRID_SCHEDULER_OK or self.__remoteStatus == CMPLGRID_SCHEDULER_ERROR or self.__remoteStatus == CMPLGRID_SCHEDULER_BUSY:
                    self.__serverMode = CMPL_GRID
                    self.__handleOutput("Connected with CmplGridScheduler at " + self.__cmplUrl + " with jobId " + self.__jobId)

                    if self.__remoteStatus == CMPLGRID_SCHEDULER_OK:
                        self.__connectServerViaScheduler(ret[1])
                        self.__serverMode = CMPL_GRID
            except Exception:
                tries += 1

                ret = str(sys.exc_info()[1])
                self.__cmplServer = None

                if self.__remoteStatus != CMPL_UNKNOWN:
                    if tries == self.__maxCmplServerTries:
                        raise CmplException("CmplServer error: " + ret)
                    else:
                        continue
                else:
                    raise CmplException("CmplServer error: " + ret)

            break

        if self.__remoteStatus == CMPLSERVER_ERROR or self.__remoteStatus == CMPLGRID_SCHEDULER_ERROR:
            self.__cleanUp()
            raise CmplException(ret[1])

        self.__cmplServerRunning = True

        if self.__serverMode != CMPL_GRID:
            self.__handleOutput("Connected with CmplServer at " + self.__cmplUrl + " with jobId " + self.__jobId + \
                                " >> maxServerTries <" + str(self.__maxCmplServerTries) + "> maxQueuingTime <" + \
                                str(self.__maxCmplServerQueuingTime) + ">")

        if self.__remoteStatus == CMPLGRID_SCHEDULER_BUSY:
            self.__handleOutput(ret[1])

    def disconnect(self):
        self.__cleanUp()

        self.__remoteStatus = CMPL_UNKNOWN
        self.__cmplServer = None
        self.__cmplUrl = ""
        self.__remoteMode = False
        self.__serverMode = STANDALONE_SERVER

    def send(self):
        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplServer")

            if self.__remoteStatus == CMPLSERVER_CLEANED:
                self.connect(self.__cmplUrl)

            self.knock()
            if self.__remoteStatus == PROBLEM_RUNNING:
                raise CmplException("Don't send the problem again before the CmplServer finished the previous one")

            self.__cmplDataElements()

            self.__status = CmplMessages()
            self.__solutions = CmplSolutions()
            self.__cmplInstance = CmplInstance()
            self.__instStr = self.__cmplInstance.cmplInstanceStr(self.__cmplFile, self.__cmplArgs, list(self.__optionsList.values()),
                                                                 self.__cmplDataStr.getvalue(), self.__jobId)

            ret = self.__cmplServerExecute("send")

            self.__remoteStatus = ret[0]
            if self.__remoteStatus == CMPLSERVER_ERROR:
                self.__cleanUp()
                raise CmplException(ret[1])

            if self.__runMode==PYCMPL:
                os.remove(self.__preCompAlias+".optcmpl")
                os.remove(self.__preCompAlias+".precmpl")
                os.remove(self.__preCompAlias+".extdata")

        else:
            raise CmplException("Cmpl::send can only be used in remote mode")

    def knock(self):
        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplServer")

            if self.__remoteStatus == CMPLSERVER_CLEANED:
                raise CmplException("Model was received and cleaned on the CmplServer")

            if self.__remoteStatus != PROBLEM_CANCELED:

                ret = self.__cmplServerExecute("knock")
                self.__remoteStatus = ret[0]

                self.__handleOutput(ret[2])

                if self.__remoteStatus == CMPLSERVER_ERROR or self.__remoteStatus == CMPL_FAILED:
                    self.__cleanUp()
                    raise CmplException(ret[1])

        else:
            raise CmplException("Cmpl::knock can only be used in remote mode")

    def retrieve(self):
        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplServer")

            if self.__remoteStatus == CMPLSERVER_CLEANED:
                raise CmplException("Model was received and cleaned from the CmplServer")

            self.knock()

            if self.__remoteStatus == PROBLEM_FINISHED:
                ret = self.__cmplServerExecute("getCmplMessages")

                self.__remoteStatus = ret[0]
                if self.__remoteStatus == CMPLSERVER_ERROR:
                    self.__cleanUp()
                    raise CmplException(ret[1])
                else:
                    self.__status.readCmplMessages(ret[2])

                if self.__status.cmplStatus == CMPL_FAILED:
                    self.__cleanUp()
                    raise CmplException("Cmpl finished with errors", self.__status.cmplMessageList)

                ret = self.__cmplServerExecute("getSolutions")

                self.__remoteStatus = ret[0]
                if self.__remoteStatus == CMPLSERVER_ERROR:
                    self.__cleanUp()
                    raise CmplException(ret[1])
                else:
                    self.__solutionString = ret[2]
                    self.__solutions.readSolution(self.__solutionString)

                self.__solReport=CmplSolutionReport(self.__solutions)

                self.conByName()
                self.varByName()
                self.__writeSolToXls()

                self.__cleanUp()

            else:
                if self.__remoteStatus == PROBLEM_CANCELED:
                    raise CmplException("Model has been canceled by user, cannot retrieve the solution")
                else:
                    raise CmplException("Model is still running, cannot retrieve the solution")
        else:
            raise CmplException("Cmpl::retrieve can only be used in remote mode")

    def cancel(self):
        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplServer")

            if self.__remoteStatus == CMPLSERVER_CLEANED:
                raise CmplException("Model has been received and cleaned from the CmplServer")

            if self.__remoteStatus != PROBLEM_CANCELED:

                ret = self.__cmplServerExecute("cancel")
                self.__remoteStatus = ret[0]
                if self.__remoteStatus == CMPLSERVER_ERROR:
                    self.__cleanUp()
                    raise CmplException(ret[1])

                ret = self.__cmplServerExecute("removeProblem")
                if ret[0] == CMPLSERVER_ERROR:
                    self.__remoteStatus = CMPLSERVER_ERROR
                    self.__cleanUp()
                    raise CmplException(ret[1])
                self.__remoteStatus = CMPLSERVER_CLEANED
        else:
            self.__cleanUp()

    def saveSolution(self, solFileName=None):
        if self.__solutions.nrOfSolutions > 0:

            if solFileName == None:
                solFile = self.__baseName + ".csol"
            else:
                solFile = solFileName

            self.__solReport.saveSolution(self.__baseName + ".cmpl", solFile)
            self.__handleOutput("CMPL: Solution has been written to cmplSolution file: " + solFile)

    def saveSolutionAscii(self, solFileName=None):
        if self.__solutions.nrOfSolutions > 0:
            if solFileName == None:
                solFile = self.__baseName + ".sol"
            else:
                solFile = solFileName
            self.solutionReport(solFile)
            self.__handleOutput("CMPL: Solution has been written to ASCII file: " + solFile)
        else:
            raise CmplException("No Solution found so far")

    def saveSolutionCsv(self, solFileName=None):
        if self.__solutions.nrOfSolutions > 0:
            if solFileName == None:
                solFile = self.__baseName + ".csv"
            else:
                solFile = solFileName
            self.__solReport.saveSolutionCsv( os.path.basename(self.__cmplFile), solFile )
            self.__handleOutput("CMPL: Solution has been written to CSV file: " + solFile)
        else:
            raise CmplException("No Solution found so far")

    def solutionReport(self, fileName=None):
        self.__solReport.solutionReport(os.path.basename(self.__cmplFile), fileName)

    def saveCmplMessageFile(self, msgFileName=None):
        if msgFileName == None or msgFileName == "":
            fName = self.__baseName + ".cmsg"
        else:
            fName = msgFileName
        self.__handleOutput("CMPL: Writing CmplMessages to file: " + fName)
        self.__status.writeCmplMessages(fName)

    # private methods								*

    def __runCmplPreComp(self):
        if self.__cmplArgs.runMode==PYCMPL:

            cmdList = [self.__cmplBinName, self.__cmplFile, "-o-opt", self.__preCompAlias+".optcmpl", "-o-pre", self.__preCompAlias+".precmpl" , "-o-extern", self.__preCompAlias+".extdata", "-modules" , "precomp", "-no-warn-unused"]

            for opt in self.__optionsList:
                tmpOpt = self.__optionsList[opt].split()
                for o in tmpOpt:
                    cmdList.append(o)

            cmdList.append("-cmsg")
            if not self.__cmplMsgFile:
                self.__cmplMsgFile = os.path.splitext(self.__cmplFile)[0]+".cmsg"
            cmdList.append(self.__cmplMsgFile)
            self.__status = CmplMessages(self.__cmplMsgFile)

            self.__runCmpl(cmdList)
            self.__cmplArgs.parseOptFile()

            self.__solver=self.__cmplArgs.solver

    def __runCmpl(self, cmdList, inputData=""):
        # no console window on Windows (GUI apps like LogisticsLab or the CMPL IDE)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0
        # without output stdout is not read - DEVNULL, otherwise cmpl could block on a full pipe
        stdout = subprocess.PIPE if self.__printOutput else subprocess.DEVNULL
        stdin = subprocess.PIPE if inputData else None
        # same encoding as formerly used for writing the cmplData file
        inputBytes = inputData.encode(locale.getpreferredencoding(False)) if inputData else None
        self.__cmplBinHandler = subprocess.Popen(cmdList, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, creationflags=flags)

        try:
            if self.__printOutput:
                if inputBytes:
                    # cmpl reads stdin completely while parsing its command line options,
                    # before it writes more than its start message - so no deadlock with stdout
                    try:
                        self.__cmplBinHandler.stdin.write(inputBytes)
                        self.__cmplBinHandler.stdin.close()
                    except BrokenPipeError:
                        # cmpl has finished early, its errors are read from stderr
                        pass
                while True:
                    line = self.__cmplBinHandler.stdout.readline()
                    if line:
                        self.__handleOutput(line)
                    else:
                        break
                errors = self.__cmplBinHandler.stderr.read()
            else:
                _, errors = self.__cmplBinHandler.communicate(input=inputBytes)

            returnCode = self.__cmplBinHandler.wait()
            if returnCode != 0:
                if not errors.strip():
                    errors = "cmpl terminated with exit code " + str(returnCode)
                raise CmplException(errors)

        except BaseException:
            # e.g. KeyboardInterrupt - cmpl and the solver must not keep running
            stopProcessTree(self.__cmplBinHandler)
            raise

        self.__status.readCmplMessages()

        if self.__status.cmplStatus == CMPL_FAILED:
            raise CmplException("Cmpl finished with errors", self.__status.cmplMessageList)

    def __cleanUp(self):
        if not self.__isCleaned:
            if self.__debug:
                input("Hit Enter to exit")

            if self.__remoteMode:
                if not (self.__serverMode == CMPL_GRID and self.__cmplGridSchedulerUrl == ""):
                    if (self.__remoteStatus != PROBLEM_FINISHED and self.__remoteStatus != CMPLSERVER_ERROR and self.__remoteStatus != PROBLEM_CANCELED):
                        if self.__cmplServerRunning:
                            self.__cmplServerExecute("cancel")

                    if (self.__remoteStatus != CMPLSERVER_CLEANED and self.__remoteStatus != CMPLSERVER_ERROR):
                        self.__cmplServerExecute("removeProblem")
                        self.__remoteStatus = CMPLSERVER_CLEANED

                if self.__serverMode == CMPL_GRID:
                    if self.__remoteStatus == CMPLGRID_SCHEDULER_BUSY or self.__remoteStatus == CMPLGRID_SCHEDULER_UNKNOWN:
                        self.__cmplServerExecute("disconnectFromScheduler")

            elif self.__cmplBinHandler != None:
                # cmpl and the solver it has started (e.g. HiGHS)
                stopProcessTree(self.__cmplBinHandler)

            if self.__cmplDataFile != None and not self.__remoteMode and (self.__cmplArgs.runMode==PYCMPL or self.__isXlsData):
                if os.path.isfile(self.__cmplDataFile):
                    os.remove(self.__cmplDataFile)

            if self.__cmplMsgFile and not self.__cmplArgs.msgFile:
                if os.path.isfile(self.__cmplMsgFile):
                    os.remove(self.__cmplMsgFile)

            if self.__cmplSolFile and not self.__cmplArgs.solFile:
                if os.path.isfile(self.__cmplSolFile):
                    os.remove(self.__cmplSolFile)

            if self.__tmpDir:
                shutil.rmtree(self.__tmpDir, ignore_errors=True)
                self.__tmpDir = None

            self.__isCleaned = True

    def __cmplDataArgs(self):
        """ command line arguments that hand the data over to cmpl

            returns the arguments and the data to write to stdin of cmpl
        """
        cmplData = self.__cmplDataStr.getvalue()
        if not cmplData:
            return [], ""

        if self.__debug:
            self.__writeCmplDataFile()

        if supportsDataStdin(self.__cmplBinName):
            # cmpl treats the data from stdin as content of the data file
            if self.__cmplArgs.runMode == PYCMPL:
                dataName = "{}.cdat"            # default data file of the model
            else:
                dataName = self.__cmplDataFile  # alias of the CmplXlsData file
            return ["-data-stdin", dataName], cmplData

        # older cmpl without -data-stdin: the data is read from a file
        if not self.__debug:
            self.__writeCmplDataFile()
        if self.__cmplArgs.runMode == PYCMPL:
            # cmpl derives {} from the model file name up to its last '.'
            dotPos = self.__cmplFile.rfind('.')
            cmplFileBase = self.__cmplFile[:dotPos] if dotPos >= 0 else self.__cmplFile
            return ["-filealias", cmplFileBase + ".cdat=" + self.__cmplDataFile], ""
        return [], ""

    def __writeCmplDataFile(self):
        try:
            f = open(self.__cmplDataFile, 'w')
            f.write(self.__cmplDataStr.getvalue())
            f.close()
        except IOError as e:
            raise CmplException("IO error for cmplDateFile " + self.__cmplDataFile + ": " + e.strerror)

    def __cmplDataElements(self):
        """ generates the cmpl data of the sets and parameters (anew for every run) """
        out = []
        setNames = set(s.name for s in self.__setList)

        for s in self.__setList:
            out.append("%" + s.name + (" set[" + str(s.rank) + "] < " if s.rank > 1 else " set < "))
            if s.type == 0:
                out.append("\n")
                for e in s.valueList:
                    out.append(_cmplIndex(e, s.name) + " \n")
            elif s.type == 1:
                out.append("\n")
                for t in s.valueList:
                    out.append(" ".join(_cmplIndex(e, s.name) for e in t) + " \n")
            elif s.type == 2:
                out.append("%d..%d " % tuple(s.valueList))
            elif s.type == 3:
                out.append("%d(%d)%d " % tuple(s.valueList))
            out.append(">\n")

        for p in self.__parameterList:
            out.append("%" + p.name)

            if p.rank == 0:
                out.append(" < " + _cmplValue(p.values[0]) + " >\n")
                continue

            for s in p.setList:
                if s.name not in setNames:
                    raise CmplException("The set " + s.name + " used for the parameter " + p.name + " doesn't exist.")
            out.append("[" + ",".join(s.name for s in p.setList) + "] ")

            if isinstance(p.values, list):
                out.append(" <\n")
                for e in p.values:
                    out.append(_cmplValueList(e) if isinstance(e, list) else _cmplValue(e) + "\n")
            else:
                if p.defaultValue is not None:
                    out.append(" = " + _cmplValue(p.defaultValue) + " ")
                out.append(" indices <\n")
                for key, val in p.values.items():
                    keys = key if isinstance(key, tuple) else (key,)
                    out.append(" ".join(_cmplIndex(k, p.name) for k in keys) + " " + _cmplValue(val) + "\n")
            out.append(">\n")

        self.__cmplDataStr = io.StringIO("".join(out))

    def __solByNr(self, solNr):
        if self.__solutions.nrOfSolutions > 0:
            if 0 <= solNr < self.__solutions.nrOfSolutions:
                return self.__solutions.solutions[solNr]
            else:
                raise CmplException("Solution with number: " + str(solNr) + " doesn't exist.")
        else:
            raise CmplException("No Solution found so far")

    def __getElementByName(self, name, solObj):
        if self.__solutions.nrOfSolutions > 0:
            solElements = []
            solElement = None
            isArray = False
            isFound = False

            for e in solObj:
                if e.name.startswith(name):
                    if e.name.find("[") != -1:
                        if e.name.split('[')[0] == name:
                            isArray = True
                            solElements.append(e)
                            isFound = True
                    else:
                        if e.name == name:
                            isArray = False
                            solElement = e
                            isFound = True

            if not isFound:
                raise CmplException(name + " does not exist.")
            if isArray:
                return solElements
            else:
                return solElement
        else:
            raise CmplException("No Solution found so far")

    def __elementByName(self, solObj):
        """ makes the variables or constraints accessible as attributes: m.x[1], m.y[(1, "a")], m.z """
        arrays = {}
        for e in solObj:
            pos = e.name.find("[")
            if pos == -1:
                self.__setModelAttr(e.name, e)
            else:
                name = e.name[:pos]
                if name not in arrays:
                    arrays[name] = collections.OrderedDict()
                arrays[name][_indexKey(e.name[pos + 1:-1])] = e
        for name, elements in arrays.items():
            self.__setModelAttr(name, elements)

    def __setModelAttr(self, name, value):
        # a set, parameter, variable or constraint must not replace a method or property of Cmpl,
        # e.g. a variable "send" - it is still available with getVarByName
        if not hasattr(Cmpl, name):
            setattr(self, name, value)

    def __handleOutput(self, oStr):
        if type(oStr)==bytes:
            oStr=oStr.decode("utf-8")
        if oStr:
            if self.__printOutput:
                self.__flushCounter+=1
                if self.__outputLeadString :
                    print(self.__outputLeadString  +oStr.strip())
                else:
                    print(oStr.strip())
                if self.__flushCounter>10:
                    sys.stdout.flush()
                    self.__flushCounter=0

    def __connectServerViaScheduler(self, cmplUrl):
        self.__cmplGridSchedulerUrl = self.__cmplUrl
        self.__cmplUrl = cmplUrl
        self.__cmplGridScheduler = self.__cmplServer
        self.__serverMode = CMPL_GRID

        try:
            self.__cmplServer = xmlrpc.client.ServerProxy(self.__cmplUrl, allow_none=False)
            self.__handleOutput("Connected with CmplServer at " + self.__cmplUrl + " with jobId " + self.__jobId + \
                                " >> maxServerTries <" + str(self.__maxCmplServerTries) + "> maxQueuingTime <" + str(
                self.__maxCmplServerQueuingTime) + ">")

        except Exception:
            self.__remoteStatus = CMPLSERVER_ERROR
            raise CmplException(str(sys.exc_info()[1]))

    def __knockScheduler(self):
        if self.__remoteMode:
            if not self.__cmplServerRunning:
                raise CmplException("Model is not connected to a CmplScheduler")

            if self.__remoteStatus != PROBLEM_CANCELED:

                ret = self.__cmplServerExecute("knock")

                self.__remoteStatus = ret[0]

                if self.__remoteStatus == CMPLGRID_SCHEDULER_ERROR:
                    self.__cleanUp()
                    raise CmplException(ret[1])
                elif self.__remoteStatus == CMPLGRID_SCHEDULER_OK:
                    self.__connectServerViaScheduler(ret[1])
        else:
            raise CmplException("Cmpl::knock can only be used in remote mode")

    def __cmplServerExecute(self, method=""):
        ret = []
        tries = 0
        while True:
            try:
                if method == "cancel":
                    ret = self.__cmplServer.cancel(self.__jobId)
                elif method == "removeProblem":
                    ret = self.__cmplServer.removeProblem(self.__jobId)
                elif method == "send":
                    ret = self.__cmplServer.send(self.__instStr)
                elif method == "knock":
                    ret = self.__cmplServer.knock(self.__jobId)
                elif method == "getCmplMessages":
                    ret = self.__cmplServer.getCmplMessages(self.__jobId)
                elif method == "getSolutions":
                    ret = self.__cmplServer.getSolutions(self.__jobId)
                elif method == "cmplServerFailed":
                    ret = self.__cmplGridScheduler.cmplServerFailed(self.__cmplUrl)
                elif method == "disconnectFromScheduler":
                    ret = self.__cmplServer.disconnectProblem(self.__jobId)
            except Exception:
                tries += 1
                if tries == self.__maxCmplServerTries:
                    self.__remoteStatus = CMPLSERVER_ERROR
                    self.__cleanUp()
                    raise CmplException("CmplServer error : " + str(sys.exc_info()[1]))
                time.sleep(self.__refreshTime)
                continue
            break
        return ret

    def __writeSolToXls(self):
        if self.__isXlsData and self.__solutions.nrOfSolutions > 0:
            if not self.__xlsData:
                self.__xlsData=CmplXlsData(self.__xlsDataFile,  self.__cmplArgs)
            if not self.__cmplArgs.isSilent:
                print("CMPL: Writing solution to Excel file <"+self.__xlsData.xlsFile+">")

            for idx,o in enumerate(self.__xlsData.solutionElements):
                if o.outType!="info":
                    s = getattr(self, o.name)
                else:
                    s=None
                self.__xlsData.writeSolElemToXls(s,idx, self.__solutions)
