"""Save the demo aircraft's STL surface as an ANSA mesh project."""
import json
import os
import traceback

from ansa import base, constants


def main():
    source = os.environ["DEMO_AIRCRAFT_STL"]
    target = os.environ["DEMO_AIRCRAFT_ANSA"]
    report_path = os.environ["DEMO_AIRCRAFT_ANSA_REPORT"]
    report = {"status": "error", "source": source, "target": target,
              "note": "Mesh-only ANSA project; no CAD FACE entities"}
    try:
        if os.path.exists(target):
            raise RuntimeError("Refusing to overwrite existing project")
        report["import_return"] = base.InputStereoLithography(source, model_action="overwrite_model")
        if report["import_return"] != 0:
            raise RuntimeError("STL import failed")
        deck = constants.FLUENT
        report["shells"] = len(base.CollectEntities(deck, None, "SHELL") or [])
        report["faces"] = len(base.CollectEntities(deck, None, "FACE") or [])
        if report["shells"] < 100:
            raise RuntimeError("Too few imported surface elements")
        report["save_return"] = base.SaveAs(target)
        if report["save_return"] != 0 or not os.path.isfile(target):
            raise RuntimeError("ANSA save failed")
        report["status"] = "saved"
    except Exception:
        report["error"] = traceback.format_exc()
    with open(report_path, "w") as stream:
        json.dump(report, stream, indent=2)
    print("DEMO_AIRCRAFT_ANSA_STATUS=" + report["status"])
