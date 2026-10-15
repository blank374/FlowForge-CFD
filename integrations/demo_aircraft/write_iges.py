"""Write a small, faceted six-patch IGES CAD test fixture from the demo shape."""
import math
from pathlib import Path

from generate import point


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "demo_aircraft_test.igs"
N = 17


def record(data, section, number):
    assert len(data) <= 72
    return f"{data:<72}{section}{number:7d}\n"


def field(value):
    return f"{value:>8}"


def knots(n):
    return [0, 0] + list(range(1, n - 1)) + [n - 1, n - 1]


def direction(face, u, v):
    if face == 0: return (1, u, v)
    if face == 1: return (-1, u, v)
    if face == 2: return (u, 1, v)
    if face == 3: return (u, -1, v)
    if face == 4: return (u, v, 1)
    return (u, v, -1)


def parameters(face):
    values = [128, N - 1, N - 1, 1, 1, 0, 0, 1, 0, 0]
    values += knots(N) + knots(N)
    values += [1] * (N * N)
    for j in range(N):
        v = -1 + 2 * j / (N - 1)
        for i in range(N):
            u = -1 + 2 * i / (N - 1)
            xyz = direction(face, u, v)
            length = math.sqrt(sum(c*c for c in xyz))
            values.extend(point(tuple(c / length for c in xyz)))
    values += [0, N - 1, 0, N - 1]
    return ",".join(f"{float(v):.10g}" if isinstance(v, float) else str(v) for v in values) + ";"


def main(patch_count=6):
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite existing IGES fixture")
    sections = {"S": [], "G": [], "D": [], "P": []}
    sections["S"].append(record("FlowForge small aircraft IGES test fixture", "S", 1))
    # Reuse a known ANSA global section with MM units, updating only the display name.
    sphere = (ROOT.parents[1] / "data" / "test_sphere_20mm.igs").read_text(errors="replace").splitlines()
    global_data = "".join(line[:72] for line in sphere if len(line) >= 73 and line[72] == "G").rstrip()
    marker = "47HF:\\Auto\\FlowForge-CFD\\data\\test_sphere_20mm.igs"
    if marker not in global_data:
        raise RuntimeError("Known-good IGES global section changed")
    name = "demo_aircraft.igs"
    global_data = global_data.replace(marker, f"{len(name)}H{name}")
    for start in range(0, len(global_data), 72):
        sections["G"].append(record(global_data[start:start+72], "G", len(sections["G"]) + 1))
    for face in range(patch_count):
        directory_pointer = 2 * face + 1
        payload = parameters(face)
        chunks = [payload[i:i+64] for i in range(0, len(payload), 64)]
        start_line = len(sections["P"]) + 1
        for chunk in chunks:
            sections["P"].append(f"{chunk:<64}{directory_pointer:8d}P{len(sections['P'])+1:7d}\n")
        first = [128, start_line, 0, 0, 0, 0, 0, 0, "00000000"]
        second = [128, 0, 0, len(chunks), 0, 0, 0, f"PATCH{face+1}", face+1]
        sections["D"].append("".join(field(x) for x in first) + f"D{directory_pointer:7d}\n")
        sections["D"].append("".join(field(x) for x in second) + f"D{directory_pointer+1:7d}\n")
    terminator = "".join(f"{key}{len(sections[key]):7d}" for key in ("S", "G", "D", "P"))
    with OUT.open("w", encoding="ascii", newline="\n") as stream:
        for key in ("S", "G", "D", "P"):
            stream.writelines(sections[key])
        stream.write(record(terminator, "T", 1))
    print(f"{OUT} {OUT.stat().st_size} bytes; {patch_count} IGES type-128 patches")


if __name__ == "__main__":
    main()
