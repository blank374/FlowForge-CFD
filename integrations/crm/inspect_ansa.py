"""Read-only inventory of a native CRM ANSA project; no mesh modification."""
import hashlib
import json
import os
import traceback

from ansa import base, constants


SOURCE = os.environ["CRM_ANSA_SOURCE"]
REPORT = os.environ["CRM_ANSA_REPORT"]
TYPES = ("FACE", "CONS", "HOT POINT", "SHELL", "TRIA", "QUAD", "GRID",
         "TETRA", "HEXA", "PENTA", "PYRAM", "SOLID", "VOLUME",
         "ANSAPART", "__PROPERTIES__", "__MATERIALS__")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    result = {"status": "error", "source": SOURCE, "source_bytes": os.path.getsize(SOURCE),
              "read_only": True, "sha256_before": digest(SOURCE)}
    try:
        result["open_return"] = repr(base.Open(SOURCE))
        result["length_units"] = base.GetLengthUnits()
        result["decks"] = {}
        for deck_name in ("FLUENT", "NASTRAN"):
            deck = getattr(constants, deck_name)
            info = {"counts": {}, "errors": {}}
            for kind in TYPES:
                try:
                    entities = base.CollectEntities(deck, None, kind) or []
                    info["counts"][kind] = len(entities)
                    if kind in ("ANSAPART", "__PROPERTIES__", "__MATERIALS__"):
                        info[kind] = [{"id": getattr(e, "_id", None),
                                       "name": getattr(e, "_name", None),
                                       "type": str(getattr(e, "_type", ""))} for e in entities[:500]]
                except Exception as exc:
                    info["errors"][kind] = str(exc)
            result["decks"][deck_name] = info
        try:
            result["topology_cons"] = {"red": base.CountRedCons(),
                                       "yellow": base.CountYellowCons(),
                                       "blue": base.CountBlueCons()}
        except Exception as exc:
            result["topology_cons_error"] = str(exc)
        result["status"] = "ok"
    except Exception:
        result["error"] = traceback.format_exc()
    result["sha256_after"] = digest(SOURCE)
    if result["sha256_after"] != result["sha256_before"]:
        result["status"] = "source_changed"
    with open(REPORT, "w") as stream:
        json.dump(result, stream, indent=2)
    print("CRM_ANSA_INSPECTION=" + result["status"])
    print("CRM_ANSA_REPORT=" + REPORT)


