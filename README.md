# pyCmpl

Python API for [CMPL](http://www.coliop.org): sets and parameters are defined in Python, the model in CMPL;
pyCmpl starts the solving process and reads the solution(s) back into the application.

pyCmpl is used by the CMPL distribution (`cmplStarter`, CMPL IDE) and by pyLogisticsLab.
This repository is the single source of pyCmpl for all of them.

## Installation

With CMPL included - a platform wheel (see [Platform wheels](#platform-wheels-with-cmpl)):

```bash
pip install pycmpl-2.2.0-py3-none-macosx_15_0_arm64.whl
pip install pyCmpl --find-links <page with the wheels>      # pip selects the wheel of the platform
```

Only the Python sources - CMPL is taken from `CMPLHOME`:

```bash
pip install "pyCmpl @ git+https://github.com/MikeSteglich/pyCmpl.git@v3.0.0"
pip install "pyCmpl[excel] @ git+https://github.com/MikeSteglich/pyCmpl.git@v3.0.0"   # with xlwings for Excel data
```

For development in several projects at the same time:

```bash
git clone https://github.com/MikeSteglich/pyCmpl.git
pip install -e pyCmpl          # changes are active immediately in every project of this environment
```

## CMPL binaries

pyCmpl looks for the CMPL binary in this order:

1. `$CMPLHOME/bin/cmpl` (`cmpl.exe` on Windows) - the layout of a CMPL installation:
   ```
   $CMPLHOME/
     bin/cmpl, bin/cmpl.opt, bin/modules.opt, bin/solversel.opt, bin/cmplstd.cmpl
     Thirdparty/Highs/highs, ...
   ```
2. `binMac/`, `binWin/` or `binLinux/` in the package - platform wheels and apps that bundle CMPL this way.
   A flat layout, the solver paths in `cmpl.opt` are relative to `cmpl`:
   ```
   binMac/
     cmpl, cmpl.opt (HIGHS Thirdparty/Highs/highs), modules.opt, solversel.opt, cmplstd.cmpl
     Thirdparty/Highs/highs, ...
   ```

The `cmpl` start script of a CMPL installation is not used, it does not accept the arguments of pyCmpl.

pyCmpl passes the data via stdin (`-data-stdin`, CMPL 2.2). With an older CMPL it writes the data
to a temporary file.

### Platform wheels with CMPL

`tools/build_wheel.py` copies a flat CMPL runtime into the package and builds a wheel for one platform
(`py3-none-<platform>`). It runs on the platform of the wheel:

```bash
python tools/build_wheel.py ../pyLogisticsLab/cmplDist/binMac          # -> dist/pycmpl-...-macosx_*_arm64.whl
python tools\build_wheel.py ..\pyLogisticsLab\cmplDist\binWin          # on Windows -> win_amd64
```

- Only the runtime is copied: `cmpl`, the `*.opt` files, `cmplstd.cmpl`, `gurobiCmpl`, the MinGW DLLs and
  the `Thirdparty` directories of the solvers in `cmpl.opt` - no IDE or Qt files.
- The platform tag comes from the binaries. On macOS it is the highest deployment target of `cmpl`
  and the solvers (e.g. HiGHS built for macOS 15 -> `macosx_15_0_arm64`), so build CMPL with
  `MACOSX_DEPLOYMENT_TARGET=11.0`. `--plat-name` overrides the tag.
- The license of CMPL (GPLv3) is added as `LICENSE-CMPL` (from the CMPL directory or `../CMPL2/LICENSE`).
- `pyCmpl/binMac` etc. exist only while the wheel is built; without them `pip install`
  builds a pure wheel (`py3-none-any`) as before.
- `linux_*` wheels can't be uploaded to PyPI, that needs `manylinux` (auditwheel).

## Cancelling

`Cmpl.cancel()`, cleanup after errors and interrupts (e.g. Ctrl+C) stop the whole process tree -
cmpl and the solver it has started (e.g. HiGHS). Before 2.1.0 only cmpl was stopped and the solver kept running.

## Changing pyCmpl

This repository is the only place where pyCmpl is changed. The other copies are generated from it:

| Location | What it is | How it is updated |
|---|---|---|
| `pyCmpl/` (this repository) | the sources | edited here |
| pyLogisticsLab | dependency in `requirements.txt` (git tag), also used by its distributions (`dist/`) | new tag in `requirements.txt` |
| CMPL distribution and CMPL IDE | copy in `pyCmpl/lib3/pyCmpl`, compiled into `cmplStarter` and `cmplServer` | `Cmpl2/dist/buildDist.py` takes a tag (`PYCMPL_DEFAULT`, `--pycmpl`) - never edit the copy by hand |

The steps below assume this layout of the working copies:

```
Projekte/
  pyCmpl/            this repository
  pyLogisticsLab/
  Cmpl2/             CMPL, build of the CMPL distribution and the CMPL IDE (dist/buildDist.py)
  CmplIde/
```

### 1. Development

Install this working copy in editable mode in the environment of the project you are testing with,
e.g. the conda environment `pyLogisticsLab`. Changes are active immediately, without reinstalling,
even if the project depends on a tag:

```bash
pip install -e ../pyCmpl
python -c "import pyCmpl; print(pyCmpl.__version__, pyCmpl.__file__)"   # must show this repository
```

Test the change in the projects that use pyCmpl, e.g. `tests/pyCmpl/find*.py` in pyLogisticsLab.

### 2. Release

1. Increase the version in **three** places: `pyproject.toml`, `pyCmpl/__init__.py` and `pyCmpl/Cmpl.py` (`__version__`).
2. Add an entry to the version list below.
3. Commit, tag and push:
   ```bash
   git commit -am "pyCmpl 3.0.1: ..."
   git tag -a v3.0.1 -m "pyCmpl 3.0.1"
   git push && git push origin v3.0.1
   ```
4. Build the platform wheels (`tools/build_wheel.py`, on macOS and Windows) and publish them,
   e.g. as assets of the GitHub release - with `--find-links` pip selects the right one.

### 3. Update the projects

- **pyLogisticsLab:** set the new tag in `requirements.txt`
  (`pyCmpl @ git+https://github.com/MikeSteglich/pyCmpl.git@v3.0.1`) and commit it.
  With the editable install from step 1 nothing has to be reinstalled locally;
  other machines and the server run `pip install -r requirements.txt`.
- **CMPL distribution and CMPL IDE** (in Cmpl2): set the new tag as `PYCMPL_DEFAULT` in `dist/buildDist.py`,
  commit it and build the distribution again - the tag is cloned, copied to `pyCmpl/lib3/pyCmpl`
  (with `PYCMPL_VERSION`) and compiled into `cmplStarter` and `cmplServer` (Nuitka):
  ```bash
  python3 dist/buildDist.py                        # with PYCMPL_DEFAULT
  python3 dist/buildDist.py --pycmpl ../pyCmpl     # the working copy instead of a tag, e.g. before a release
  ```

## Versions

Releases are git tags (`vX.Y.Z`); projects should depend on a tag, not on `main`.

### 3.0.0
- the solver of the cmpl command line is sent to the CmplServer (`cmpl ... -url` via cmplStarter) - before always
  `cbc`; default solver `highs` instead of `cbc` (as in cmpl)
- data via stdin (`-data-stdin`, CMPL 2.2), no temporary model copy, temporary files in an own directory
- platform wheels with a bundled CMPL (`tools/build_wheel.py`)
- relative Excel file in a CmplXlsData file is relative to the CmplXlsData file
- numpy/pandas numbers are numbers in the cmpl data (before: strings); non-integral floats as indices are an error (before: truncated)
- `setOption` after `delOption` no longer overwrites an option; `saveSolution` can be called several times;
  `saveSolutionCsv()` writes `.csv`; type check of the default value of a sparse parameter
- valid XML in `saveCmplMessageFile` and CmplInstance; `&quot;`, `&lt;` ... are decoded in messages
- variables/constraints/sets named like a method (e.g. `send`) no longer replace it (`getVarByName` still works)
- `cmplStatus`/`solverStatus` before `solve()`; errors of `getSolutions`/`removeProblem` of the CmplServer are reported
- `from pyCmpl import *` exports only the API (before also `os`, `sys`, `math.pow` instead of `pow`, ...)
- no `exec`/`eval`: reading a solution with 100,000 variables in Python takes ~0.25 s instead of ~1.1 s
- tests: `CMPLHOME=... python -m pytest` (the tests with CMPL are skipped without a CMPL binary)

### 2.1.0
- cancel/cleanup/interrupts stop cmpl and the solver (`stopProcessTree`)
- one implementation for all apps: no console window on Windows, no blocking stdout pipe without output,
  error messages of cmpl are always read
- `CMPLHOME` or bundled `binMac`/`binWin`/`binLinux`, clear error message if the binary is missing
- xlwings is imported only when Excel data are used
- no `SyntaxWarning` for regular expressions
- `str(CmplException)` returns the message (before only "ERROR:"), `e.msg` is unchanged

## License

LGPL-3.0-or-later, see `LICENSE`.
