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


class CmplSet(object):
    """ set of a CMPL model

        type 0: enumeration set           setValues([1, 2, "a"])
        type 1: tuple set (rank > 1)      setValues([(1, "a"), (2, "b")])
        type 2: algorithmic set n..m      setValues(n, m)
        type 3: algorithmic set n(k)m     setValues(n, k, m)
    """

    def __init__(self, name, rank=1):
        if not isinstance(name, str):
            raise CmplException("not a valid name for set: " + str(name))
        if CmplTools.stringContainsWhitespace(name):
            raise CmplException("set name " + name + " contains whitespaces")

        self.__name = name
        self.__rank = rank
        self.__type = 0
        self.__valueList = []

    def setValues(self, val1, val2=None, val3=None):
        self.__valueList = []

        if val2 is None and val3 is None:
            if not isinstance(val1, list):
                raise CmplException("unexpected values for set " + self.__name + " : " + str(val1) + " is not a list")
            if val1 and isinstance(val1[0], (list, tuple)):
                if len(val1[0]) != self.__rank:
                    raise CmplException("Rank and number of indexing entries for set " + self.__name + " : " + str(val1[0]) + " don't match.")
                self.__type = 1
            else:
                if self.__rank > 1:
                    raise CmplException("incorrect definition of a tuple set " + self.__name)
                self.__type = 0
            self.__valueList = val1

        elif val3 is None:
            if not (_isInt(val1) and _isInt(val2)):
                raise CmplException("unexpected values for set " + self.__name + " : " + str(val1) + "/" + str(val2) + " is not an valid integer combination")
            if val2 < val1:
                raise CmplException("unexpected values for set " + self.__name + " : end value " + str(val2) + " is less then start value " + str(val1))
            self.__type = 2
            self.__rank = 1
            self.__valueList = [int(val1), int(val2)]

        else:
            if not (_isInt(val1) and _isInt(val2) and _isInt(val3)):
                raise CmplException("unexpected values for set " + self.__name + " : " + str(val1) + "/" + str(val2) + "/" + str(val3) + " is not an valid integer combination")
            if val2 > 0 and val3 <= val1:
                raise CmplException("unexpected values for set " + self.__name + " : end value " + str(val3) + " is less than or equal to start value " + str(val1) + " and the increment is positive " + str(val2))
            if val2 < 0 and val1 <= val3:
                raise CmplException("unexpected values for set " + self.__name + " : end value " + str(val3) + " is greater than or equal to start value " + str(val1) + " and the increment is negative " + str(val2))
            if val2 == 0:
                raise CmplException("unexpected values for the set " + self.__name + " :  increment/decrement equals zero  ")
            self.__type = 3
            self.__rank = 1
            self.__valueList = [int(val1), int(val2), int(val3)]

    def __range(self):
        if self.__type == 2:
            return range(self.__valueList[0], self.__valueList[1] + 1)
        start, step, end = self.__valueList
        return range(start, end + (1 if step > 0 else -1), step)

    def count(self):
        """ number of elements """
        return self.len

    @property
    def valueList(self):
        """ values as given to setValues """
        return self.__valueList

    @property
    def values(self):
        """ elements of the set, tuples for tuple sets """
        if self.__type == 0:
            return self.__valueList
        if self.__type == 1:
            return [tuple(c) for c in self.__valueList]
        return list(self.__range())

    @property
    def name(self):
        return self.__name

    @property
    def type(self):
        return self.__type

    @property
    def rank(self):
        return self.__rank

    @property
    def len(self):
        """ number of elements """
        if self.__type in (0, 1):
            return len(self.__valueList)
        return len(self.__range())


def _isInt(v):
    return isinstance(v, numbers.Integral) and not isinstance(v, bool)
