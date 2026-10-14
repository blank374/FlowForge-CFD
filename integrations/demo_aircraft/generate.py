"""Generate a smooth, watertight, illustrative aircraft-like body (not CRM CAD)."""
import json
import math
import struct
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "demo_aircraft_v3.stl"


def point(direction):
    x, y, z = direction
    # An elongated fuselage with a smooth horizontal wing lobe.
    body = 1.0 / math.sqrt((x / 12.0) ** 2 + (y / 2.4) ** 2 + (z / 2.2) ** 2)
    wing = 9.0 * abs(y) ** 2 * math.exp(-((x + 0.08) / 0.55) ** 2) * math.exp(-(z / 0.25) ** 2)
    horizontal_tail = 4.0 * abs(y) ** 2 * math.exp(-((x + 0.78) / 0.24) ** 2) * math.exp(-(z / 0.28) ** 2)
    vertical_tail = 5.0 * max(z, 0.0) ** 2 * math.exp(-((x + 0.72) / 0.28) ** 2) * math.exp(-(y / 0.25) ** 2)
    radius = body + wing + horizontal_tail + vertical_tail
    return np.asarray(direction, dtype=np.float64) * radius


def make_mesh(n_lat=72, n_lon=144):
    vertices = [np.array([0.0, 0.0, 12.0])]
    for row in range(1, n_lat):
        theta = math.pi * row / n_lat
        for col in range(n_lon):
            phi = 2 * math.pi * col / n_lon
            vertices.append(point((math.sin(theta) * math.cos(phi),
                                   math.sin(theta) * math.sin(phi), math.cos(theta))))
    south = len(vertices)
    vertices.append(np.array([0.0, 0.0, -12.0]))
    # Correct the two pole locations to the same radial rule as all other vertices.
    vertices[0] = point((0.0, 0.0, 1.0))
    vertices[south] = point((0.0, 0.0, -1.0))
    triangles = []
    def idx(row, col):
        return 1 + (row - 1) * n_lon + col % n_lon
    for col in range(n_lon):
        triangles.append((0, idx(1, col), idx(1, col + 1)))
    for row in range(1, n_lat - 1):
        for col in range(n_lon):
            a, b = idx(row, col), idx(row, col + 1)
            c, d = idx(row + 1, col), idx(row + 1, col + 1)
            triangles.extend(((a, c, b), (b, c, d)))
    for col in range(n_lon):
        triangles.append((idx(n_lat - 1, col), south, idx(n_lat - 1, col + 1)))
    vertices = np.asarray(vertices)
    triangles = np.asarray(triangles, dtype=np.int32)
    # Orient every triangle away from the origin.
    a, b, c = vertices[triangles[:, 0]], vertices[triangles[:, 1]], vertices[triangles[:, 2]]
    normals = np.cross(b - a, c - a)
    flip = np.einsum("ij,ij->i", normals, (a + b + c) / 3) < 0
    triangles[flip, 1], triangles[flip, 2] = triangles[flip, 2].copy(), triangles[flip, 1].copy()
    return vertices, triangles


def main():
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite demo aircraft STL")
    vertices, triangles = make_mesh()
    with OUT.open("wb") as stream:
        stream.write(b"FlowForge illustrative smooth aircraft".ljust(80, b" "))
        stream.write(struct.pack("<I", len(triangles)))
        for i, j, k in triangles:
            a, b, c = vertices[[i, j, k]]
            normal = np.cross(b - a, c - a)
            normal /= np.linalg.norm(normal)
            stream.write(struct.pack("<12fH", *(normal.tolist() + a.tolist() + b.tolist() + c.tolist()), 0))
    print(json.dumps({"output": str(OUT), "triangles": len(triangles),
                      "bbox_min_mm": vertices.min(axis=0).tolist(),
                      "bbox_max_mm": vertices.max(axis=0).tolist()}, indent=2))


if __name__ == "__main__":
    main()
