"""Builds a platform wheel of pyCmpl with a bundled CMPL

    python tools/build_wheel.py <cmpl-dir> [--plat-name TAG] [--cmpl-license FILE] [--out DIR]

<cmpl-dir> is a flat CMPL runtime - the layout of binMac/binWin/binLinux:

    cmpl (cmpl.exe), cmpl.opt, modules.opt, solversel.opt, cmplstd.cmpl
    Thirdparty/Highs/highs, ...    solver paths in cmpl.opt relative to cmpl (e.g. HIGHS Thirdparty/Highs/highs)

Only the runtime files are copied - the Thirdparty directories of the solvers in cmpl.opt,
no IDE or Qt files. The platform tag is derived from the binaries (macOS: architecture and
deployment target), --plat-name overrides it.
"""

import argparse
import fnmatch
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "pyCmpl")

RUNTIME_FILES = ("cmpl", "cmpl.exe", "cmpl.opt", "modules.opt", "solversel.opt", "cmplstd.cmpl",
                 "gurobiCmpl", "gurobiCmpl.py", "gurobiCmpl.bat")
# runtime of the MinGW build on Windows
RUNTIME_PATTERNS = ("libgcc_s_*.dll", "libstdc++-*.dll", "libwinpthread-*.dll")


def fail(msg):
    sys.exit("ERROR: " + msg)


def warn(msg):
    print("WARNING: " + msg)


def binDirOf(cmplDir, platName):
    if platName:
        if platName.startswith("macosx"):
            return "binMac"
        if platName.startswith("win"):
            return "binWin"
        return "binLinux"
    if os.path.isfile(os.path.join(cmplDir, "cmpl.exe")):
        return "binWin"
    return {"Darwin": "binMac", "Linux": "binLinux"}.get(platform.system()) or fail("unknown platform")


def solverPaths(cmplDir):
    """ relative solver paths in cmpl.opt """
    paths = []
    with open(os.path.join(cmplDir, "cmpl.opt")) as f:
        for line in f:
            parts = line.split(None, 1)
            if len(parts) == 2 and not parts[0].startswith("#"):
                path = parts[1].strip()
                if not os.path.isabs(path) and not re.match(r"^[A-Za-z]:", path):
                    paths.append((parts[0], path))
    return paths


def macPlatName(files):
    """ platform tag from the Mach-O files: common architectures and highest deployment target """
    archs = None
    minos = (11, 0)
    for f in files:
        try:
            info = subprocess.run(["lipo", "-archs", f], capture_output=True, text=True)
        except OSError:
            fail("lipo not found - use --plat-name")
        if info.returncode != 0:
            continue    # no Mach-O file
        fArchs = set(info.stdout.split())
        archs = fArchs if archs is None else archs & fArchs
        load = subprocess.run(["otool", "-l", f], capture_output=True, text=True).stdout
        m = re.search(r"minos (\d+)\.(\d+)", load) or re.search(r"version (\d+)\.(\d+)", load)
        if m:
            minos = max(minos, (int(m.group(1)), int(m.group(2))))

    if not archs:
        fail("no common architecture of the binaries")
    arch = "universal2" if {"arm64", "x86_64"} <= archs else sorted(archs)[0]
    # since macOS 11 pip only knows the major version
    version = "%d_0" % minos[0] if minos[0] >= 11 else "10_%d" % minos[1]
    return "macosx_%s_%s" % (version, arch)


def copyRuntime(cmplDir, target):
    exe = "cmpl.exe" if os.path.isfile(os.path.join(cmplDir, "cmpl.exe")) else "cmpl"
    for f in (exe, "cmpl.opt", "modules.opt"):
        if not os.path.isfile(os.path.join(cmplDir, f)):
            fail(f + " not found in " + cmplDir)

    os.makedirs(target)
    for f in os.listdir(cmplDir):
        src = os.path.join(cmplDir, f)
        if os.path.isfile(src) and (f in RUNTIME_FILES or any(fnmatch.fnmatch(f, p) for p in RUNTIME_PATTERNS)):
            shutil.copy2(src, target)

    # Thirdparty directories of the solvers in cmpl.opt
    solvers = []
    for name, path in solverPaths(cmplDir):
        parts = re.split(r"[\\/]", path)
        if len(parts) >= 2 and parts[0] == "Thirdparty":
            src = os.path.join(cmplDir, parts[0], parts[1])
            dst = os.path.join(target, parts[0], parts[1])
            if not os.path.isfile(os.path.join(cmplDir, *parts)) and not os.path.isfile(os.path.join(cmplDir, *parts) + ".exe"):
                warn("solver %s (%s) not found - not bundled" % (name, path))
            elif not os.path.isdir(dst):
                shutil.copytree(src, dst)
                solvers.append(name)
    if not solvers:
        warn("no solver bundled")

    # executables must stay executable, even if the source has lost the bit
    if exe == "cmpl":
        executables = ["cmpl", "gurobiCmpl"] + [path for _, path in solverPaths(cmplDir)]
        for f in executables:
            f = os.path.join(target, *re.split(r"[\\/]", f))
            if os.path.isfile(f):
                os.chmod(f, os.stat(f).st_mode | 0o755)

    return os.path.join(target, exe), solvers


