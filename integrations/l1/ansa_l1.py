"""Create a documented test sphere CAD fixture or mesh an imported fixture in ANSA."""
import json
import os
import traceback

from ansa import base, constants, mesh


ACTION = os.environ.get("ANSA_L1_ACTION", "mesh")
OUT = os.environ["ANSA_L1_OUTPUT_DIR"]
FIXTURE_DIR = os.environ["ANSA_L1_FIXTURE_DIR"]
CAD = os.environ.get("ANSA_L1_CAD_INPUT", os.path.join(FIXTURE_DIR, "TEST_DATA_sphere_r10mm_v2.ansa"))
REPORT = os.path.join(OUT, "ansa_" + ACTION + ".json")
TARGET_LENGTH_MM = float(os.environ.get("ANSA_L1_TARGET_LENGTH_MM", "0.5"))


def main():
    result = {"status": "error", "action": ACTION, "test_data": CAD.lower().endswith(".ansa"),
              "cad": CAD, "length_units": "MILLIMETERS"}
    try:
        if not os.path.isdir(OUT):
            os.makedirs(OUT)
        if ACTION == "generate":
            if os.path.exists(CAD):
                raise IOError("Refusing to overwrite test CAD fixture: " + CAD)
            deck = constants.NASTRAN
            base.SetCurrentDeck(deck)
            base.SetLengthUnits("millimeter", False)
            part = base.CreateEntity(deck, "ANSAPART", {"Name": "TEST_ONLY_SPHERE_R10MM"})
            prop = base.CreateEntity(deck, "PSHELL", {"Name": "TEST_ONLY_SPHERE_R10MM"})
            old_defaults = base.GetANSAdefaultsValues({"ctolerance", "ntolerance", "perimeter_length"})
            base.SetANSAdefaultsValues({"ctolerance": 0.001, "ntolerance": 0.001,
                                        "perimeter_length": 1.0})
            created = base.CreateVolumeSphere([0.0, 0.0, 0.0], 10.0, part, prop, False)
            base.SetANSAdefaultsValues(old_defaults)
            faces = base.CollectEntities(deck, None, "FACE") or []
            cons = base.CollectEntities(deck, None, "CONS") or []
            if not created or len(faces) < 1 or len(cons) < 1:
                raise RuntimeError("ANSA did not create a topologized sphere surface")
            result["created_faces"] = len(faces)
            result["created_cons"] = len(cons)
            result["create_volume_sphere_return_count"] = len(created)
            base.All()
            result["native_save_return"] = base.SaveAs(CAD)
            if result["native_save_return"] != 0 or not os.path.isfile(CAD) or os.path.getsize(CAD) < 1000:
                raise RuntimeError("ANSA test geometry save failed")
            result["cad_bytes"] = os.path.getsize(CAD)
            result["status"] = "ok"
        elif ACTION == "mesh":
            if not os.path.isfile(CAD):
                raise IOError("Test CAD fixture missing: " + CAD)
            target = os.path.join(OUT, "l1_imported_meshed_sphere.ansa")
            stl = os.path.join(OUT, "l1_ansa_surface.stl")
            result["open_return"] = repr(base.Open(CAD))
            deck = constants.NASTRAN
            base.SetCurrentDeck(deck)
            faces = base.CollectEntities(deck, None, "FACE") or []
            cons = base.CollectEntities(deck, None, "CONS") or []
            result["imported_face_count"] = len(faces)
            result["imported_con_count"] = len(cons)
            result["imported_units"] = base.GetLengthUnits()
            if not faces or not cons:
                raise RuntimeError("ANSA CAD import did not produce connected geometry")
            if base.GetLengthUnits().lower() != "millimeter":
                raise RuntimeError("L1 sphere input must declare millimeter units")
            if CAD.lower().endswith((".igs", ".iges")):
                result["red_cons_before_topo"] = base.CountRedCons()
                result["topo_return"] = base.Topo(cons="all")
                result["red_cons_after_topo"] = base.CountRedCons()
            base.All()
            result["target_surface_length_mm"] = TARGET_LENGTH_MM
            result["defaults_before_mesh"] = base.GetANSAdefaultsValues({"perimeter_length"})
            base.SetANSAdefaultsValues({"perimeter_length": TARGET_LENGTH_MM})
            if CAD.lower().endswith((".igs", ".iges")):
                perimeter_cons = base.CollectEntities(deck, None, "CONS") or []
                result["perimeter_cons_count"] = len(perimeter_cons)
                result["apply_perimeter_length_return"] = mesh.ApplyNewLengthToMacros(str(TARGET_LENGTH_MM), perimeter_cons)
            result["target_length_return"] = mesh.SetMeshParamTargetLength("absolute", TARGET_LENGTH_MM)
            result["mesh_return"] = mesh.CreateCfdMesh()
            counts = {}
            for kind in ("SHELL", "TRIA", "QUAD", "GRID"):
                counts[kind] = len(base.CollectEntities(deck, None, kind) or [])
            result["mesh_counts"] = counts
            if not (counts["TRIA"] or counts["QUAD"] or counts["SHELL"]):
                raise RuntimeError("ANSA CFD surface mesh contains no shell elements")
            result["save_return"] = base.SaveAs(target)
            result["stl_return"] = base.OutputStereoLithography(filename=stl, mode="all", format="binary")
            if result["save_return"] != 0 or result["stl_return"] != 0:
                raise RuntimeError("ANSA save or STL export reported failure")
            for path in (target, stl):
                if not os.path.isfile(path) or os.path.getsize(path) < 1000:
                    raise RuntimeError("ANSA output missing or unexpectedly small: " + path)
            result["ansa_mesh"] = target
            result["stl"] = stl
            result["ansa_mesh_bytes"] = os.path.getsize(target)
            result["stl_bytes"] = os.path.getsize(stl)
            result["status"] = "ok"
        else:
            raise ValueError("Unknown ANSA_L1_ACTION: " + ACTION)
    except Exception:
        result["error"] = traceback.format_exc()
    with open(REPORT, "w") as stream:
        json.dump(result, stream, indent=2)
    print("ANSA_L1_ACTION=" + ACTION)
    print("ANSA_L1_STATUS=" + result["status"])
    print("ANSA_L1_REPORT=" + REPORT)
    if result["status"] != "ok":
        print(result.get("error", "unknown error"))
