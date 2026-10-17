""" CmplMessages, CmplSolutions, CmplInstance and the package namespace - no CMPL binary needed """

import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from pyCmpl import CmplMessages, CmplSolutions, CmplInstance, CmplException, CMPL_FAILED

MSG = """<?xml version="1.0" encoding="UTF-8"?>
<CmplMessages version="1.2">
\t<general>
\t\t<generalStatus>error</generalStatus>
\t\t<instanceName>/a/b/model.cmpl</instanceName>
\t\t<message>cmpl finished with errors</message>
\t\t<cmplVersion>2.1.0</cmplVersion>
\t</general>
\t<messages numberOfMessages="1">
\t\t<message type="error" module="compile" location="model.cmpl:4.38" description="symbol &apos;y&apos; &lt;is&gt; not &quot;defined&quot; &amp; more"/>
\t</messages>
</CmplMessages>
"""

SOL = """<?xml version="1.0" encoding="UTF-8"?>
<CmplSolutions version="1.0">
   <general>
       <instanceName>model.cmpl</instanceName>
       <nrOfVariables>2</nrOfVariables>
       <nrOfConstraints>1</nrOfConstraints>
       <objectiveName>profit</objectiveName>
       <objectiveSense>max</objectiveSense>
       <nrOfSolutions>1</nrOfSolutions>
       <solverName>HIGHS</solverName>
       <solverMsg>normal</solverMsg>
       <variablesDisplayOptions>(all)</variablesDisplayOptions>
       <constraintsDisplayOptions>(all)</constraintsDisplayOptions>
   </general>
   <solution idx="0" status="INTEGER OPTIMAL" value="6.5">
       <variables>
           <variable idx="0" name="x[1,p]" type="I" activity="3.0" lowerBound="0" upperBound="inf" marginal="NaN"/>
           <variable idx="1" name="y" type="C" activity="0.5" lowerBound="-inf" upperBound="1" marginal="-"/>
       </variables>
       <linearConstraints>
           <constraint idx="0" name="cap" type="L" activity="3.5" lowerBound="-inf" upperBound="4" marginal="0.25"/>
       </linearConstraints>
   </solution>
</CmplSolutions>
"""


def test_read_messages():
    m = CmplMessages()
    m.readCmplMessages(MSG)
    assert m.cmplStatus == CMPL_FAILED
    assert len(m.cmplMessageList) == 1
    msg = m.cmplMessageList[0]
    assert (msg.type, msg.module, msg.location) == ("error", "compile", "model.cmpl:4.38")
    assert msg.description == "symbol 'y' <is> not \"defined\" & more"


def test_write_messages_is_valid_xml(tmp_path):
    m = CmplMessages()
    m.readCmplMessages(MSG)
    f = str(tmp_path / "x.cmsg")
    m.writeCmplMessages(f)
    root = ET.parse(f).getroot()
    assert root.find("general/generalStatus").text == "error"
    assert root.find("messages/message").get("description") == "symbol 'y' <is> not \"defined\" & more"

    again = CmplMessages(f)
    again.readCmplMessages()
    assert again.cmplMessageList[0].description == m.cmplMessageList[0].description


def test_wrong_message_file(tmp_path):
    f = tmp_path / "x.cmsg"
    f.write_text('<?xml version="1.0"?>\n<Other/>\n')
    with pytest.raises(CmplException):
        CmplMessages(str(f)).readCmplMessages()


def test_read_solution():
    s = CmplSolutions()
    s.readSolution(SOL)
    assert (s.nrOfVariables, s.nrOfConstraints, s.nrOfSolutions) == (2, 1, 1)
    assert (s.objectiveName, s.objectiveSense, s.solver, s.solverMessage) == ("profit", "max", "HIGHS", "normal")
    assert s.isIntegerProgram

    sol = s.solution
    assert (sol.idx, sol.status, sol.value) == (0, "INTEGER OPTIMAL", 6.5)
    x, y = sol.variables
    assert (x.name, x.type, x.activity, x.upperBound) == ("x[1,p]", "I", 3, float("inf"))
    assert isinstance(x.activity, int)
    assert y.lowerBound == float("-inf") and y.marginal != y.marginal     # NaN
    assert sol.constraints[0].marginal == 0.25


def test_wrong_solution_file():
    with pytest.raises(CmplException):
        CmplSolutions().readSolution('<?xml version="1.0"?>\n<Other/>\n')


def test_instance_with_missing_folder(tmp_path):
    with pytest.raises(CmplException):
        CmplInstance().writeCmplInstance(str(tmp_path / "missing") + "/", "<CmplInstance/>")


def test_star_import_keeps_builtins():
    code = ("import builtins\n"
            "from pyCmpl import *\n"
            "assert pow is builtins.pow, 'pow replaced'\n"
            "leaked = [n for n in ('e', 'pi', 'log', 'floor', 'os', 'time', 're', 'subprocess') if n in globals()]\n"
            "assert not leaked, leaked\n"
            "for n in ('Cmpl', 'CmplSet', 'CmplParameter', 'CmplException', 'CmplSolutions', 'CmplMessages',\n"
            "          'CmplXlsData', 'CmplArgs', 'CmplInstance', 'SOLVER_OK', 'CMPL_OK', 'PYCMPL', 'CMPL_STATUS_TXT'):\n"
            "    assert n in globals(), n\n")
    from conftest import SRC
    res = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r)\n" % SRC + code],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
