# Generic aircraft external CFD run (2026-10-14)

Input: approved workflow `2f7c72f876984d3788f6bf4e5b183c5f`, version 1,
`flowforge_wing_body_test.igs`. This run uses the generic path and does not invoke
the L1 sphere diameter gate. All paths below are under
`data/workflows/2f7c72f876984d3788f6bf4e5b183c5f/v1/`.

| Stage | Actual result | Evidence |
|---|---|---|
| ANSA geometry | Approved; 590 CAD faces, 1324 CONS, 0 free and 0 nonmanifold CONS | `geometry_report.json`, `review.ansa` |
| ANSA surface | 11,378 shell entities; 22,210 STL triangles; 12 mm target length; elapsed 1.66 s | `surface/report.json`, `surface/surface.ansa`, `surface/surface.stl`, `surface/ansa.log` |
| Independent STL check | 0 open edges, 0 nonmanifold edges, 0 degenerate triangles; bounds 1510 × 1360 × 170.94 mm | `surface/stl_quality.json` |
| Pointwise volume | 506,417 cells: 439,985 tetrahedra, 66,274 prisms, 158 pyramids; 0 negative/zero Jacobians; max equiangle skew 0.959 | `pointwise/pointwise.log`, `pointwise/aircraft_volume.pw`, `pointwise/aircraft_volume.cgns` |
| OpenFOAM mesh | AIRCRAFT_WALL 22,210 faces, FARFIELD 5,680 faces; one connected region; checkMesh `Mesh OK` after mm-to-m scaling | `pointwise/export.log`, `openfoam_case/constant/polyMesh/`, `openfoam_case/units.json`, `checkMesh.log` |
| OpenFOAM solve | **Failed numerical gate**. Test setup: 1 m/s, laminar, nu=1.5e-5 m²/s, 0° nominal incidence, 0.0001 s step. Stopped after 17 steps at 0.0017 s because maximum Courant number reached 203,932.7. No converged forces or validated CFD field. | `solver.log` |
| ParaView / report | Not run because the solve failed. | — |

The volume mesh has 1,473 faces above 70° non-orthogonality; `checkMesh` still
reports `Mesh OK`. The Pointwise log also warns about two high-aspect-ratio
boundary triangles. These warnings and the unstable solve require mesh/solver
review before any physical interpretation. The short laminar setup is a software
execution test, not a validated aircraft aerodynamics configuration.

New generic scripts and API routes cover ANSA surface generation, Pointwise
volume generation and OpenFOAM mesh checks. Solver case automation, numerical
stabilization, ParaView postprocessing, and report generation remain unfinished.
The existing L1 route is unchanged by these generic scripts. The L1 regression
was not rerun in this session.
