"""Export the audited 20 mm ANSA sphere as a neutral IGES input fixture."""

import json
import os
import traceback

from ansa import base, constants


def main():
    source = os.environ["FLOWFORGE_IGES_SOURCE"]
    target = os.environ["FLOWFORGE_IGES_TARGET"]
    report = os.environ["FLOWFORGE_IGES_REPORT"]
    result = {"status": "error", "source": source, "target": target}
    try:
        base.Open(source)
        base.SetCurrentDeck(constants.NASTRAN)
        faces = base.CollectEntities(constants.NASTRAN, None, "FACE") or []
        result["faces"] = len(faces)
        result["source_units"] = base.GetLengthUnits()
        if not faces or result["source_units"].lower() != "millimeter":
            raise RuntimeError("Source sphere geometry or millimeter units are invalid")
        base.All()
        result["export_return"] = base.SaveFileAsIGES(target, "MILLIMETERS")
        if result["export_return"] != 1 or not os.path.isfile(target) or os.path.getsize(target) < 1000:
            raise RuntimeError("ANSA IGES export failed")
        result["bytes"] = os.path.getsize(target)
        result["status"] = "ok"
    except Exception:
        result["error"] = traceback.format_exc()
    with open(report, "w") as stream:
        json.dump(result, stream, indent=2)
    print("IGES_TEST_EXPORT_STATUS=" + result["status"])
    if result["status"] != "ok":
        print(result.get("error"))
