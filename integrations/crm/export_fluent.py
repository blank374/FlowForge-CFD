"""Export a read-only ANSA CRM mesh copy to a new SI-scaled Fluent mesh."""
import hashlib
import json
import os
import traceback

from ansa import base, constants


SOURCE = os.environ["CRM_ANSA_SOURCE"]
TARGET = os.environ["CRM_FLUENT_TARGET"]
REPORT = os.environ["CRM_FLUENT_REPORT"]


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    report = {"status": "error", "source": SOURCE, "target": TARGET,
              "source_sha256_before": digest(SOURCE), "output_scale_mm_to_m": 0.001}
    try:
        if os.path.exists(TARGET):
            raise RuntimeError("Refusing to overwrite an existing export")
        base.Open(SOURCE)
        if base.GetLengthUnits().lower() != "millimeter":
            raise RuntimeError("Expected millimetre mesh; refusing to scale unknown unit")
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        properties = base.CollectEntities(deck, None, "__PROPERTIES__") or []
        report["property_shells"] = {}
        for prop in properties:
            report["property_shells"][prop._name] = len(base.CollectEntities(deck, prop, "SHELL") or [])
        report["shells"] = len(base.CollectEntities(deck, None, "SHELL") or [])
        report["solids"] = len(base.CollectEntities(deck, None, "SOLID") or [])
        report["nodes"] = len(base.CollectEntities(deck, None, "NODE") or [])
        if report["solids"] != 3722509 or report["shells"] != 124962:
            raise RuntimeError("Source mesh counts differ from the inspected CRM project")
        report["export_return"] = base.OutputFluent(filename=TARGET, mode="all",
                                                      format="ascii", scale=0.001,
                                                      write_solver_info="off")
        if report["export_return"] != 1 or not os.path.isfile(TARGET):
            raise RuntimeError("ANSA Fluent mesh export failed")
        report["target_bytes"] = os.path.getsize(TARGET)
        report["status"] = "exported"
    except Exception:
        report["error"] = traceback.format_exc()
    report["source_sha256_after"] = digest(SOURCE)
    if report["source_sha256_after"] != report["source_sha256_before"]:
        report["status"] = "source_changed"
    with open(REPORT, "w") as stream:
        json.dump(report, stream, indent=2)
    print("CRM_FLUENT_EXPORT=" + report["status"])
    print("CRM_FLUENT_REPORT=" + REPORT)


