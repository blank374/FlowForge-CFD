# CRM-WB geometry gate (2026-10-13)

Target: uploaded `DPW4_wb_no_tail_v03.igs`, SHA-256 `e2b7ed29bc632e99ef95da87525f81f9943315a0c1e380cacf932737b6329a21`. This is the same source used in the 2026-10-12 seam assessment. The uploaded file was hash-checked before and after the new read-only ANSA diagnosis and did not change.

## Fresh checks in FlowForge-CFD

- Raw IGES import: 20 FACE, 76 CONS, source units inch. Its curves are not yet topologized; all 76 were free in the direct import. ANSA reported one CAD intersection region at this stage. Evidence: `data/crm_wb_uploaded_diagnosis.json`.
- Prepared **copy**: converted to millimeters, ran Topo and Orient, saved `data/crm_wb_prepared.ansa`; 20 FACE, 54 CONS, 15 red CONS after preparation. The uploaded IGES was not overwritten. Evidence: `data/crm_wb_prepared.json`.
- Local seams on that copy: FACE 2/7, CONS 7/89 have coincident endpoints but a maximum sampled curve separation of 26.98 mm and one CAD intersection region. FACE 7/8, CONS 22/27 have a maximum endpoint separation of 83.84 mm and one CAD intersection region. Evidence: `data/crm_wb_local_seams.json`.

The prior 10 mm surface-mesh assessment on this same source found 381 off-symmetry open edges, 12 ANSA mesh-intersection regions and 164 Pointwise intersected facets. Its default SmartPaste candidate did not change the topology or mesh. See `F:/Auto/automation/diagnostics/20261012-local-seams/README.md`.

## Decision

**BLOCKED_GEOMETRY**: the prepared copy is a diagnostic candidate, not an accepted repaired CAD. Do not generate a volume mesh or run OpenFOAM from it. A successful browser preview is only a visualization check.

To pass this gate, make a local CAD retrim/connection on a further copy, preserve the intended outer mold line, and then verify shared boundary topology, no unintended free edges or intersections, unchanged intended shape, a clean surface mesh, independent Pointwise readback and a valid volume mesh. The two seam plots in the legacy diagnostic directory identify the locations, but do not establish which trim boundary is the design authority.

## Alternative uploaded aircraft check

The uploaded `DPW4_wbt_ihp0_v03.igs` was also prepared on a copy and meshed at a 10 mm target size. Its surface has 226,963 facets, 381 off-symmetry open edges and 258 nonmanifold edges (`data/crm_wbt_surface_quality.json`). This is not an accepted substitute for the WB model or a solver-ready surface.
