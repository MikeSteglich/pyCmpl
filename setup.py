# Wheel tag of pyCmpl - the metadata is in pyproject.toml
#
# Without a bundled CMPL (pyCmpl/binMac, binWin or binLinux) the wheel is pure Python (py3-none-any).
# With a bundled CMPL it is a platform wheel (py3-none-<platform>); tools/build_wheel.py copies the
# CMPL runtime into the package and sets the platform in PYCMPL_PLAT_NAME.

import os

from setuptools import setup

try:
    from setuptools.command.bdist_wheel import bdist_wheel
except ImportError:  # setuptools < 70.1
    from wheel.bdist_wheel import bdist_wheel

BIN_DIRS = ("binMac", "binWin", "binLinux")


def bundledCmpl():
    here = os.path.dirname(os.path.abspath(__file__))
    return [d for d in BIN_DIRS if os.path.isdir(os.path.join(here, "pyCmpl", d))]


class BdistWheel(bdist_wheel):

    def get_tag(self):
        if not bundledCmpl():
            return super().get_tag()

        platName = os.environ.get("PYCMPL_PLAT_NAME")
        if not platName:
            raise SystemExit("pyCmpl contains a CMPL binary (" + ", ".join(bundledCmpl()) +
                             ") - build the wheel with tools/build_wheel.py")
        # the binaries don't depend on the Python version
        return "py3", "none", platName.replace("-", "_").replace(".", "_")


setup(cmdclass={"bdist_wheel": BdistWheel})
