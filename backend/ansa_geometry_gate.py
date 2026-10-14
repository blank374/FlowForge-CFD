"""Read-only geometry gate run inside ANSA. Save an independent review copy."""
import hashlib
import json
import os
import traceback

from ansa import base, constants


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    source = os.environ["FLOWFORGE_GATE_SOURCE"]
    target = os.environ["FLOWFORGE_GATE_PROJECT"]
    report_path = os.environ["FLOWFORGE_GATE_REPORT"]
    report = {"status": "error", "source_sha256": digest(source)}
    try:
        base.Open(source)
        base.All()
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        faces = base.CollectEntities(deck, None, "FACE") or []
        cons = base.CollectEntities(deck, None, "CONS") or []
        # Inspection only. Topo, stitching and surface repair belong in ANSA GUI.
        free = [c._id for c in cons if len(base.GetFacesOfCons(c) or []) == 1]
        intersections = base.CheckIntersections(True, False, True) or []
        report.update(unit=str(base.GetLengthUnits()), face_count=len(faces),
                      con_count=len(cons), free_cons_count=len(free),
                      free_cons_ids=free[:200], cad_intersection_regions=len(intersections))
        if faces:
            report["save_return"] = base.SaveAs(target)
        report["status"] = "passed" if faces and cons and not free and not intersections and os.path.isfile(target) else "needs_manual_repair"
    except Exception:
        report["error"] = traceback.format_exc()
    report["source_unchanged"] = digest(source) == report["source_sha256"]
    if not report["source_unchanged"]:
        report["status"] = "error"
        report["error"] = "Source file changed during inspection"
    with open(report_path, "w") as stream:
        json.dump(report, stream, indent=2)
    print("FLOWFORGE_GEOMETRY_GATE=" + report["status"])


if __name__ == "__main__":
    main()
