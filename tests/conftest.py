import os
import sys

import pytest

# the tests use this working copy, PYCMPL_SRC selects another one (e.g. to compare with an older version)
SRC = os.environ.get("PYCMPL_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SRC)

from pyCmpl import CmplException  # noqa: E402
from pyCmpl.Cmpl import cmplBinary  # noqa: E402


LP_MODEL = """%data : I set, c[I], b
variables:
  x[I]: real[0..];
objectives:
  profit: sum{ i in I: c[i]*x[i] } -> max;
constraints:
  cap: sum{ i in I: x[i] } <= b;
"""


@pytest.fixture
def cmplAvailable():
    """ skips the test if no CMPL binary is found (CMPLHOME or bundled) """
    try:
        cmplBinary()
    except CmplException as e:
        pytest.skip(e.msg)


@pytest.fixture
def workDir(tmp_path, monkeypatch):
    """ working directory of the test - solver logs like HiGHS.log are written there """
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


@pytest.fixture
def modelFile(tmp_path):
    """ writes a model into its own directory, returns the path of the model file """
    def write(text, name="model.cmpl"):
        d = tmp_path / "model"
        d.mkdir(exist_ok=True)
        f = d / name
        f.write_text(text)
        return str(f)
    return write
