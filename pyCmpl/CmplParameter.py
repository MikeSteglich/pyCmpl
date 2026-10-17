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

import numbers

from .CmplException import CmplException
from .CmplTools import CmplTools
from .CmplSet import CmplSet


class CmplParameter(object):
    """ parameter of a CMPL model

        scalar:               CmplParameter("b").setValues(10)
        array (dense):        CmplParameter("c", I, J).setValues([[1, 2], [3, 4]]) or a dict with all index tuples
        array (sparse):       CmplParameter("c", I, J).setValues({(1, 2): 5}, defaultVal=0)
    """

    def __init__(self, name, *sets):
        if not isinstance(name, str):
            raise CmplException("not a valid name for a parameter: " + str(name))
        if CmplTools.stringContainsWhitespace(name):
            raise CmplException("parameter name " + name + " contains whitespaces")

        if len(sets) == 1 and isinstance(sets[0], list):
            sets = sets[0]

        self.__name = name
        self.__valueList = []
        self.__count = 1
        self.__defaultVal = None
        self._setList = []
        self.__rank = 0

        for s in sets:
            if not isinstance(s, CmplSet):
                raise CmplException(str(s) + " is not a CMPL set ")
            self._setList.append(s)
            self.__rank += s.rank

    def __countElements(self, vList):
        """ number of elements of a nested list """
        if vList and isinstance(vList[0], list):
            return sum(self.__countElements(v) for v in vList)
        return len(vList)

    def __setCount(self):
        count = 1
        for s in self._setList:
            count *= s.count()
        return count

    def setValues(self, val, defaultVal=None):
        self.__valueList = []
        self.__defaultVal = None

        if self.__rank == 0:
            if isinstance(val, (list, dict)):
                raise CmplException("incompatible data for scalar parameter <" + self.__name + "> : " + str(val))
            self.__valueList.append(val)

        elif isinstance(val, list):
            self.__count = self.__countElements(val)
            if self.__count != self.__setCount():
                raise CmplException("The dimension of the parameter <" + self.__name + "> doesn't match the dimension of the set(s).")
            self.__valueList = val

        elif isinstance(val, dict):
            if defaultVal is not None:
                # sparse array with default value
                if isinstance(defaultVal, bool) or not isinstance(defaultVal, (str, numbers.Number)):
                    raise CmplException("Wrong type of the default value of the parameter <" + self.__name + "> : "
                                        + str(defaultVal) + " : " + type(defaultVal).__name__)
                self.__defaultVal = defaultVal
            else:
                # dense array
                if len(val) != self.__setCount():
                    raise CmplException("The dimension of the parameter " + self.__name + " doesn't match the dimension of the set(s).")
                if val and isinstance(next(iter(val.values())), (list, dict)):
                    raise CmplException("Unexpected data type for parameter " + self.__name)
            self.__count = len(val)
            self.__valueList = val

        else:
            raise CmplException("incompatible data for parameter array <" + self.__name + "> : " + str(val))

    @property
    def setList(self):
        return self._setList

    @property
    def values(self):
        return self.__valueList

    @property
    def value(self):
        """ value of a scalar parameter """
        return self.__valueList[0]

    @property
    def name(self):
        return self.__name

    @property
    def rank(self):
        return self.__rank

    @property
    def len(self):
        """ number of values """
        return self.__count

    @property
    def defaultValue(self):
        return self.__defaultVal
