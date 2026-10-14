"""Read-only ANSA topology diagnostic for an uploaded CRM IGES file."""
import hashlib
import json
import os
import traceback

from ansa import base, constants


def digest(path):
    sha = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    source = os.environ["FLOWFORGE_CRM_SOURCE"]
    report_path = os.environ["FLOWFORGE_CRM_REPORT"]
    report = {"status": "error", "source": source, "source_sha256_before": digest(source)}
    try:
        base.Open(source)
        base.All()
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        faces = base.CollectEntities(deck, None, "FACE") or []
        cons = base.CollectEntities(deck, None, "CONS") or []
        if not faces or not cons:
            raise RuntimeError("ANSA did not import CAD faces and curves; this input may be a mesh rather than CAD")
        free = [c._id for c in cons if len(base.GetFacesOfCons(c) or []) == 1]
        report.update(length_units=base.GetLengthUnits(), face_count=len(faces),
                      con_count=len(cons), free_cons_count=len(free), free_cons_ids=free)
        report["cad_intersection_regions"] = len(base.CheckIntersections(True, False, True) or [])
        report["status"] = "diagnosed"
    except Exception:
        report["error"] = traceback.format_exc()
    report["source_sha256_after"] = digest(source)
    report["source_unchanged"] = report["source_sha256_before"] == report["source_sha256_after"]
    if not report["source_unchanged"]:
        report["status"] = "source_changed"
    with open(report_path, "w") as stream:
        json.dump(report, stream, indent=2)
    print("FLOWFORGE_CRM_DIAGNOSIS=" + report["status"])
