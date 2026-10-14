"""Plot the OpenFOAM sphere drag coefficient from forceCoeffs.dat."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

source, output = Path(sys.argv[1]), Path(sys.argv[2])
rows = [list(map(float, line.split())) for line in source.read_text().splitlines()
        if line.strip() and not line.startswith("#")]
if len(rows) < 5:
    raise RuntimeError("Too few force-coefficient samples")
fig, ax = plt.subplots(figsize=(9, 5), dpi=150, constrained_layout=True)
ax.plot([row[0] for row in rows], [row[2] for row in rows], "o-", markersize=3)
ax.set(xlabel="Simulation time (s)", ylabel="Drag coefficient Cd",
       title="L1 sphere Re=100 · OpenFOAM forceCoeffs", xlim=(0.2, 1.0))
ax.grid(True, alpha=.3)
fig.savefig(output, facecolor="white")
