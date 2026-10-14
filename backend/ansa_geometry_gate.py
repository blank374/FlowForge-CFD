"""Conservative ANSA 20.1.6 geometry gate; never edits the uploaded source."""
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


def check(name, actual, criterion, status, reason=""):
    return dict(name=name, actual=actual, pass_condition=criterion, status=status, reason=reason)


def snapshot(deck):
    faces = base.CollectEntities(deck, None, "FACE") or []
    cons = base.CollectEntities(deck, None, "CONS") or []
    free, nonmanifold, detached = [], [], []
    for con in cons:
        adjacent = base.GetFacesOfCons(con)
        if adjacent is None:
            raise RuntimeError("GetFacesOfCons returned None for CONS {}".format(con._id))
        count = len(adjacent)
        if count == 1:
            free.append(con._id)
        elif count > 2:
            nonmanifold.append(con._id)
        elif count == 0:
            detached.append(con._id)
    return dict(face_count=len(faces), con_count=len(cons),
                free_cons_count=len(free), free_cons_ids=free[:200],
                nonmanifold_cons_count=len(nonmanifold), nonmanifold_cons_ids=nonmanifold[:200],
                detached_cons_count=len(detached), detached_cons_ids=detached[:200])


def element_intersections():
    # API docs: this checks FE elements, not CAD FACE intersections.
    regions = base.CheckIntersections(False, False, True)
    if regions is None:
        return dict(status="none", region_count=0, note="No intersected FE elements reported; CAD self-intersection is not proven absent")
    if not isinstance(regions, (list, tuple)) or any(not isinstance(x, (list, tuple)) for x in regions):
        raise RuntimeError("Unexpected CheckIntersections return type: {}".format(type(regions).__name__))
    return dict(status="found" if regions else "none", region_count=len(regions),
                element_count=sum(len(x) for x in regions),
                note="ANSA CheckIntersections(..., fast_run=False, return_regions=True) reports FE element regions, not CAD face intersections")


def main():
    source = os.environ["FLOWFORGE_GATE_SOURCE"]
    target = os.environ["FLOWFORGE_GATE_PROJECT"]
    report_path = os.environ["FLOWFORGE_GATE_REPORT"]
    report = dict(status="error", source=source, project=target, checks=[], source_sha256=None)
    try:
        report["source_sha256"] = digest(source)
        # A fresh ANSA process imports the immutable input; all following changes
        # remain in memory until saved to the independent review.ansa path.
        opened = base.Open(source)
        base.All()
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        before = snapshot(deck)
        report["import_return"] = repr(opened)
        report["before_topo"] = before
        if not before["face_count"]:
            raise RuntimeError("CAD import produced zero FACE entities")
        report["unit"] = str(base.GetLengthUnits())
        report["import_save_return"] = repr(base.SaveAs(target))
        if not os.path.isfile(target) or os.path.getsize(target) == 0:
            raise RuntimeError("Initial ANSA working copy was not saved")
        # Documented Topo(cons='all', paste_with_frozen_faces=False,
        # paste_different_pids=False) uses the existing ANSA tolerances.
        # We do not adjust tolerances or paste across different PIDs.
        topo_result = base.Topo(cons="all", paste_with_frozen_faces=False,
                                paste_different_pids=False)
        report["topo_return"] = topo_result
        if topo_result not in (0, 1):
            raise RuntimeError("Unexpected Topo return: {}".format(repr(topo_result)))
        after = snapshot(deck)
        report["after_topo"] = after
        report["element_intersections"] = element_intersections()
        options = ["CRACKS", "OVERLAPS", "NEEDLE FACES", "COLLAPSED CONS", "TRIPLE CONS"]
        geometry = base.CheckAndFixGeometry(0, options, [0] * len(options), True, True)
        if geometry is not None and not isinstance(geometry, dict):
            raise RuntimeError("Unexpected CheckAndFixGeometry return type")
        failed = [] if geometry is None else geometry.get("failed")
        if failed is None:
            raise RuntimeError("Incomplete CheckAndFixGeometry report")
        report["geometry_check"] = dict(options=options, fix_options=[0] * len(options),
                                         failed_count=len(failed),
                                         remaining_errors=[] if geometry is None else geometry.get("remaining_errors"),
                                         failed_ids=[getattr(x, "_id", None) for x in failed[:200]])
        report["checks"] = [
            check("CAD FACE import", after["face_count"], "> 0", "passed"),
            check("nonmanifold CONS", after["nonmanifold_cons_count"], "= 0",
                  "passed" if not after["nonmanifold_cons_count"] else "failed"),
            check("detached CONS", after["detached_cons_count"], "= 0",
                  "passed" if not after["detached_cons_count"] else "failed"),
            check("open CONS", after["free_cons_count"], "= 0 or engineer-confirmed intended openings",
                  "passed" if not after["free_cons_count"] else "review",
                  "Boundary intent cannot be inferred from IGES alone" if after["free_cons_count"] else ""),
            check("ANSA geometry checks", len(failed), "= 0", "passed" if not failed else "failed",
                  ", ".join(report["geometry_check"]["remaining_errors"] or []) if failed else ""),
            check("FE element intersections", report["element_intersections"]["region_count"], "= 0",
                  "passed" if not report["element_intersections"]["region_count"] else "failed",
                  "Does not validate CAD face self-intersection"),
        ]
        report["final_save_return"] = repr(base.SaveAs(target))
        if not os.path.isfile(target) or os.path.getsize(target) == 0:
            raise RuntimeError("Post-Topo ANSA working copy was not saved")
        statuses = [item["status"] for item in report["checks"]]
        report["status"] = ("needs_manual_repair" if "failed" in statuses else
                            "waiting_for_review" if "review" in statuses else "passed")
    except Exception:
        report["status"] = "error"
        report["error"] = traceback.format_exc()
    try:
        report["source_unchanged"] = digest(source) == report["source_sha256"]
        if not report["source_unchanged"]:
            report["status"] = "error"
            report["error"] = "Uploaded source changed during inspection"
    except Exception:
        report["status"] = "error"
        report["error"] = traceback.format_exc()
    with open(report_path, "w") as stream:
        json.dump(report, stream, indent=2)
    print("FLOWFORGE_GEOMETRY_GATE=" + report["status"])


if __name__ == "__main__":
    main()
