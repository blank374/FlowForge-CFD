"""Summarize the independent 1 s sphere validation and force monitor."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main(directory: Path) -> None:
    solver = (directory / "solver_long.log").read_text(encoding="utf-8", errors="replace")
    if "\nEnd\n" not in solver:
        raise RuntimeError("Extended solver has no normal completion marker")
    times = [float(x) for x in re.findall(r"(?m)^Time = ([0-9.eE+-]+)", solver)]
    p_residuals = [float(x) for x in re.findall(
        r"Solving for p, Initial residual = [0-9.eE+-]+, Final residual = ([0-9.eE+-]+)", solver)]
    courant = [float(x) for x in re.findall(r"Courant Number mean: [0-9.eE+-]+ max: ([0-9.eE+-]+)", solver)]
    continuity = [abs(float(x)) for x in re.findall(
        r"time step continuity errors\s*:\s*sum local = [^,]+, global = ([0-9.eE+-]+)", solver)]
    force_file = directory / "postProcessing" / "forceCoeffs" / "0.2" / "forceCoeffs.dat"
    force = [list(map(float, line.split())) for line in force_file.read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    cd = {round(row[0], 6): row[2] for row in force}
    fields = json.loads((directory / "field_stats.json").read_text(encoding="utf-8"))
    result = {
        "case": str(directory.resolve()), "source_run": "27e63b6565344386934a7540267a3492",
        "solver_exit": "normal", "final_time_s": times[-1], "additional_steps": len(times),
        "max_courant": max(courant), "last_10_p_final_residual_max": max(p_residuals[-10:]),
        "last_10_global_continuity_max": max(continuity[-10:]),
        "force_coefficients": {"Aref_m2": 3.141592653589793e-4, "Uinf_m_s": 0.075,
                               "rho_kg_m3": 1.225, "Cd_0_2": cd[0.2],
                               "Cd_0_8": cd[0.8], "Cd_1_0": cd[1.0],
                               "relative_Cd_change_0_8_to_1_0": abs(cd[1.0] - cd[0.8]) / cd[1.0]},
        "field_stats_at_1_s": fields,
        "numerical_test": "passed" if (abs(times[-1] - 1.0) < 1e-6 and max(courant) < 1
                                       and max(p_residuals[-10:]) < 1e-3
                                       and max(continuity[-10:]) < 1e-5
                                       and fields["U_magnitude_m_s"][1] < .15) else "failed",
        "engineering_acceptance": "not established: farfield-size and grid independence not tested",
    }
    (directory / "validation_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
