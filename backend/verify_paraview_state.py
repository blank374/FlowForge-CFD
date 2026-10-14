"""Smoke-check that a saved ParaView state can be loaded."""

import sys

from paraview.simple import GetSources, LoadState

LoadState(sys.argv[1])
names = [name for name, _ in GetSources()]
if not any("OpenFOAMReader" in name or "case.foam" in name for name in names):
    raise RuntimeError(f"No OpenFOAM source in state: {names}")
print("PARAVIEW_STATE_REOPEN_OK=" + ", ".join(names))
