import json
import os
import traceback

from ansa import base, constants


def main():
    source = os.environ["FLOWFORGE_CFX5_ANSA"]
    target = os.environ["FLOWFORGE_CFX5_VERIFY_REPORT"]
    report = {"status": "error", "source": source}
    try:
        base.Open(source)
        deck = constants.FLUENT
        report["nodes"] = len(base.CollectEntities(deck, None, "NODE") or [])
        report["shells"] = len(base.CollectEntities(deck, None, "SHELL") or [])
        report["solids"] = len(base.CollectEntities(deck, None, "SOLID") or [])
        report["cad_faces"] = len(base.CollectEntities(deck, None, "FACE") or [])
        if (report["nodes"], report["shells"], report["solids"]) != (1450569, 124962, 3722509):
            raise RuntimeError("Reopened ANSA mesh counts differ from CFX5 import")
        report["status"] = "verified"
    except Exception:
        report["error"] = traceback.format_exc()
    with open(target, "w") as stream:
        json.dump(report, stream, indent=2)
    print("ANSA_MESH_REOPEN_STATUS=" + report["status"])
