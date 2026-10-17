__version__ = "2.1.0"

from .CmplDefs import *
from .Cmpl import *
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

from . import CmplDefs as _defs

# names of "from pyCmpl import *" - without it the imports of the modules (os, sys, math.pow, ...)
# would end up in the namespace of the caller
__all__ = [n for n in vars(_defs) if n.isupper()] + [
    "Cmpl", "cmplBinary", "supportsDataStdin",
    "CmplException",
    "CmplMsg", "CmplMessages",
    "CmplTools", "stopProcessTree",
    "CmplSolElement", "CmplSolution", "CmplSolutions", "CmplSolutionReport",
    "CmplSet", "CmplParameter",
    "CmplInstance", "CmplArgs",
    "CmplXlsData", "InputSet", "InputParameter", "OutputElement",
    # compatibility: pyLogisticsLab (pCentre, pMedian, wlp) uses random without importing it
    "random",
]

import random
