import json
import os
from ansa import base, constants


def main():
    base.SetCurrentDeck(constants.NASTRAN)
    result = base.SurfacesFit([[0, 0, 0], [1, 0, 0], [0, 1, 0]], ret_ents=True)
    faces = base.CollectEntities(constants.NASTRAN, None, "FACE") or []
    with open(os.environ["DEMO_IGES_PROBE_REPORT"], "w") as stream:
        json.dump({"fit_result": repr(result), "faces": len(faces)}, stream)
    if faces:
        base.All()
        export = base.SaveFileAsIGES(file_name=os.environ["DEMO_IGES_PROBE"], file_units="MILLIMETERS", entities=faces)
        with open(os.environ["DEMO_IGES_PROBE_REPORT"], "w") as stream:
            json.dump({"fit_result": repr(result), "faces": len(faces), "export": export}, stream)
