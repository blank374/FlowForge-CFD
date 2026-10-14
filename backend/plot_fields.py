"""Render 2D field images from ParaView-exported cell centers, with data gates."""
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as tri
import numpy as np


def render(csv_path: Path, output: Path, label: str) -> dict:
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        records = list(csv.DictReader(stream))
    if len(records) < 100:
        raise RuntimeError("ParaView exported too few field samples")
    x = np.array([float(row["Points:0"]) for row in records])
    y = np.array([float(row["Points:1"]) for row in records])
    ux = np.array([float(row["U:0"]) for row in records])
    uy = np.array([float(row["U:1"]) for row in records])
    uz = np.array([float(row["U:2"]) for row in records])
    speed = np.sqrt(ux * ux + uy * uy + uz * uz)
    pressure = np.array([float(row["p"]) for row in records])
    if not all(np.isfinite(a).all() for a in (x, y, speed, pressure)):
        raise RuntimeError("Nonfinite coordinate or field value")
    stats = {"samples": len(records), "x_range_m": [float(x.min()), float(x.max())],
             "y_range_m": [float(y.min()), float(y.max())],
             "U_magnitude_m_s": [float(speed.min()), float(speed.max())],
             "U_median_m_s": float(np.median(speed)),
             "U_p999_m_s": float(np.quantile(speed, .999)),
             "U_samples_above_0_15_m_s": int(np.count_nonzero(speed > .15)),
             "p": [float(pressure.min()), float(pressure.max())]}
    if np.ptp(speed) < 1e-7:
        raise RuntimeError("Velocity field has no resolvable variation")
    pressure_name = "Kinematic pressure" if label.startswith("L1 ") else "Pressure"
    pressure_unit = "m²/s²" if label.startswith("L1 ") else "Pa"
    for values, field, unit, filename in ((speed, "Speed magnitude", "m/s", "U.png"),
                                           (pressure, pressure_name, pressure_unit, "p.png")):
        fig, ax = plt.subplots(figsize=(11, 8), dpi=150, constrained_layout=True)
        # Scatter preserves the actual ParaView sample values and avoids interpolating
        # across an immersed body or disconnected CFD patches.
        sc = ax.scatter(x, y, c=values, s=9 if len(records) > 1000 else 100,
                        marker="s", cmap="turbo", linewidths=0, rasterized=True)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        ax.set_title(f"{label} · {field} · ParaView field samples")
        cb = fig.colorbar(sc, ax=ax, shrink=0.85)
        cb.set_label(unit)
        fig.savefig(output / filename, facecolor="white")
        plt.close(fig)
    return stats


if __name__ == "__main__":
    csv_path, output, label = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    stats = render(csv_path, output, label)
    (output / "field_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats))