def checkDataStdin(exe):
    """ pyCmpl passes the data via stdin (-data-stdin), older CMPL versions read a data file """
    try:
        res = subprocess.run([exe, "-h"], capture_output=True)
    except OSError:
        return  # binary of another platform
    if b"-data-stdin" not in res.stdout + res.stderr:
        warn("this CMPL does not support -data-stdin - pyCmpl writes the data to a file")


def checkWheel(whl, binDir):
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        exe = [n for n in names if n.endswith("/" + binDir + "/cmpl") or n.endswith("/" + binDir + "/cmpl.exe")]
        if not exe:
            fail("cmpl is missing in " + whl)
        if not exe[0].endswith(".exe") and not (z.getinfo(exe[0]).external_attr >> 16) & 0o111:
            fail("cmpl is not executable in " + whl)
        return len([n for n in names if "/" + binDir + "/" in n])


def cleanBuild():
    shutil.rmtree(os.path.join(REPO, "build"), ignore_errors=True)
    for d in glob.glob(os.path.join(REPO, "*.egg-info")):
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="builds a platform wheel of pyCmpl with a bundled CMPL")
    ap.add_argument("cmplDir", help="flat CMPL runtime (cmpl, *.opt, Thirdparty/...)")
    ap.add_argument("--plat-name", help="platform tag, e.g. macosx_11_0_arm64, win_amd64 (default: from the binaries)")
    ap.add_argument("--cmpl-license", help="license of CMPL (default: LICENSE in cmplDir or ../CMPL2/LICENSE)")
    ap.add_argument("--out", default=os.path.join(REPO, "dist"), help="output directory (default: dist)")
    args = ap.parse_args()

    cmplDir = os.path.abspath(args.cmplDir)
    binDir = binDirOf(cmplDir, args.plat_name)
    target = os.path.join(PACKAGE, binDir)

    for d in ("binMac", "binWin", "binLinux"):
        if os.path.exists(os.path.join(PACKAGE, d)):
            fail("pyCmpl/%s exists - remove it first" % d)

    try:
        exe, solvers = copyRuntime(cmplDir, target)

        cmplLicense = args.cmpl_license
        if not cmplLicense:
            for f in (os.path.join(cmplDir, "LICENSE"), os.path.join(REPO, "..", "CMPL2", "LICENSE")):
                if os.path.isfile(f):
                    cmplLicense = f
                    break
        if cmplLicense:
            shutil.copy(cmplLicense, os.path.join(target, "LICENSE-CMPL"))
        else:
            warn("no license of CMPL found - use --cmpl-license")

        platName = args.plat_name
        if not platName:
            if binDir == "binMac":
                files = [os.path.join(dp, f) for dp, _, fs in os.walk(target) for f in fs if os.access(os.path.join(dp, f), os.X_OK)]
                platName = macPlatName(files)
            elif binDir == "binWin":
                platName = "win_amd64"
            else:
                platName = "linux_" + platform.machine()
                warn("a linux_* wheel can't be uploaded to PyPI (manylinux needs auditwheel)")

        checkDataStdin(exe)

        print("CMPL: " + exe + "\nsolvers: " + ", ".join(solvers) + "\nplatform: " + platName)

        cleanBuild()
        os.makedirs(args.out, exist_ok=True)
        env = dict(os.environ, PYCMPL_PLAT_NAME=platName)
        subprocess.run([sys.executable, "-m", "pip", "wheel", REPO, "--no-deps", "-w", args.out], env=env, check=True)

        wheels = [f for f in os.listdir(args.out) if f.endswith("-" + platName + ".whl")]
        if not wheels:
            fail("no wheel for " + platName + " in " + args.out)
        for w in wheels:
            n = checkWheel(os.path.join(args.out, w), binDir)
            print("wheel: %s (%d files of CMPL)" % (os.path.join(args.out, w), n))

    finally:
        shutil.rmtree(target, ignore_errors=True)
        cleanBuild()


if __name__ == "__main__":
    main()
