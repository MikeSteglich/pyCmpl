""" remote mode (connect/send/knock/retrieve) against a fake CmplServer in this process """

import os
import subprocess
import threading
from xmlrpc.server import SimpleXMLRPCServer

import pytest

from pyCmpl import (Cmpl, CmplException, CMPLSERVER_OK, CMPLSERVER_ERROR, CMPLSERVER_CLEANED,
                    PROBLEM_FINISHED, PROBLEM_NOTRUNNING, PROBLEM_CANCELED)
from pyCmpl.Cmpl import cmplBinary

from conftest import LP_MODEL
from test_solve import lpModel

pytestmark = pytest.mark.usefixtures("cmplAvailable", "workDir")

DATA = '%I set < 1 2 3 >\n%c[I] < 3 1 2 >\n%b < 10 >\n'


class FakeCmplServer:
    """ answers like a CmplServer, the results come from a local cmpl run """

    def __init__(self, cmsg, csol, failSolutions=False):
        self.cmsg, self.csol, self.failSolutions = cmsg, csol, failSolutions
        self.calls, self.instance, self.sent = [], None, False

    def getJobId(self, name, solver, compatibility):
        self.calls.append("getJobId")
        return [CMPLSERVER_OK, "", "job-1"]

    def send(self, instance):
        self.calls.append("send")
        self.instance, self.sent = instance, True
        return [CMPLSERVER_OK, "", ""]

    def knock(self, jobId):
        self.calls.append("knock")
        return [PROBLEM_FINISHED if self.sent else PROBLEM_NOTRUNNING, "", ""]

    def getCmplMessages(self, jobId):
        self.calls.append("getCmplMessages")
        return [PROBLEM_FINISHED, "", self.cmsg]

    def getSolutions(self, jobId):
        self.calls.append("getSolutions")
        if self.failSolutions:
            return [CMPLSERVER_ERROR, "solution file is lost", ""]
        return [PROBLEM_FINISHED, "", self.csol]

    def cancel(self, jobId):
        self.calls.append("cancel")
        return [PROBLEM_CANCELED, "", ""]

    def removeProblem(self, jobId):
        self.calls.append("removeProblem")
        return [CMPLSERVER_CLEANED, "", ""]


@pytest.fixture
def server(modelFile, tmp_path):
    """ starts the fake server, returns (url, server object factory) """
    model = modelFile(LP_MODEL)
    dataFile = os.path.splitext(model)[0] + ".cdat"     # a file - works also with CMPL without -data-stdin
    with open(dataFile, "w") as f:
        f.write(DATA)
    try:
        subprocess.run([cmplBinary(), model, "-solution", str(tmp_path / "r.csol"),
                        "-cmsg", str(tmp_path / "r.cmsg"), "-silent-start"],
                       stdout=subprocess.DEVNULL, check=True)
    finally:
        os.remove(dataFile)
    cmsg, csol = (tmp_path / "r.cmsg").read_text(), (tmp_path / "r.csol").read_text()

    servers = []

    def start(**kw):
        fake = FakeCmplServer(cmsg, csol, **kw)
        srv = SimpleXMLRPCServer(("127.0.0.1", 0), logRequests=False, allow_none=True)
        srv.register_instance(fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return "http://127.0.0.1:%d" % srv.server_address[1], fake

    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()      # later calls (e.g. cleanup in __del__) are refused instead of hanging


def test_remote_solve(modelFile, server):
    url, fake = server()
    m = lpModel(modelFile)
    m.setRefreshTime(0.01)
    m.connect(url)
    m.solve()

    assert m.solution.value == 30 and m.x[1].activity == 10
    assert "%c[I]" in fake.instance and "cap:" in fake.instance
    assert fake.calls[0] == "getJobId" and "send" in fake.calls and fake.calls[-1] == "removeProblem"


def test_remote_solution_error(modelFile, server):
    url, fake = server(failSolutions=True)
    m = lpModel(modelFile)
    m.setRefreshTime(0.01)
    m.connect(url)
    with pytest.raises(CmplException) as e:
        m.solve()
    assert "solution file is lost" in e.value.msg
