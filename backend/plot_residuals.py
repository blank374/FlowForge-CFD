"""Extract one pressure solve and continuity value per OpenFOAM time step."""

import csv
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main(log_path: Path, output_dir: Path) -> None:
    rows = []
    current = None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        time = re.match(r"Time = ([\d.eE+-]+)s?", line)
        if time:
            if current and "p_initial" in current and "continuity" in current:
                rows.append(current)
            current = {"time_s": float(time.group(1))}
            continue
        if current is None:
            continue
        pressure = re.search(r"Solving for p, Initial residual = ([\d.eE+-]+), Final residual = ([\d.eE+-]+)", line)
        if pressure and "p_initial" not in current:
            current["p_initial"] = float(pressure.group(1))
            current["p_final"] = float(pressure.group(2))
        continuity = re.search(r"time step continuity errors\s*:\s*sum local = [^,]+, global = ([\d.eE+-]+)", line)
        if continuity:
            current["continuity"] = abs(float(continuity.group(1)))
    if current and "p_initial" in current and "continuity" in current:
        rows.append(current)
    if not rows:
        raise ValueError("No pressure residual and continuity history found")
    with (output_dir / "residuals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("time_s", "p_initial", "p_final", "continuity"))
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=160)
    ax.semilogy([r["time_s"] for r in rows], [max(r["p_initial"], 1e-15) for r in rows], label="p initial residual")
    ax.semilogy([r["time_s"] for r in rows], [max(r["p_final"], 1e-15) for r in rows], label="p final residual")
    ax.semilogy([r["time_s"] for r in rows], [max(r["continuity"], 1e-15) for r in rows], label="|global continuity error|")
    ax.set(xlabel="Simulation time (s)", ylabel="Residual / continuity error", title="L1 sphere OpenFOAM solver history")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "residuals.png")
    plt.close(fig)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
