# Legacy integration audit — 2026-10-12

Inspected `F:\Auto\automation` read only. Its working tree contained preexisting modifications and untracked files. No legacy file was copied into or modified for this implementation.

`automation/platform/server.py` has FastAPI, SQLite, background runs, SSE and profile restricted Python/command nodes. It hard codes old ANSA and Pointwise locations and contains CRM and CFX specific nodes, so it is not used by the new standalone service.

`automation/platform/legacy_l1/runs/L1/20261012-153544-d2d19606/run_summary.json` records a test sphere ANSA surface mesh and Pointwise 47,543 cell volume mesh with zero negative Jacobians and CGNS readback. The same directory contains a later Pointwise OpenFOAM `polyMesh` export. This demonstrates an existing mesh artifact, not a validated CFD solve. The L1 scripts require review of their inputs and license behavior before migration.

`automation/openfoam/export_l1_openfoam.glf` selects Pointwise's `OpenFOAM 3` exporter and exports a loaded `.pw` block. Migrated copies now run independently in `integrations/l1`. A fresh API run found that the reloaded project exports the farfield as `Unspecified`; the L1-only repair and `checkMesh` passed, but solver units and physics remain open. The CRM pipeline remains blocked by self intersections and open edges according to `automation/PROJECT_STATUS.md`; it must not be used as a valid CFD case.

Reusable concepts: quality gates, per run directories, Pointwise Glyph batch execution and L1 test fixture. L1 mesh integration status: **PASS through OpenFOAM checkMesh**. L1 CFD solution: **NOT_TESTED**.
