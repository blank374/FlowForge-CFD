"""Create a display-only STL from uploaded CAD in an isolated ANSA process."""
import json
import os
import traceback

from ansa import base, constants, mesh


def main():
    source = os.environ["FLOWFORGE_PREVIEW_SOURCE"]
    output = os.environ["FLOWFORGE_PREVIEW_STL"]
    report = os.environ["FLOWFORGE_PREVIEW_REPORT"]
    result = {"status": "error", "source": source}
    try:
        base.Open(source)
        deck = constants.NASTRAN
        base.SetCurrentDeck(deck)
        faces = base.CollectEntities(deck, None, "FACE") or []
        if not faces:
            raise RuntimeError("CAD import produced no surfaces")
        result["face_count"] = len(faces)
        base.All()
        result["mesh_return"] = repr(mesh.CreateCfdMesh())
        shells = sum(len(base.CollectEntities(deck, None, kind) or []) for kind in ("TRIA", "QUAD", "SHELL"))
        if not shells:
            raise RuntimeError("CAD preview meshing produced no surface elements")
        result["surface_elements"] = shells
        result["stl_return"] = base.OutputStereoLithography(filename=output, mode="all", format="binary")
        if result["stl_return"] != 0 or not os.path.isfile(output) or os.path.getsize(output) < 84:
            raise RuntimeError("ANSA STL preview export failed")
        result["status"] = "ok"
    except Exception:
        result["error"] = traceback.format_exc()
    with open(report, "w") as handle:
        json.dump(result, handle)
    print("FLOWFORGE_PREVIEW_STATUS=" + result["status"])


if __name__ == "__main__":
    main()
