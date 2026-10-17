# pyCmpl

Python API for [CMPL](http://www.coliop.org): sets and parameters are defined in Python, the model in CMPL;
pyCmpl starts the solving process and reads the solution(s) back into the application.

pyCmpl is used by the CMPL distribution (`cmplStarter`, CMPL IDE) and by pyLogisticsLab.
This repository is the single source of pyCmpl for all of them.

## Installation

```bash
pip install "pyCmpl @ git+https://github.com/MikeSteglich/pyCmpl.git@v2.1.0"
pip install "pyCmpl[excel] @ git+https://github.com/MikeSteglich/pyCmpl.git@v2.1.0"   # with xlwings for Excel data
```

For development in several projects at the same time:

```bash
git clone https://github.com/MikeSteglich/pyCmpl.git
pip install -e pyCmpl          # changes are active immediately in every project of this environment
```

## CMPL binaries

The package contains only the Python sources. pyCmpl looks for the CMPL binary in this order:

1. `$CMPLHOME/bin/cmpl` (`cmpl.exe` on Windows) - the layout of a CMPL installation:
   ```
   $CMPLHOME/
     bin/cmpl, bin/cmpl.opt, bin/modules.opt, bin/solversel.opt, bin/cmplstd.cmpl
     Thirdparty/Highs/highs, ...
   ```
2. `binMac/`, `binWin/` or `binLinux/` next to the package - for apps that bundle CMPL this way.

The `cmpl` start script of a CMPL installation is not used, it does not accept the arguments of pyCmpl.

## Cancelling

`Cmpl.cancel()`, cleanup after errors and interrupts (e.g. Ctrl+C) stop the whole process tree -
cmpl and the solver it has started (e.g. HiGHS). Before 2.1.0 only cmpl was stopped and the solver kept running.

## Versions

Releases are git tags (`vX.Y.Z`); projects should depend on a tag, not on `main`.

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
