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
from xml.sax.saxutils import escape

from .CmplDefs import *
from .CmplException import *

# CMPL writes the attributes of messages not always escaped (e.g. location) - the file is read
# line by line and tolerant, html.unescape keeps invalid entities like a single "&" as they are
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_ELEM = re.compile(r"<(\w+)>([^<]*)</\1>")


def _quoteAttr(v):
    """ attribute value in double quotes, as the reader expects it """
    return '"' + escape(v, {'"': "&quot;"}) + '"'


class CmplMsg(object):
    """ one message of CMPL (error or warning) """

    def __init__(self):
        self.__type = ""
        self.__module = ""
        self.__location = ""
        self.__description = ""

    @property
    def type(self):
        return self.__type

    def setType(self, type):
        self.__type = type

    @property
    def location(self):
        return self.__location

    def setLocation(self, file):
        self.__location = file

    @property
    def module(self):
        return self.__module

    def setModule(self, mod):
        self.__module = mod

    @property
    def description(self):
        return self.__description

    def setDescription(self, msg):
        self.__description = msg


class CmplMessages(object):
    """ messages of a CMPL run (CmplMessages file or string) """

    _STATUS = {"normal": CMPL_OK, "warning": CMPL_WARNINGS, "error": CMPL_FAILED}

    def __init__(self, msgFile=None):
        self.__cmplStatus = ""
        self.__instance = ""
        self.__cmplVersion = ""
        self.__cmplMessage = ""
        self.__msgFile = msgFile
        self.__cmplMessageList = []

    @property
    def cmplStatus(self):
        return self._STATUS.get(self.__cmplStatus, CMPL_UNKNOWN)

    @property
    def cmplMessageList(self):
        return self.__cmplMessageList

    @property
    def cmplMessage(self):
        return self.__cmplMessage

    def readCmplMessages(self, msgStr=None):
        if msgStr is None and self.__msgFile is None:
            raise CmplException("Neither cmplMessageFile nor cmplMessageString defined")

        source = "CmplMessages string"
        if self.__msgFile is not None:
            source = "CmplMessages file " + self.__msgFile
            if not os.path.isfile(self.__msgFile):
                raise CmplException("CMPL failed.")
            try:
                with open(self.__msgFile, "r") as f:
                    msgStr = f.read()
            except IOError:
                raise CmplException("IO error for " + source)

        lines = msgStr.splitlines()
        if len(lines) < 2 or "<?xml version" not in lines[0]:
            raise CmplException(source + " - is not a XML file!")
        if "<CmplMessages" not in lines[1]:
            raise CmplException("Cant't read " + source + " - wrong file type!")

        self.__cmplMessageList = []
        inGeneral = inMessages = False

        for line in lines[2:]:
            if "<general>" in line:
                inGeneral = True
            elif "</general>" in line:
                inGeneral = False
            elif "<messages" in line:
                inMessages = True
            elif "</messages" in line:
                inMessages = False

            elif inGeneral:
                m = _ELEM.search(line)
                if m:
                    tag, val = m.group(1), html.unescape(m.group(2))
                    if tag == "generalStatus":
                        self.__cmplStatus = val
                    elif tag == "instanceName":
                        self.__instance = os.path.basename(val)
                    elif tag == "message":
                        self.__cmplMessage = val
                    elif tag == "cmplVersion":
                        self.__cmplVersion = val

            elif inMessages and "<message" in line:
                attrs = dict((k, html.unescape(v)) for k, v in _ATTR.findall(line))
                x = CmplMsg()
                x.setType(attrs.get("type", ""))
                x.setModule(attrs.get("module", ""))
                x.setLocation(os.path.basename(attrs.get("location", "")))
                x.setDescription(attrs.get("description", ""))
                self.__cmplMessageList.append(x)

    def writeCmplMessages(self, fileName):
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<CmplMessages version="1.1">',
                 "\t<general>",
                 "\t\t<instanceName>" + escape(self.__instance) + "</instanceName>",
                 "\t\t<generalStatus>" + escape(self.__cmplStatus) + "</generalStatus>",
                 "\t\t<message>" + escape(self.__cmplMessage) + "</message>",
                 "\t\t<cmplVersion>" + escape(self.__cmplVersion) + "</cmplVersion>",
                 "\t</general>"]
        if self.__cmplMessageList:
            lines.append('\t<messages numberOfMessages="%d">' % len(self.__cmplMessageList))
            for m in self.__cmplMessageList:
                lines.append("\t\t<message type=%s module=%s location=%s description=%s/>"
                             % tuple(_quoteAttr(v) for v in (m.type, m.module, m.location, m.description)))
            lines.append("\t</messages>")
        lines.append("</CmplMessages>")
        try:
            with open(fileName, "w") as f:
                f.write("\n".join(lines) + "\n")
        except IOError:
            raise CmplException("IO error for CmplMessage file " + fileName)
