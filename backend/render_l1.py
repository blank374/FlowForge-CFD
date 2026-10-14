"""Export a real L1 mid-plane U/p slice from ParaView 6.0.1."""
import json
import sys
from pathlib import Path

from paraview.simple import OpenFOAMReader, Slice, CellCenters, SaveData, CreateView, Show, ColorBy, GetColorTransferFunction, SaveState

case = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
expected_cells = int(sys.argv[3])
time_s = float(sys.argv[4]) if len(sys.argv) > 4 else 0.2
marker = case / "case.foam"
marker.touch()
reader = OpenFOAMReader(FileName=str(marker))
reader.MeshRegions = ["internalMesh", "L1_WALL", "L1_FARFIELD"]
reader.CellArrays = ["U", "p"]
reader.SkipZeroTime = 1
reader.UpdatePipeline(time=time_s)
info = reader.GetDataInformation()
if info.GetNumberOfCells() != expected_cells:
    raise RuntimeError(f"Expected {expected_cells} L1 cells, got {info.GetNumberOfCells()}")
slice_proxy = Slice(Input=reader)
slice_proxy.SliceType = "Plane"
slice_proxy.SliceType.Origin = [0, 0, 0]
slice_proxy.SliceType.Normal = [0, 0, 1]
slice_proxy.UpdatePipeline(time=time_s)
slice_info = slice_proxy.GetDataInformation()
if slice_info.GetNumberOfCells() < 1000:
    raise RuntimeError("L1 mid-plane slice is unexpectedly small")
centers = CellCenters(Input=slice_proxy)
centers.UpdatePipeline(time=time_s)
SaveData(str(out / "slice_centers.csv"), proxy=centers)
view = CreateView("RenderView")
view.ViewSize = [1200, 900]
view.CameraParallelProjection = 1
view.CameraPosition = [0, 0, 0.3]
view.CameraFocalPoint = [0, 0, 0]
view.CameraViewUp = [0, 1, 0]
view.CameraParallelScale = 0.06
display = Show(slice_proxy, view)
ColorBy(display, ("CELLS", "U", "Magnitude"))
GetColorTransferFunction("U").RescaleTransferFunction(0, 0.09)
SaveState(str(out / "L1_U.pvsm"))
ColorBy(display, ("CELLS", "p"))
GetColorTransferFunction("p").RescaleTransferFunction(-0.003, 0.0035)
SaveState(str(out / "L1_p.pvsm"))
manifest = {"source": str(marker), "time_s": time_s, "slice_z_m": 0,
            "cells_in_reader": info.GetNumberOfCells(), "cells_in_slice": slice_info.GetNumberOfCells(),
            "variables": ["U", "p"], "association": "CELLS", "paraview": "6.0.1",
            "camera": "XY orthographic data plot", "color_mapping": "turbo; data range"}
(out / "paraview_manifest.json").write_text(json.dumps(manifest, indent=2))
print("PARAVIEW_EXTRACT_OK=" + json.dumps(manifest))
