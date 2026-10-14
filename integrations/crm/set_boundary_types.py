"""Set known CRM patch classes on a separate OpenFOAM conversion copy."""
import json
import re
import sys
from pathlib import Path


EXPECTED = {
    "far": (7188, "patch"),
    "fuse": (6971, "wall"),
    "inlet": (1956, "patch"),
    "outlet": (1958, "patch"),
    "sym": (77699, "symmetryPlane"),
    "wing": (29190, "wall"),
}


def main(case: Path):
    boundary = case / "constant" / "polyMesh" / "boundary"
    original = boundary.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^    (\w+)\s*\{([^}]+)\}", original))
    found = {match.group(1): int(re.search(r"nFaces\s+(\d+);", match.group(2)).group(1))
             for match in matches}
    if found != {name: spec[0] for name, spec in EXPECTED.items()}:
        raise RuntimeError("CRM patch names or face counts differ: " + repr(found))
    target = original
    for name, (_, kind) in EXPECTED.items():
        pattern = rf"(?m)(^    {name}\s*\{{)([^}}]+)(\}})"
        def replace(match):
            body = re.sub(r"type\s+\w+;", f"type            {kind};", match.group(2), count=1)
            body = re.sub(r"inGroups\s+List<word>\s+1\(\w+\);",
                          f"inGroups        List<word> 1({kind});", body, count=1)
            return match.group(1) + body + match.group(3)
        target, count = re.subn(pattern, replace, target, count=1)
        if count != 1:
            raise RuntimeError("Missing patch block: " + name)
    backup = boundary.with_name("boundary.before_types")
    if backup.exists():
        raise RuntimeError("Boundary types were already edited")
    backup.write_text(original, encoding="utf-8")
    boundary.write_text(target, encoding="utf-8")
    report = case.parent / "boundary_types.json"
    report.write_text(json.dumps({"status": "changed_on_trial_copy", "patches": EXPECTED,
                                  "original": str(backup), "updated": str(boundary)}, indent=2), encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
