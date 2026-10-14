"""Import the demo IGES in ANSA and check whether topology closes its patches."""
import json
import os
import traceback
from ansa import base, constants


def main():
    source = os.environ["DEMO_IGES_SOURCE"]
    report_path = os.environ["DEMO_IGES_REPORT"]
    result = {"source": source, "status": "error"}
    try:
        base.Open(source)
        base.SetCurrentDeck(constants.NASTRAN)
        result["units"] = base.GetLengthUnits()
        result["faces_before"] = len(base.CollectEntities(constants.NASTRAN, None, "FACE") or [])
        result["cons_before"] = len(base.CollectEntities(constants.NASTRAN, None, "CONS") or [])
        result["red_cons_before"] = base.CountRedCons()
        result["topo_return"] = repr(base.Topo(cons="all"))
        result["faces_after"] = len(base.CollectEntities(constants.NASTRAN, None, "FACE") or [])
        result["cons_after"] = len(base.CollectEntities(constants.NASTRAN, None, "CONS") or [])
        result["red_cons_after"] = base.CountRedCons()
        result["intersections_after"] = len(base.CheckIntersections(True, False, True) or [])
        result["status"] = "ok" if result["units"] == "millimeter" and result["faces_after"] == 6 and result["red_cons_after"] == 0 and result["intersections_after"] == 0 else "failed_gate"
    except Exception:
        result["error"] = traceback.format_exc()
    with open(report_path, "w") as output:
        json.dump(result, output, indent=2)
    print("DEMO_IGES_VALIDATION=" + result["status"])
