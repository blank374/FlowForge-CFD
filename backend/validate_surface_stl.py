"""Independent binary STL closure and bounds check for exported CFD surfaces."""
import collections
import json
import struct
import sys
from pathlib import Path


def inspect(path):
    edges = collections.Counter()
    low, high = [float("inf")] * 3, [float("-inf")] * 3
    degenerate = 0
    with Path(path).open("rb") as stream:
        stream.read(80)
        count = struct.unpack("<I", stream.read(4))[0]
        for _ in range(count):
            record = stream.read(50)
            if len(record) != 50:
                raise ValueError("Truncated binary STL")
            vertices = [struct.unpack_from("<3f", record, 12 + 12 * i) for i in range(3)]
            keys = [tuple(round(x, 4) for x in v) for v in vertices]
            degenerate += len(set(keys)) < 3
            for vertex in vertices:
                for axis, value in enumerate(vertex):
                    low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
            for a, b in ((0, 1), (1, 2), (2, 0)):
                edges[tuple(sorted((keys[a], keys[b])))] += 1
        if stream.read(1):
            raise ValueError("Binary STL contains trailing data")
    report = {"triangles": count, "bbox_min_mm": low, "bbox_max_mm": high,
              "degenerate_triangles": degenerate,
              "open_edges": sum(value == 1 for value in edges.values()),
              "nonmanifold_edges": sum(value > 2 for value in edges.values())}
    report["passed"] = (count >= 1000 and not any(report[key] for key in
                        ("degenerate_triangles", "open_edges", "nonmanifold_edges")))
    return report


if __name__ == "__main__":
    result = inspect(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
