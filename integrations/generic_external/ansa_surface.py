"""Mesh an approved, closed ANSA CAD working copy for external CFD."""
import json
import os
import time
import traceback

from ansa import base, constants, mesh


def main():
    source = os.environ["FLOWFORGE_SURFACE_SOURCE"]
    output = os.environ["FLOWFORGE_SURFACE_OUTPUT"]
    report_path = os.environ["FLOWFORGE_SURFACE_REPORT"]
    length = float(os.environ.get("FLOWFORGE_SURFACE_LENGTH_MM", "12"))
    result = {"status": "error", "source": source, "target_length_mm": length}
    started = time.time()
    try:
        if not 0.1 <= length <= 100:
            raise ValueError("Surface length outside supported millimetre range")
        if any(os.path.exists(os.path.join(output, name)) for name in ("surface.ansa", "surface.stl")):
            raise RuntimeError("Output already exists; use a fresh stage directory")
        base.Open(source)
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        result["unit"] = str(base.GetLengthUnits())
        if result["unit"].lower() != "millimeter":
            raise RuntimeError("Approved CAD must declare millimetres")
        faces = base.CollectEntities(deck, None, "FACE") or []
        cons = base.CollectEntities(deck, None, "CONS") or []
        result["cad_faces"] = len(faces)
        result["cad_cons"] = len(cons)
        result["open_cons"] = sum(len(base.GetFacesOfCons(con) or []) == 1 for con in cons)
        result["nonmanifold_cons"] = sum(len(base.GetFacesOfCons(con) or []) > 2 for con in cons)
        if not faces or result["open_cons"] or result["nonmanifold_cons"]:
            raise RuntimeError("CAD surface is not closed and manifold")
        base.All()
        base.SetANSAdefaultsValues({"perimeter_length": length})
        result["apply_length_return"] = repr(mesh.ApplyNewLengthToMacros(str(length), cons))
        result["target_length_return"] = repr(mesh.SetMeshParamTargetLength("absolute", length))
        result["mesh_return"] = repr(mesh.CreateCfdMesh())
        result["tria"] = len(base.CollectEntities(deck, None, "TRIA") or [])
        result["quad"] = len(base.CollectEntities(deck, None, "QUAD") or [])
        result["shell"] = len(base.CollectEntities(deck, None, "SHELL") or [])
        if result["tria"] + result["quad"] + result["shell"] < 1000:
            raise RuntimeError("No usable surface mesh was generated")
        result["intersection_regions"] = base.CheckIntersections(False, False, True)
        if result["intersection_regions"] is not None:
            result["intersection_region_count"] = len(result["intersection_regions"])
            if result["intersection_region_count"]:
                raise RuntimeError("Surface elements intersect")
        else:
            result["intersection_region_count"] = 0
        project = os.path.join(output, "surface.ansa")
        stl = os.path.join(output, "surface.stl")
        result["save_return"] = base.SaveAs(project)
        result["stl_return"] = base.OutputStereoLithography(filename=stl, mode="all", format="binary")
        if result["save_return"] != 0 or result["stl_return"] != 0:
            raise RuntimeError("ANSA project save or STL export failed")
        for path in (project, stl):
            if not os.path.isfile(path) or os.path.getsize(path) < 1000:
                raise RuntimeError("Missing or empty output: " + path)
        result["status"] = "meshed"
    except Exception:
        result["error"] = traceback.format_exc()
    result["elapsed_seconds"] = round(time.time() - started, 2)
    with open(report_path, "w") as stream:
        json.dump(result, stream, indent=2, default=str)
    print("FLOWFORGE_SURFACE_STATUS=" + result["status"])


