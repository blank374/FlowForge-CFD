# FlowForge CFD V0.1

The main page now uses one versioned workflow view for file input, ANSA, Pointwise, OpenFOAM, ParaView and report. The **L1 20 mm IGES sphere** is the verified full automatic profile. General CAD enters the ANSA inspection/manual handoff path and stays blocked before unverified meshing or physics stages. See [unified workflow and acceptance evidence](docs/unified_workflow.md).

The human handoff opens a versioned working copy directly in the local ANSA GUI. Save changes to the path shown on the page and click **提交本机修复并复检** to create a new version and rerun inspection. Download/upload remains available for another computer or a different save path. Automatic inspection does not Topo or repair geometry. Later Pointwise/OpenFOAM stages stay blocked until implemented and verified. See [unified workflow and acceptance evidence](docs/unified_workflow.md).

The existing L1 run detail now shows ANSA, Pointwise, OpenFOAM, ParaView and report stages from saved logs and artifacts. This is the only currently verified automatic import-to-report profile. A general CAD workflow still needs validated surface/volume mesh templates, boundary mappings and physical inputs before it can continue beyond the ANSA handoff.

Local CFD workbench at `F:\Auto\FlowForge-CFD`. The old `F:\Auto\automation` project is not needed at runtime.

## Start

```powershell
cd F:\Auto\FlowForge-CFD
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
pwsh -NoProfile -File .\start.ps1
```

Open `http://127.0.0.1:8123/` (API docs at `/docs`). The service needs Windows permission to invoke WSL. `FLOWFORGE_WSL_DISTRO` overrides `Ubuntu-F2`; adjust `config.json` for local executable paths.

**运行内置 L1 球体** runs the built-in `.ansa` sphere. Upload and select a 20 mm sphere `.igs`/`.iges` file, then click **运行选中 IGES 球体** to send that actual CAD file through ANSA, Pointwise, OpenFOAM Foundation 13, ParaView field extraction, image plotting and report generation. Each task snapshots its source file and records mm→m conversion, mesh/solver logs, a residual chart, U/p plots, ParaView states, and an OpenFOAM case archive. Pointwise now exports the farfield patch natively for the L1 sphere. **运行 OpenFOAM cavity** runs the official tutorial as a separate integration example.

Uploaded STL/OBJ and CAD files can be previewed in 3D. The IGES-to-CFD workflow is intentionally limited to the 20 mm L1 sphere; other shapes fail its geometry gate. A running task has a **取消任务** button and `POST /api/runs/{id}/cancel` endpoint. Production batch control and general CAD boundary classification are not implemented.

See [implementation status](docs/implementation_status.md) for PASS/FAIL/BLOCKED/NOT_TESTED, verified run IDs, reproduction steps and limitations. Generated run data is excluded from Git.

For the separate CRM mesh, see [the script and manual review workflow](docs/human_in_the_loop_cfd.md). Its current OpenFOAM mesh checks fail, so the CRM solver stage is blocked pending mesh review and repair.
