""" solving with the CMPL binary (CMPLHOME or bundled), the tests are skipped without it """

import os
import xml.etree.ElementTree as ET

import pytest

from pyCmpl import (Cmpl, CmplSet, CmplParameter, CmplException,
                    SOLVER_OK, SOLVER_FAILED, CMPL_OK, CMPL_FAILED, CMPL_UNKNOWN)
from pyCmpl.Cmpl import supportsDataStdin, cmplBinary

from conftest import LP_MODEL

pytestmark = pytest.mark.usefixtures("cmplAvailable", "workDir")


def lpModel(modelFile, I=(1, 2, 3), c=(3, 1, 2), b=10, model=LP_MODEL, name="model.cmpl"):
    m = Cmpl(modelFile(model, name))
    s = CmplSet("I")
    s.setValues(list(I))
    pc = CmplParameter("c", s)
    pc.setValues(list(c))
    pb = CmplParameter("b")
    pb.setValues(b)
    m.setSets(s)
    m.setParameters(pc, pb)
    return m


def test_lp_solution(modelFile):
    m = lpModel(modelFile)
    m.solve()

    assert m.solverStatus == SOLVER_OK
    assert m.cmplStatus == CMPL_OK
    assert m.solution.status == "OPTIMAL"
    assert m.solution.value == 30
    assert m.nrOfSolutions == 1 and len(m.solutionPool) == 1
    assert m.nrOfVariables == 3 and m.nrOfConstraints == 1
    assert m.objectiveName == "profit" and m.objectiveSense == "max"

    assert [v.activity for v in m.solution.variables] == [10, 0, 0]
    assert m.x[1].activity == 10 and m.x[3].activity == 0
    assert m.cap.activity == 10 and m.cap.upperBound == 10
    assert [v.name for v in m.getVarByName("x")] == ["x[1]", "x[2]", "x[3]"]
    assert m.getConByName("cap").activity == 10


def test_status_before_solve(modelFile):
    m = lpModel(modelFile)
    assert m.cmplStatus == CMPL_UNKNOWN
    assert m.solverStatus == SOLVER_FAILED


def test_repeated_solve(modelFile):
    m = lpModel(modelFile)
    m.solve()
    m.solve()
    assert m.solution.value == 30


def test_parameters_as_dict(modelFile):
    m = Cmpl(modelFile(LP_MODEL))
    s = CmplSet("I")
    s.setValues([1, 2, 3])
    dense = CmplParameter("c", s)
    dense.setValues({1: 3, 2: 1, 3: 2})
    b = CmplParameter("b")
    b.setValues(10)
    m.setSets(s)
    m.setParameters(dense, b)
    m.solve()
    assert m.solution.value == 30

    sparse = CmplParameter("c", s)
    sparse.setValues({2: 5}, 0)
    m2 = Cmpl(m.modelName)
    m2.setSets(s)
    m2.setParameters(sparse, b)
    m2.solve()
    assert m2.solution.value == 50 and m2.x[2].activity == 10


INDEX_MODEL = """%data : S set, A set[2]
variables:
  x[S]: real[0..1];
  y[A]: integer[0..2];
  z: binary;
objectives:
  sum{ i in S: x[i] } + sum{ [i,j] in A: y[i,j] } + z -> max;
constraints:
  cap: sum{ i in S: x[i] } <= 1;
  { i in S: k[i]: x[i] <= 1; }
"""


def test_index_keys(modelFile):
    """ the keys of m.x[...] must stay as they are - pyLogisticsLab uses m.x[(i,j)].activity """
    m = Cmpl(modelFile(INDEX_MODEL))
    S = CmplSet("S")
    S.setValues(["a", "bc", 3, -4])
    A = CmplSet("A", 2)
    A.setValues([(1, "p"), (2, "q")])
    m.setSets(S, A)
    m.solve()

    assert set(m.x.keys()) == {"a", "bc", 3, -4}
    assert set(m.y.keys()) == {(1, "p"), (2, "q")}
    assert m.y[(1, "p")].activity == 2 and isinstance(m.y[(1, "p")].activity, int)
    assert m.z.activity == 1
    assert m.k["a"].type == "L"
    assert m.solution.value == 6


