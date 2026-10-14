# FlowForge CFD implementation status — 2026-10-13

Scope: a **20 mm IGES sphere** generated from the ANSA L1 fixture. The workflow actually runs Windows ANSA 20.1.6 → Windows Pointwise 2024.1 → WSL OpenFOAM Foundation 13 → WSL ParaView 6.0.1. Other shapes are rejected by the sphere geometry gate. The current result is an integration and numerical test, not production CFD validation.

## Main evidence

- Uploaded source: `data/test_sphere_20mm.igs`, generated with `integrations/l1/generate_test_iges.py`; browser upload ID `d512ececdf9748d4b2f81d8ff40e0c0a` in project `04d9ec57b43448b6b8714e9e2695e230` (Acceptance).
- **PASS — fresh web full run:** `data/runs/27e63b6565344386934a7540267a3492/`, database status `success`. `input.json` stores the uploaded file ID and SHA-256; `source_model.igs` is a per-run copy. `result.json` and logs show 75,415 cells, 2,506 wall faces, 3,940 farfield faces, `checkMesh` OK, 400 solver steps to 0.2 s, and real U/p fields.
- **PASS — native Pointwise patch:** `pointwise_l1.glf` assigns six farfield block-face registers to `L1_FARFIELD` before `.pw` save. `export_l1_openfoam.glf` verifies this after reload. `units.json` records `pointwise_l1_repair=false`; patch face counts remain unchanged through mm→m conversion. The old guarded text repair is limited to the exact known L1 sphere signature; unknown patch sets fail.
- **PASS — longer numerical check:** `data/physics_long_iges_20261013/` is an independent copy continued from the accepted 0.2 s case to 1.0 s (1,600 additional steps). `validation_summary.json`: normal solver exit, max Courant 0.5664, last ten pressure final residuals ≤1.56e-6, continuity ≤4.08e-12. OpenFOAM `forceCoeffs` gives Cd 1.5226 at 0.2 s, 1.4002 at 0.8 s, and 1.3888 at 1.0 s (0.82% change over the final 0.2 s). At 1.0 s, ParaView sampled 4,882 cells with U max 0.08806 m/s and no samples above 0.15 m/s. See `Cd.png`, `U.png`, `p.png`, `forceCoeffs.log`, and `postProcessing/forceCoeffs/0.2/forceCoeffs.dat`.
- **PASS — browser results and CAD preview:** Acceptance page displayed the uploaded IGES as a 3D sphere, the successful run parameters, residual chart, and U/p images. The PNGs are in the run folder. An earlier built-in run has `web_acceptance.png` at `data/runs/f97d6ea510f84d8a864b97ecb4e43d25/`.
- **PASS — failure isolation:** Invalid IGES run `1c41dd4534494b99bd53310453ad4a9d` failed at ANSA import (`imported_face_count=0`) with no `result.json`; accepted run remained `success`.
- **PASS — meshing-stage cancellation:** run `5fb6e6f8e908407a9c8b72ca2880d8b4` was cancelled via `POST /api/runs/{id}/cancel`, reached `cancelled`, and did not advance to OpenFOAM. Repeated cancellation returned HTTP 409.
- **PASS — solver-stage cancellation:** run `9ed2f8cedc2b45818b4f0e9b5bb890bf` was cancelled while OpenFOAM was at 0.175 s. It reached `cancelled`; WSL process lookup found no run-specific solver; its log stopped at 0.176 s with no `End`, and no `result.json` or U/p images were created.
- **PASS — browser cancel control:** clicking **运行选中 IGES 球体** then **取消任务** created run `ba16866b02d34919a6d1f8110c78ee78`; the page showed `cancelling` then `cancelled` and the process log recorded `CANCELLED`.

## Acceptance matrix

| Item | Status | Evidence / limit |
|---|---|---|
| Generated sphere IGES → ANSA surface | PASS | `source_model.igs`, `ansa_mesh.json`, `ansa_surface_quality.json`; imported IGES uses millimetres, topology joined, perimeter spacing applied, sphere geometry gate passed. |
| Pointwise volume mesh and native farfield export | PASS | 75,415 cells, 65,391 tets + 10,024 prisms, zero negative Jacobians; native `L1_FARFIELD` and `L1_WALL` in exported boundary. |
| Unit conversion | PASS | `units.json`: source mm, target m, scale 0.001 once; outer bbox roughly ±50 mm → ±0.05 m; cell and patch counts unchanged. Repeat scaling is refused by a marker. |
| Physical test setup | PASS for L1 test | Re=100, U∞=0.075 m/s, ν=1.5e-5 m²/s, D=.02 m, no-slip sphere, `freestreamVelocity`/`freestreamPressure` spherical outer boundary. Foundation 13 parsed the templates. |
| OpenFOAM execution and fields | PASS for 0.2 s / 1.0 s tests | Normal exit and numerical gates passed; final U/p fields and logs retained. Solver exit, numerical checks, and engineering acceptance are separate conclusions. |
| ParaView data and visual artifacts | PASS | ParaView 6.0.1 OpenFOAMReader extracted real U/p at 0.2 s and 1.0 s; `.pvsm` states, CSV, manifest, nonblank U/p plots retained. |
| Native headless ParaView screenshots | FAIL | WSL OpenGL screenshot remains black/sawtooth; images are Matplotlib plots of ParaView-extracted field samples. |
| Web full run / file preview / result display | PASS for test sphere | Fresh web ID `27e63…`; uploaded IGES preview and result images observed in browser. |
| Error isolation | PASS for invalid CAD | Invalid IGES fails at ANSA; prior success remains intact. Concurrent worker isolation was not tested. |
| Task cancellation | PASS for meshing, solver, and browser control | Backend tracks subprocess trees and exposes cancel endpoint/UI. See runs `5fb6…`, `9ed2…`, and `ba168…`; WSL solver process stopped. Restart recovery of a cancelled task was not tested. |
| Engineering validation / arbitrary CAD | BLOCKED | No grid-independence or farfield-radius study, experimental comparison, or arbitrary-model boundary classification. Cd still drifts 0.82% from 0.8 to 1.0 s. Other IGES geometries intentionally fail the L1 sphere gate. |
| CRM `.ansa` mesh and production batch | BLOCKED / NOT_TESTED | `CRM_cfx5_mesh.ansa` passed read-only ANSA inventory, Pointwise import, and OpenFOAM conversion. Default `checkMesh` failed 1 check; full check failed 6. No CRM solve or field render was run. Production batch remains NOT_TESTED. See `docs/human_in_the_loop_cfd.md`. |

## Reproduce

From PowerShell in `F:\Auto\FlowForge-CFD`:

```powershell
npm --prefix frontend run build
pwsh -NoProfile -File .\start.ps1
$body = @{kind='l1_full';file_id='d512ececdf9748d4b2f81d8ff40e0c0a'} | ConvertTo-Json
$new = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8123/api/projects/04d9ec57b43448b6b8714e9e2695e230/runs' -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://127.0.0.1:8123/api/runs/$($new.id)"
# For a running task only:
Invoke-RestMethod -Method Post "http://127.0.0.1:8123/api/runs/$($new.id)/cancel"
```

The service must run in a Windows context allowed to invoke WSL. Open `data/runs/<id>/openfoam_case/case.foam` or the corresponding `L1_U.pvsm` / `L1_p.pvsm` in ParaView. For the independent 1 s validation, copy the accepted OpenFOAM case, set `startFrom latestTime`, `endTime 1.0`, `writeInterval 100` in `system/controlDict`, run `foamRun`, then use `backend/analyze_long_validation.py` and `backend/plot_forces.py` on the saved outputs.
