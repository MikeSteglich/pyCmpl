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

import html
import os
import re

from .CmplException import *

# CMPL writes the names of variables and constraints unescaped (e.g. x[a&b]) - the file is read
# line by line and tolerant instead of with an XML parser
_ELEMENT = re.compile(r'<(variable|constraint) idx="([^"]*)" name="([^"]*)" type="([^"]*)" activity="([^"]*)" '
                      r'lowerBound="([^"]*)" upperBound="([^"]*)" marginal="([^"]*)"')
_SOLUTION = re.compile(r'<solution idx="([^"]*)" status="([^"]*)" value="([^"]*)"')
_GENERAL = re.compile(r"<(\w+)>([^<]*)</\1>")


class CmplSolElement(object):
    """ variable or constraint of a solution """

    def __init__(self):
        self.__idx = 0
        self.__name = ""
        self.__type = ""
        self.__activity = 0
        self.__lowerBound = 0
        self.__upperBound = 0
        self.__marginal = 0

    @property
    def idx(self):
        return self.__idx

    def setIdx(self, idx):
        self.__idx = idx

    @property
    def name(self):
        return self.__name

    def setName(self, name):
        self.__name = name

    @property
    def type(self):
        return self.__type

    def setType(self, type):
        self.__type = type

    @property
    def activity(self):
        return self.__activity

    def setActivity(self, activity):
        self.__activity = activity

    @property
    def lowerBound(self):
        return self.__lowerBound

    def setLowerBound(self, lB):
        self.__lowerBound = lB

    @property
    def upperBound(self):
        return self.__upperBound

    def setUpperBound(self, uB):
        self.__upperBound = uB

    @property
    def marginal(self):
        return self.__marginal

    def setMarginal(self, marginal):
        self.__marginal = marginal


class CmplSolution(object):
    """ one solution: status, objective value, variables and constraints """

    def __init__(self):
        self.__idx = 0
        self.__status = ""
        self.__value = 0
        self.__variables = []
        self.__constraints = []

    @property
    def idx(self):
        return self.__idx

    def setIdx(self, idx):
        self.__idx = idx

    @property
    def status(self):
        return self.__status

    def setStatus(self, status):
        self.__status = status

    @property
    def value(self):
        return self.__value

    def setValue(self, val):
        self.__value = val

    @property
    def variables(self):
        return self.__variables

    def setVar(self, var):
        self.__variables.append(var)

    @property
    def constraints(self):
        return self.__constraints

    def setCon(self, con):
        self.__constraints.append(con)


class CmplSolutions(object):
    """ all solutions of a CMPL run (CmplSolution file or string) """

    # entries of <general>: tag -> (attribute, conversion)
    _GENERAL_ENTRIES = {
        "nrOfVariables": ("nrOfVariables", int),
        "nrOfConstraints": ("nrOfConstraints", int),
        "objectiveName": ("objectiveName", str),
        "objectiveSense": ("objectiveSense", str),
        "nrOfSolutions": ("nrOfSolutions", int),
        "solverName": ("solverName", str),
        "solverMsg": ("solverMsg", str),
        "variablesDisplayOptions": ("varDisplayOptions", str),
        "constraintsDisplayOptions": ("conDisplayOptions", str),
    }

    def __init__(self, solFile=None):
        self._nrOfVariables = 0
        self._nrOfConstraints = 0
        self._objectiveName = ""
        self._objectiveSense = ""
        self._nrOfSolutions = 0
        self._solverName = ""
        self._solverMsg = ""
        self._varDisplayOptions = ""
        self._conDisplayOptions = ""
        self.__solList = []
        self.__solutionFile = solFile
        self.__solFileContent = ""
        self.__isIntegerProgram = False

    @property
    def nrOfVariables(self):
        return self._nrOfVariables

    @property
    def nrOfConstraints(self):
        return self._nrOfConstraints

    @property
    def objectiveName(self):
        return self._objectiveName

    @property
    def objectiveSense(self):
        return self._objectiveSense

    @property
    def nrOfSolutions(self):
        return self._nrOfSolutions

    @property
    def solver(self):
        return self._solverName

    @property
    def solverMessage(self):
        return self._solverMsg

    @property
    def varDisplayOptions(self):
        return self._varDisplayOptions

    @property
    def conDisplayOptions(self):
        return self._conDisplayOptions

    # never set - kept for compatibility
    asciiSolFile = csvSolFile = cmplSolFile = ""

    @property
    def solutions(self):
        return self.__solList

    @property
    def solution(self):
        return self.__solList[0]

    @property
    def solFileContent(self):
        return self.__solFileContent

    def delSolFileContent(self):
        self.__solFileContent = ""

    @property
    def isIntegerProgram(self):
        return self.__isIntegerProgram

    def __element(self, m):
        x = CmplSolElement()
        x.setIdx(int(m.group(2)))
        name = m.group(3)
        x.setName(html.unescape(name) if "&" in name else name)
        x.setType(m.group(4))
        activity = float(m.group(5))
        if m.group(1) == "variable" and x.type in ("I", "B"):
            self.__isIntegerProgram = True
            activity = int(round(activity))
        x.setActivity(activity)
        x.setLowerBound(float(m.group(6)))
        x.setUpperBound(float(m.group(7)))
        x.setMarginal(float("NaN") if m.group(8) in ("NaN", "-") else float(m.group(8)))
        return x

    def readSolution(self, solStr=None):
        if not solStr and self.__solutionFile is None:
            raise CmplException("No solution found")

        source = "CmplSolution string"
        if self.__solutionFile is not None:
            source = "CmplSolution file " + self.__solutionFile
            if not os.path.isfile(self.__solutionFile):
                raise CmplException("No solution found")
            try:
                with open(self.__solutionFile, "r") as f:
                    solStr = f.read()
            except IOError:
                raise CmplException("IO error for " + source)

        lines = solStr.splitlines()
        if len(lines) < 2 or "<?xml version" not in lines[0]:
            raise CmplException(source + " - is not a XML file!")
        if "<CmplSolutions" not in lines[1]:
            raise CmplException("Cant't read " + source + " - wrong file type!")

        self.__solFileContent = solStr
        self.__solList = []
        inGeneral = False
        s = None

        for line in lines[2:]:
            if s is not None:
                m = _ELEMENT.search(line)
                if m:
                    (s.setVar if m.group(1) == "variable" else s.setCon)(self.__element(m))
                elif "</solution>" in line:
                    self.__solList.append(s)
                    s = None
            elif inGeneral:
                if "</general>" in line:
                    inGeneral = False
                else:
                    m = _GENERAL.search(line)
                    if m and m.group(1) in self._GENERAL_ENTRIES:
                        attr, conv = self._GENERAL_ENTRIES[m.group(1)]
                        setattr(self, "_" + attr, conv(html.unescape(m.group(2))))
            elif "<general>" in line:
                inGeneral = True
            else:
                m = _SOLUTION.search(line)
                if m:
                    s = CmplSolution()
                    s.setIdx(int(m.group(1)))
                    s.setStatus(m.group(2))
                    s.setValue(float(m.group(3)))
