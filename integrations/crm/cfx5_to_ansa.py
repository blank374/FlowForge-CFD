"""Import a CFX5 volume mesh into ANSA and save a mesh-only .ansa project."""
import json
import os
import traceback

from ansa import base, constants


def count(deck, kind):
    try:
        return len(base.CollectEntities(deck, None, kind) or [])
    except Exception:
        return None


def main():
    source = os.environ["FLOWFORGE_CFX5_SOURCE"]
    target = os.environ["FLOWFORGE_CFX5_ANSA"]
    report_path = os.environ["FLOWFORGE_CFX5_REPORT"]
    report = {"status": "error", "source": source, "target": target,
              "kind": "mesh_only_ansa_project"}
    try:
        if os.path.exists(target):
            raise RuntimeError("Refusing to overwrite existing ANSA project")
        result = base.InputCFX(filename=source, model_action="overwrite_model")
        report["input_return"] = result
        if result != 0:
            raise RuntimeError("ANSA InputCFX failed")
        deck = constants.FLUENT
        base.SetCurrentDeck(deck)
        report["counts"] = {kind: count(deck, kind) for kind in
                            ("FACE", "CONS", "NODE", "SHELL", "SOLID", "TETRA", "PENTA", "HEXA")}
        if not report["counts"]["NODE"] or report["counts"]["NODE"] < 1000:
            raise RuntimeError("Imported mesh contains too few nodes")
        report["save_return"] = base.SaveAs(target)
        if report["save_return"] != 0 or not os.path.isfile(target):
            raise RuntimeError("ANSA SaveAs failed")
        report["target_bytes"] = os.path.getsize(target)
        report["status"] = "saved"
    except Exception:
        report["error"] = traceback.format_exc()
    with open(report_path, "w") as stream:
        json.dump(report, stream, indent=2)
    print("CFX5_TO_ANSA_STATUS=" + report["status"])
