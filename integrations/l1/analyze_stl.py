"""Measure topology of the ANSA-exported binary STL surface mesh."""

import json
import os
import struct

import numpy as np


ROOT = os.environ.get("ANSA_CRM_OUTPUT_DIR", os.getcwd())
STL = os.environ.get("ANSA_STL_SOURCE", os.path.join(ROOT, "crm_surface_mesh_candidate.stl"))
REPORT = os.environ.get("ANSA_STL_REPORT", os.path.join(ROOT, "stl_quality.json"))


def main():
    with open(STL, "rb") as stream:
        stream.seek(80)
        count = struct.unpack("<I", stream.read(4))[0]
    dtype = np.dtype([("normal", "<f4", (3,)),
                      ("vertices", "<f4", (3, 3)),
                      ("attribute", "<u2")])
    facets = np.memmap(STL, dtype=dtype, mode="r", offset=84, shape=(count,))
    raw_vertices = np.asarray(facets["vertices"]).reshape(-1, 3)
    vertices, inverse = np.unique(raw_vertices, axis=0, return_inverse=True)
    triangles = inverse.reshape(-1, 3)
    edges = np.sort(np.concatenate((triangles[:, (0, 1)],
                                    triangles[:, (1, 2)],
                                    triangles[:, (2, 0)]), axis=0), axis=1)
    unique_edges, multiplicity = np.unique(edges, axis=0, return_counts=True)
    boundary = unique_edges[multiplicity == 1]
    boundary_ys = vertices[boundary, 1]
    symmetry = np.all(np.abs(boundary_ys) < 0.01, axis=1)
    off_symmetry = boundary[~symmetry]
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for u, v in off_symmetry:
        u, v = int(u), int(v)
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[rv] = ru
    component_parent = list(range(len(vertices)))

    def component_find(node):
        while component_parent[node] != node:
            component_parent[node] = component_parent[component_parent[node]]
            node = component_parent[node]
        return node

    for u, v in unique_edges:
        u, v = int(u), int(v)
        root_u, root_v = component_find(u), component_find(v)
        if root_u != root_v:
            component_parent[root_v] = root_u
    connected_components = len({component_find(i) for i in range(len(vertices))})
    components = {}
    for u, v in off_symmetry:
        components.setdefault(find(int(u)), []).append((int(u), int(v)))
    off_symmetry_components = []
    for component_edges in components.values():
        ids = np.unique(np.asarray(component_edges).reshape(-1))
        pts = vertices[ids]
        e = np.asarray(component_edges)
        length = np.linalg.norm(vertices[e[:, 0]] - vertices[e[:, 1]], axis=1).sum()
        endpoint_ids, endpoint_degrees = np.unique(e.reshape(-1), return_counts=True)
        centered = pts.astype(np.float64) - pts.astype(np.float64).mean(axis=0)
        _, _, axes = np.linalg.svd(centered, full_matrices=False)
        signed_deviation = centered @ axes[-1]
        off_symmetry_components.append({
            "edge_count": len(component_edges),
            "vertex_count": len(ids),
            "closed_loop": bool(np.all(endpoint_degrees == 2)),
            "min_vertex_degree": int(endpoint_degrees.min()),
            "max_vertex_degree": int(endpoint_degrees.max()),
            "length_mm": float(length),
            "plane_rms_deviation_mm": float(np.sqrt(np.mean(signed_deviation ** 2))),
            "plane_max_deviation_mm": float(np.max(np.abs(signed_deviation))),
            "min_mm": pts.min(axis=0).astype(float).tolist(),
            "max_mm": pts.max(axis=0).astype(float).tolist(),
        })
    off_symmetry_components.sort(key=lambda item: item["edge_count"], reverse=True)
    a = raw_vertices[0::3].astype(np.float64)
    b = raw_vertices[1::3].astype(np.float64)
    c = raw_vertices[2::3].astype(np.float64)
    doubled_area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    center = (vertices.min(axis=0).astype(np.float64) + vertices.max(axis=0).astype(np.float64)) / 2.0
    radii = np.linalg.norm(vertices.astype(np.float64) - center, axis=1)
    report = {
        "stl": STL,
        "facets": int(count),
        "unique_vertices": int(len(vertices)),
        "unique_edges": int(len(unique_edges)),
        "connected_components": int(connected_components),
        "boundary_edges": int(len(boundary)),
        "boundary_edges_on_y_zero": int(np.count_nonzero(symmetry)),
        "boundary_edges_away_from_y_zero": int(np.count_nonzero(~symmetry)),
        "off_symmetry_components": off_symmetry_components,
        "nonmanifold_edges": int(np.count_nonzero(multiplicity > 2)),
        "degenerate_facets": int(np.count_nonzero(doubled_area < 1e-8)),
        "bounding_box_min_mm": vertices.min(axis=0).astype(float).tolist(),
        "bounding_box_max_mm": vertices.max(axis=0).astype(float).tolist(),
        "surface_area_mm2": float(doubled_area.sum() / 2.0),
        "radius_center_mm": center.tolist(),
        "radius_min_mm": float(radii.min()),
        "radius_mean_mm": float(radii.mean()),
        "radius_max_mm": float(radii.max()),
    }
    with open(REPORT, "w") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

