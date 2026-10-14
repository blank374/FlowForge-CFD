"""Extract actual OpenFOAM cavity fields using ParaView 6.0.1."""
import json
import sys
from pathlib import Path

from paraview.simple import OpenFOAMReader, CellCenters, SaveData

case = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
marker = case / "cavity.foam"
marker.touch()
reader = OpenFOAMReader(FileName=str(marker))
reader.MeshRegions = ["internalMesh"]
reader.CellArrays = ["U", "p"]
reader.SkipZeroTime = 1
reader.UpdatePipeline()
time = float(reader.TimestepValues[-1])
reader.UpdatePipeline(time=time)
info = reader.GetDataInformation()
if info.GetNumberOfCells() != 400:
    raise RuntimeError(f"Expected official cavity 400 cells, got {info.GetNumberOfCells()}")
centers = CellCenters(Input=reader)
centers.UpdatePipeline(time=time)
SaveData(str(out / "cavity_centers.csv"), proxy=centers)
manifest = {"source": str(marker), "time_s": time, "variables": ["U", "p"],
            "association": "CELLS", "samples": info.GetNumberOfCells(),
            "paraview": "6.0.1", "camera": "XY orthographic data plot", "color_mapping": "turbo; data range"}
(out / "paraview_manifest.json").write_text(json.dumps(manifest, indent=2))
print("PARAVIEW_EXTRACT_OK=" + json.dumps(manifest))