def test_numpy_values(modelFile):
    """ numpy integers and floats, e.g. from pandas - they must stay numbers, the model uses x[1] """
    np = pytest.importorskip("numpy")
    model = LP_MODEL + "  first: x[1] <= 4;\n"
    m = lpModel(modelFile, I=list(np.array([1, 2, 3])), c=list(np.array([3.0, 1.0, 2.0])), b=np.int64(10), model=model)
    m.solve()
    assert m.solution.value == 24
    assert set(m.x.keys()) == {1, 2, 3}


def test_float_set_elements(modelFile):
    m = lpModel(modelFile, I=(1.0, 2.0, 3.0))   # e.g. from Excel
    m.solve()
    assert m.solution.value == 30

    with pytest.raises(CmplException):
        lpModel(modelFile, I=(1.5, 2.5, 3.5)).solve()


def test_options(modelFile):
    m = lpModel(modelFile)
    a = m.setOption("-a")
    b = m.setOption("-b")
    m.delOption(a)
    c = m.setOption("-c")
    assert c != b

    m.delOptions()
    m.setOption("-solver highs")
    m.solve()
    assert m.solver.upper() == "HIGHS"


def test_name_of_model_element_does_not_replace_method(modelFile):
    m = Cmpl(modelFile("variables: send: real[0..5];\nobjectives: send -> max;\nconstraints: c: send <= 5;\n"))
    m.solve()
    assert callable(m.send)
    assert m.getVarByName("send").activity == 5


def test_save_solution_files(modelFile, tmp_path):
    m = lpModel(modelFile)
    m.solve()

    for f in ("a.csol", "b.csol"):
        m.saveSolution(str(tmp_path / f))
        root = ET.parse(str(tmp_path / f)).getroot()
        assert root.find("general/instanceName").text.endswith("model.cmpl")
        assert len(root.findall(".//variable")) == 3

    m.saveSolutionAscii(str(tmp_path / "s.sol"))
    assert "Objective value" in (tmp_path / "s.sol").read_text()

    m.saveSolutionCsv()
    base = os.path.splitext(m.modelName)[0]
    assert os.path.isfile(base + ".csv")
    assert "Objective value;30" in open(base + ".csv").read()


def test_model_error(modelFile, tmp_path):
    m = lpModel(modelFile, model=LP_MODEL.replace("<= b;", "<= b + y;"), name="bad.cmpl")
    with pytest.raises(CmplException) as e:
        m.solve()
    assert "symbol 'y' is not defined" in e.value.msg
    assert m.cmplStatus == CMPL_FAILED

    msg = m.cmplMessages[0]
    assert msg.location.startswith("bad.cmpl:")
    assert "symbol 'y' is not defined" in msg.description

    m.saveCmplMessageFile(str(tmp_path / "bad.cmsg"))
    root = ET.parse(str(tmp_path / "bad.cmsg")).getroot()
    assert "symbol 'y' is not defined" in root.find("messages/message").get("description")


def test_no_files_in_model_directory(modelFile):
    m = lpModel(modelFile)
    modelDir = os.path.dirname(m.modelName)
    m.solve()
    assert os.listdir(modelDir) == ["model.cmpl"]


def test_cmpl_without_data_stdin(modelFile, monkeypatch):
    """ older CMPL versions read the data from a file """
    import sys
    cmplModule = sys.modules["pyCmpl.Cmpl"]   # pyCmpl.Cmpl is the class
    monkeypatch.setitem(cmplModule._dataStdinSupport, cmplBinary(), False)
    m = lpModel(modelFile)
    m.solve()
    assert m.solution.value == 30


def test_data_stdin_is_detected():
    assert supportsDataStdin(cmplBinary()) in (True, False)
