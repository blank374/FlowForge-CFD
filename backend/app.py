from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA = Path(os.getenv("FLOWFORGE_DATA_DIR", str(ROOT / "data")))
DATA.mkdir(exist_ok=True)
DB = DATA / "flowforge.sqlite3"
WSL_DISTRO = os.getenv("FLOWFORGE_WSL_DISTRO", "Ubuntu-F2")
FOAM_BASHRC = "/opt/openfoam13/etc/bashrc"
app = FastAPI(title="FlowForge CFD", version="0.1.0")
preview_lock = threading.Lock()
preview_jobs: set[str] = set()
run_lock = threading.Lock()
run_cancel: dict[str, threading.Event] = {}
run_processes: dict[str, subprocess.Popen] = {}


class RunCancelled(Exception):
    pass


def run_process(rid: str, command: list[str], out, timeout: int, **kwargs):
    """Track each external stage so a run can stop its Windows child tree."""
    with run_lock:
        event = run_cancel[rid]
        if event.is_set():
            raise RunCancelled("Task cancelled before stage start")
        process = subprocess.Popen(command, stdout=out, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), **kwargs)
        run_processes[rid] = process
    try:
        code = process.wait(timeout=timeout)
        if event.is_set():
            raise RunCancelled("Task cancelled")
        return code
    except subprocess.TimeoutExpired:
        stop_process_tree(process)
        raise
    finally:
        with run_lock:
            if run_processes.get(rid) is process:
                run_processes.pop(rid, None)


def stop_process_tree(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def connection():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    return db


with connection() as db:
    db.executescript("""CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,name TEXT NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,error TEXT);""")
    db.execute("UPDATE runs SET status='interrupted',error='Backend restarted during run' WHERE status='running'")


def now():
    return datetime.now(timezone.utc).isoformat()


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive != CONFIG["wsl_mount_drive"].lower():
        raise ValueError("Project drive does not match verified WSL mount")
    return "/mnt/f/" + resolved.relative_to(resolved.anchor).as_posix()


def rows(sql, params=()):
    with connection() as db:
        return [dict(x) for x in db.execute(sql, params)]


class ProjectIn(BaseModel):
    name: str


class RunIn(BaseModel):
    kind: str = "python_validation"
    file_id: str | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "api_revision": "workflow-v1-handoff", "environment": environment()}


def environment():
    ansa = Path(CONFIG["ansa_executable"])
    pointwise = Path(CONFIG["pointwise_glyph_executable"])
    return {"ansa": ansa.is_file(), "pointwise": pointwise.is_file(), "wsl": shutil.which("wsl.exe") is not None,
            "openfoam": "OpenFOAM-13 / Ubuntu-F2 (detected; workflow verification separate)",
            "paraview": "6.0.1 / Ubuntu-F2 (detected; workflow verification separate)"}


@app.get("/api/projects")
def projects():
    return rows("SELECT * FROM projects ORDER BY created DESC")


@app.post("/api/projects")
def create_project(body: ProjectIn):
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(400, "Project name must be 1–100 characters")
    pid = uuid.uuid4().hex
    with connection() as db:
        db.execute("INSERT INTO projects VALUES(?,?,?)", (pid, name, now()))
    return {"id": pid, "name": name}


@app.get("/api/projects/{pid}/files")
def project_files(pid: str):
    return rows("SELECT id,name,size,created FROM files WHERE project_id=? ORDER BY created DESC", (pid,))


@app.post("/api/projects/{pid}/files")
async def upload(pid: str, file: UploadFile = File(...)):
    if not rows("SELECT id FROM projects WHERE id=?", (pid,)):
        raise HTTPException(404, "Project not found")
    name = Path(file.filename or "model").name
    if Path(name).suffix.lower() not in {".stl", ".obj", ".step", ".stp", ".iges", ".igs", ".ansa", ".pw", ".cgns"}:
        raise HTTPException(400, "Unsupported model format")
    fid = uuid.uuid4().hex
    dest = DATA / "uploads" / pid / f"{fid}{Path(name).suffix.lower()}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            limit = 1024 * 1024 * 1024 if Path(name).suffix.lower() in {".ansa", ".pw", ".cgns"} else 250 * 1024 * 1024
            if size > limit:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {limit // (1024 * 1024)} MB")
            out.write(chunk)
    with connection() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?,?,?)", (fid, pid, name, str(dest), size, now()))
    return {"id": fid, "name": name, "size": size}


@app.get("/api/files/{fid}")
def download(fid: str):
    found = rows("SELECT * FROM files WHERE id=?", (fid,))
    if not found:
        raise HTTPException(404, "File not found")
    return FileResponse(found[0]["path"], filename=found[0]["name"])


@app.get("/api/files/{fid}/inspect")
def inspect_uploaded_file(fid: str):
    found = rows("SELECT * FROM files WHERE id=?", (fid,))
    if not found:
        raise HTTPException(404, "File not found")
    entry = found[0]
    path = Path(entry["path"])
    if not path.is_file() or path.stat().st_size != entry["size"] or not entry["size"]:
        return {"status": "INVALID", "reason": "Uploaded file is missing, empty, or changed"}
    with path.open("rb") as stream:
        header = stream.read(4096)
    suffix = Path(entry["name"]).suffix.lower()
    signature = "unknown"
    if header.startswith(b"\x89HDF\r\n\x1a\n") or b"ADF Database" in header[:128]:
        signature = "cgns_candidate"
    elif b"ISO-10303-21" in header[:256]:
        signature = "step"
    elif suffix in {".igs", ".iges"} and len(header) >= 80 and header[72:73] in {b"S", b"G", b"D"}:
        signature = "iges_candidate"
    elif suffix == ".ansa":
        signature = "ansa_candidate"
    elif suffix == ".pw":
        signature = "pointwise_candidate"
    kind = "CAD" if suffix in {".igs", ".iges", ".step", ".stp"} else ("MESH_OR_PROJECT" if suffix in {".ansa", ".pw", ".cgns"} else "SURFACE")
    mismatch = suffix in {".step", ".stp"} and signature != "step"
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return {"status": "MISMATCH" if mismatch else "IDENTIFIED", "name": entry["name"],
            "size": entry["size"], "sha256": digest.hexdigest(),
            "kind": kind, "signature": signature,
            "start_stage": "ANSA_GEOMETRY" if kind == "CAD" else "NATIVE_CONTENT_CHECK",
            "volume_mesh_verified": False,
            "note": "File signature is not a volume-mesh quality check; native import and topology checks are required."}


def build_cad_preview(fid: str, source: Path, output: Path) -> None:
    report = output.with_suffix(".json")
    log = output.with_suffix(".log")
    env = os.environ.copy()
    env.update(FLOWFORGE_PREVIEW_SOURCE=str(source), FLOWFORGE_PREVIEW_STL=str(output),
               FLOWFORGE_PREVIEW_REPORT=str(report))
    script = (ROOT / "backend" / "cad_preview.py").as_posix()
    try:
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run([CONFIG["ansa_executable"], "-exec", f"load_script: '{script}'",
                                        "-exec", "main()", "-nogui"], env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, timeout=600)
        result = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        if completed.returncode or result.get("status") != "ok":
            output.unlink(missing_ok=True)
            report.write_text(json.dumps({"status": "error", "error": result.get("error", "ANSA preview conversion failed; see preview log")}), encoding="utf-8")
    except Exception as exc:
        output.unlink(missing_ok=True)
        report.write_text(json.dumps({"status": "error", "error": str(exc)}), encoding="utf-8")
    finally:
        with preview_lock:
            preview_jobs.discard(fid)


@app.get("/api/files/{fid}/preview")
def cad_preview_status(fid: str):
    found = rows("SELECT * FROM files WHERE id=?", (fid,))
    if not found:
        raise HTTPException(404, "File not found")
    source = Path(found[0]["path"])
    suffix = source.suffix.lower()
    if suffix in {".stl", ".obj"}:
        return {"status": "ready", "url": f"/api/files/{fid}"}
    if suffix == ".ansa":
        return {"status": "error", "error": "ANSA project preview is unavailable; download and inspect in ANSA GUI"}
    if suffix not in {".igs", ".iges", ".step", ".stp"}:
        raise HTTPException(400, "Unsupported preview format")
    output = DATA / "previews" / f"{fid}.stl"
    report = output.with_suffix(".json")
    if output.is_file():
        return {"status": "ready", "url": f"/api/files/{fid}/preview.stl"}
    with preview_lock:
        if fid in preview_jobs:
            return {"status": "processing"}
        if report.is_file():
            result = json.loads(report.read_text(encoding="utf-8"))
            if result.get("status") == "error":
                return {"status": "error", "error": result.get("error", "Preview conversion failed")}
        if not Path(CONFIG["ansa_executable"]).is_file():
            return {"status": "error", "error": "ANSA executable is unavailable"}
        output.parent.mkdir(parents=True, exist_ok=True)
        preview_jobs.add(fid)
    threading.Thread(target=build_cad_preview, args=(fid, source, output), daemon=True).start()
    return {"status": "processing"}


@app.get("/api/files/{fid}/preview.stl")
def cad_preview_file(fid: str):
    if not rows("SELECT id FROM files WHERE id=?", (fid,)):
        raise HTTPException(404, "File not found")
    output = DATA / "previews" / f"{fid}.stl"
    if not output.is_file():
        raise HTTPException(404, "Preview not ready")
    return FileResponse(output, media_type="model/stl")


@app.get("/api/projects/{pid}/runs")
def project_runs(pid: str):
    return rows("SELECT * FROM runs WHERE project_id=? ORDER BY created DESC", (pid,))


@app.post("/api/projects/{pid}/runs")
def create_run(pid: str, body: RunIn):
    if not rows("SELECT id FROM projects WHERE id=?", (pid,)):
        raise HTTPException(404, "Project not found")
    if body.kind not in {"python_validation", "foam_cavity", "l1_mesh", "l1_full"}:
        raise HTTPException(400, "Unsupported run kind")
    source = None
    if body.file_id:
        if body.kind not in {"l1_mesh", "l1_full"}:
            raise HTTPException(400, "Uploaded CAD is supported only by L1 sphere tasks")
        found = rows("SELECT * FROM files WHERE id=? AND project_id=?", (body.file_id, pid))
        if not found or Path(found[0]["name"]).suffix.lower() not in {".igs", ".iges"}:
            raise HTTPException(400, "Select an IGES file from this project")
        source = found[0]
    rid = uuid.uuid4().hex
    if source:
        directory = DATA / "runs" / rid
        directory.mkdir(parents=True)
        model = directory / ("source_model" + Path(source["name"]).suffix.lower())
        shutil.copy2(source["path"], model)
        (directory / "input.json").write_text(json.dumps({"file_id": source["id"], "name": source["name"],
            "sha256": hashlib.sha256(model.read_bytes()).hexdigest(), "path": str(model)}, indent=2), encoding="utf-8")
    with connection() as db:
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (rid, pid, body.kind, "running", now(), now(), None))
    with run_lock:
        run_cancel[rid] = threading.Event()
    threading.Thread(target=execute, args=(rid, body.kind), daemon=True).start()
    return {"id": rid, "status": "running"}


@app.post("/api/runs/{rid}/cancel")
def cancel_run(rid: str):
    with run_lock:
        event = run_cancel.get(rid)
        if event is None:
            raise HTTPException(409, "Run is not active")
        event.set()
        process = run_processes.get(rid)
        with connection() as db:
            db.execute("UPDATE runs SET status='cancelling',updated=? WHERE id=? AND status='running'", (now(), rid))
    if process is not None:
        stop_process_tree(process)
    return {"id": rid, "status": "cancelling"}


def execute(rid: str, kind: str):
    directory = DATA / "runs" / rid
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "process.log"
    status, error = "success", None
    try:
        if kind == "python_validation":
            result = {"run_id": rid, "input": "built-in validation", "result": "passed", "timestamp": now()}
            (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            log.write_text("Python validation completed successfully\n", encoding="utf-8")
        elif kind == "l1_mesh":
            run_l1(rid, directory, log, solve=False, cad_input=next(directory.glob("source_model.ig*"), None))
            status = "needs_review"
        elif kind == "l1_full":
            run_l1(rid, directory, log, solve=True, cad_input=next(directory.glob("source_model.ig*"), None))
            status = "success"
        else:
            # Fixed, operator-controlled tutorial only. No user input enters the shell script.
            linux_dir = wsl_path(directory)
            script = f"set -e; source {FOAM_BASHRC}; cp -a /opt/openfoam13/tutorials/fluid/cavity/. '{linux_dir}/'; cd '{linux_dir}'; blockMesh; checkMesh; foamRun; pvbatch '{wsl_path(ROOT / 'backend' / 'paraview_cavity.py')}' '{linux_dir}' '{linux_dir}'; python3 '{wsl_path(ROOT / 'backend' / 'plot_fields.py')}' '{linux_dir}/cavity_centers.csv' '{linux_dir}' 'OpenFOAM 13 cavity, t=1 s'"
            with log.open("w", encoding="utf-8") as out:
                code = run_process(rid, ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script], out, 300)
            if code:
                raise RuntimeError(f"OpenFOAM exited {code}; inspect process.log")
            if not (directory / "constant" / "polyMesh" / "boundary").is_file():
                raise RuntimeError("Missing OpenFOAM mesh boundary")
            output = log.read_text(encoding="utf-8", errors="replace")
            if "Mesh OK." not in output or "\nEnd\n" not in output:
                raise RuntimeError("Mesh or solver completion marker missing")
            if not (directory / "cavity_centers.csv").is_file() or not (directory / "U.png").is_file():
                raise RuntimeError("ParaView output missing")
            stats = json.loads((directory / "field_stats.json").read_text(encoding="utf-8"))
            (directory / "result.json").write_text(json.dumps({"run_id": rid, "solver": "OpenFOAM-13 foamRun", "paraview": "6.0.1", "exit_code": 0, "mesh_check": "passed", "solver_completion": "passed", "velocity_field_range_m_s": stats["U_magnitude_m_s"], "visual_quality": "passed: ParaView field samples plotted", "engineering_validation": "tutorial integration only"}, indent=2), encoding="utf-8")
        with run_lock:
            if run_cancel[rid].is_set():
                raise RunCancelled("Task cancelled")
    except RunCancelled as exc:
        status, error = "cancelled", str(exc)
        with log.open("a", encoding="utf-8") as out:
            out.write(f"\nCANCELLED: {error}\n")
    except Exception as exc:
        status, error = "failed", str(exc)
        with log.open("a", encoding="utf-8") as out:
            out.write(f"\nERROR: {error}\n")
    with run_lock:
        if run_cancel[rid].is_set() and status != "cancelled":
            status, error = "cancelled", "Task cancelled"
        with connection() as db:
            db.execute("UPDATE runs SET status=?,updated=?,error=? WHERE id=?", (status, now(), error, rid))
        run_cancel.pop(rid, None)
        run_processes.pop(rid, None)


def run_l1(rid: str, directory: Path, log: Path, solve: bool, cad_input: Path | None = None) -> None:
    """Run the gated 20 mm L1 sphere chain; reject other uploaded IGES shapes."""
    integration = ROOT / "integrations" / "l1"
    command = ["pwsh", "-NoProfile", "-File", str(integration / "run-l1.ps1"),
               "-AnsaBat", CONFIG["ansa_executable"], "-PointwiseTcl", CONFIG["pointwise_glyph_executable"],
               "-Python", str(ROOT / ".venv" / "Scripts" / "python.exe"), "-RunDir", str(directory)]
    if cad_input:
        command.extend(["-CadInput", str(cad_input)])
    with log.open("w", encoding="utf-8") as out:
        code = run_process(rid, command, out, 600)
    summary_path = directory / "run_summary.json"
    if code or not summary_path.is_file():
        if summary_path.is_file():
            failed_summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
            if failed_summary.get("error"):
                raise RuntimeError(str(failed_summary["error"]) + " See run_summary.json")
        raise RuntimeError(f"ANSA/Pointwise run failed ({code}); inspect process.log")
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if summary.get("status") != "passed" or not summary.get("geometry", {}).get("sphere_gate") or summary.get("volume_quality", {}).get("volume_cells", 0) < 100:
        raise RuntimeError("L1 mesh quality gate failed; inspect run_summary.json")
    export = directory / "openfoam_export"
    with (directory / "openfoam_export.log").open("w", encoding="utf-8") as out:
        code = run_process(rid, [CONFIG["pointwise_glyph_executable"], str(integration / "export_l1_openfoam.glf"),
                                 str(directory / "l1_pointwise_volume.pw"), str(export)],
                                out, 120)
    if code or not all((export / name).is_file() for name in ("boundary", "faces", "owner", "neighbour", "points")):
        raise RuntimeError("Pointwise OpenFOAM export failed")
    boundary = (export / "boundary").read_text(encoding="utf-8", errors="replace")
    patches = {name: int(count) for name, count in re.findall(r"(L1_\w+|Unspecified)\s*\{[^}]*nFaces\s+(\d+)", boundary)}
    original_patches = dict(patches)
    repaired = False
    if set(patches) == {"L1_WALL", "Unspecified"} and len(patches) == 2 and patches["Unspecified"] > 0 and summary["geometry"]["sphere_gate"] and summary["surface_quality"]["farfield_boundary_domains"] == 6:
        # Fallback for older L1 projects made before the Pointwise register fix.
        # The sphere gate and exactly six non-wall domains constrain its scope.
        boundary = re.sub(r"(?m)^([ \t]*)Unspecified([ \t]*)$", r"\1L1_FARFIELD\2", boundary, count=1)
        boundary = re.sub(r"(L1_FARFIELD\s*\{[^}]*?type\s+)Unspecified(\s*;)", r"\1patch\2", boundary, count=1)
        (export / "boundary").write_text(boundary, encoding="utf-8")
        patches["L1_FARFIELD"] = patches.pop("Unspecified")
        repaired = True
    if set(patches) != {"L1_WALL", "L1_FARFIELD"} or min(patches.values()) <= 0:
        raise RuntimeError(f"Boundary patch gate failed: {patches}")
    if not re.search(r"L1_FARFIELD\s*\{[^}]*type\s+patch\s*;", boundary):
        raise RuntimeError("Farfield OpenFOAM patch type is invalid")
    case = directory / "openfoam_case"
    mesh = case / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    shutil.copytree(export, mesh, dirs_exist_ok=True)
    template = integration / "foam_template"
    for relative in ("0/U", "0/p", "constant/momentumTransport", "constant/physicalProperties",
                     "system/controlDict", "system/fvSchemes", "system/fvSolution"):
        target = case / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template / relative, target)
    linux_case = wsl_path(case)
    def wsl_run(script: str, name: str, timeout: int) -> str:
        path = directory / name
        with path.open("w", encoding="utf-8") as out:
            code = run_process(rid, ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc",
                                        f"set -e; source {FOAM_BASHRC}; {script}"],
                                       out, timeout)
        value = path.read_text(encoding="utf-8", errors="replace")
        if code:
            raise RuntimeError(f"{name} failed ({code}); inspect log")
        return value
    def mesh_metrics(value: str) -> tuple[int, list[float]]:
        count = re.search(r"(?m)^\s*cells:\s+(\d+)", value)
        bounds = re.search(r"Overall domain bounding box\s*\(([^)]+)\)\s*\(([^)]+)\)", value)
        if "Mesh OK." not in value or not count or not bounds:
            raise RuntimeError("OpenFOAM mesh quality or bounds gate failed")
        return int(count.group(1)), [float(x) for part in bounds.groups() for x in part.split()]
    before_count, before_box = mesh_metrics(wsl_run(f"checkMesh -case '{linux_case}'", "checkMesh_mm.log", 120))
    marker = directory / "units.json"
    if marker.exists():
        raise RuntimeError("Refusing to scale an already scaled mesh")
    wsl_run(f"transformPoints -case '{linux_case}' 'scale=(0.001 0.001 0.001)'", "transformPoints.log", 120)
    after_count, after_box = mesh_metrics(wsl_run(f"checkMesh -case '{linux_case}'", "checkMesh.log", 120))
    cells = summary["volume_quality"]["volume_cells"]
    if before_count != cells or after_count != cells or not all(abs(a - b * .001) < 2e-6 for a, b in zip(after_box, before_box)):
        raise RuntimeError("SI conversion changed cell count or bounds unexpectedly")
    if not (0.095 < after_box[3] - after_box[0] < 0.105):
        raise RuntimeError("L1 farfield dimension after conversion is implausible")
    if hashlib.sha256((mesh / "boundary").read_bytes()).hexdigest() != hashlib.sha256((export / "boundary").read_bytes()).hexdigest():
        raise RuntimeError("Patch definitions changed during unit conversion")
    marker.write_text(json.dumps({"source_unit": "mm", "target_unit": "m", "scale": .001,
                                  "before_bbox_mm": before_box, "after_bbox_m": after_box,
                                  "cells_before": before_count, "cells_after": after_count,
                                  "patch_faces_before": original_patches, "patch_faces_after": patches,
                                  "pointwise_l1_repair": repaired}, indent=2), encoding="utf-8")
    result_data = {"pipeline": "ANSA → Pointwise → OpenFOAM", "input_model": str(cad_input) if cad_input else "built-in L1 sphere .ansa",
                   "cells": cells, "patch_faces": patches, "mesh_units": "m", "pointwise_farfield_repair": repaired,
                   "physics": {"solver": "OpenFOAM Foundation 13 incompressibleFluid", "flow": "transient laminar external sphere",
                               "U_m_s": [0.075, 0, 0], "nu_m2_s": 1.5e-5, "diameter_m": .02,
                               "Re": 100, "end_time_s": .2, "delta_t_s": .0005}, "mesh_validation": "passed"}
    if solve:
        solver = wsl_run(f"foamRun -case '{linux_case}'", "solver.log", 300)
        times = [float(x) for x in re.findall(r"(?m)^Time = ([0-9.eE+-]+)", solver)]
        pressure_residuals = [float(x) for x in re.findall(r"Solving for p, Initial residual = [0-9.eE+-]+, Final residual = ([0-9.eE+-]+)", solver)]
        continuity = [float(x) for x in re.findall(r"time step continuity errors\s*:\s*sum local = [^,]+, global = ([0-9.eE+-]+)", solver)]
        if "\nEnd\n" not in solver or not times or abs(times[-1] - .2) > 1e-6 or not pressure_residuals:
            raise RuntimeError("Solver did not complete the prescribed 0.2 s interval")
        if max(pressure_residuals[-10:]) > 1e-3 or (continuity and max(abs(x) for x in continuity[-10:]) > 1e-5):
            raise RuntimeError("Solver numerical residual or continuity gate failed")
        for field in ("U", "p"):
            if not (case / "0.2" / field).is_file():
                raise RuntimeError(f"Final OpenFOAM field missing: {field}")
        linux_dir = wsl_path(directory)
        wsl_run(f"python3 '{wsl_path(ROOT / 'backend' / 'plot_residuals.py')}' '{linux_dir}/solver.log' '{linux_dir}'", "residuals_plot.log", 120)
        wsl_run(f"pvbatch '{wsl_path(ROOT / 'backend' / 'render_l1.py')}' '{linux_case}' '{linux_dir}' {cells}", "paraview.log", 120)
        wsl_run(f"python3 '{wsl_path(ROOT / 'backend' / 'plot_fields.py')}' '{linux_dir}/slice_centers.csv' '{linux_dir}' 'L1 sphere Re=100, t=0.2 s'", "plot.log", 120)
        stats = json.loads((directory / "field_stats.json").read_text(encoding="utf-8"))
        if not (0 < stats["U_median_m_s"] < .12 and stats["U_p999_m_s"] < .15
                and stats["U_magnitude_m_s"][1] < .3
                and stats["U_samples_above_0_15_m_s"] / stats["samples"] < .001
                and stats["p"][0] < stats["p"][1]):
            raise RuntimeError("Final L1 field range is invalid")
        result_data.update({"solver_exit": "passed", "numerical_criteria": "passed for test horizon; steady convergence not claimed",
                            "final_time_s": times[-1], "steps": len(times), "max_last_10_p_residual": max(pressure_residuals[-10:]),
                            "max_last_10_global_continuity": max(abs(x) for x in continuity[-10:]) if continuity else None,
                            "field_stats": stats, "velocity_outlier_warning": stats["U_magnitude_m_s"][1] > .15,
                            "visualization": "ParaView 6.0.1 field extraction + Matplotlib image",
                            "engineering_validation": "test case passed; not a general CAD case"})
    else:
        result_data["engineering_validation"] = "mesh only; solver not run"
    (directory / "result.json").write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    (directory / "report.md").write_text("# L1 sphere CFD test\n\n" +
        f"Source: {str(cad_input) if cad_input else 'ANSA native test sphere (.ansa)'}.\n\n" +
        f"Cells: {cells}; wall faces: {patches['L1_WALL']}; farfield faces: {patches['L1_FARFIELD']}.\n\n" +
        f"Mesh converted once from mm to m; bounding box (m): {after_box}.\n\n" +
        f"Physics: {json.dumps(result_data['physics'])}.\n\n" +
        f"Validation: {result_data['engineering_validation']}.\n\n" +
        ("Velocity outliers above 0.15 m/s were observed; review farfield mesh/BC sensitivity.\n" if result_data.get("velocity_outlier_warning") else ""), encoding="utf-8")
    if solve:
        from backend.reporting import write_report
        write_report(directory, result_data)
        shutil.make_archive(str(directory / "openfoam_case"), "zip", root_dir=directory, base_dir="openfoam_case")


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    found = rows("SELECT * FROM runs WHERE id=?", (rid,))
    if not found:
        raise HTTPException(404, "Run not found")
    directory = DATA / "runs" / rid
    result_path = directory / "result.json"
    return {**found[0], "stages": run_stages(found[0], directory),
            "log": (directory / "process.log").read_text(encoding="utf-8", errors="replace")[-50000:] if (directory / "process.log").exists() else "",
            "artifacts": [p.name for p in directory.iterdir() if p.is_file()] if directory.exists() else [],
            "result": json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else None}


def run_stages(run: dict, directory: Path) -> list[dict]:
    """Report L1 progress only from persisted outputs, never from elapsed time."""
    if run["kind"] not in {"l1_mesh", "l1_full"}:
        return []
    summary_path = directory / "run_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig")) if summary_path.is_file() else {}
    except (OSError, ValueError):
        summary = {}
    recorded = summary.get("stages") or []
    def stage(name: str, complete: bool, evidence: str, blocked: bool = False):
        return {"name": name, "status": "PASSED" if complete else
                ("BLOCKED" if blocked or run["status"] in {"failed", "cancelled"} else "PENDING"),
                "evidence": evidence if (directory / evidence).exists() else None}
    ansa = any(s.get("name") == "ansa_surface_mesh" and str(s.get("status", "")).startswith("passed") for s in recorded)
    pointwise = summary.get("status") == "passed" and (directory / "l1_pointwise_volume.pw").is_file()
    check = (directory / "checkMesh.log").read_text(encoding="utf-8", errors="replace") if (directory / "checkMesh.log").is_file() else ""
    solver = (directory / "solver.log").read_text(encoding="utf-8", errors="replace") if (directory / "solver.log").is_file() else ""
    geometry = bool((summary.get("geometry") or {}).get("sphere_gate"))
    return [stage("ANSA 几何检查", geometry, "run_summary.json"),
            stage("ANSA 表面网格", ansa, "ansa_mesh.json"),
            stage("Pointwise 体网格", pointwise, "run_summary.json"),
            stage("OpenFOAM 网格检查", "Mesh OK." in check, "checkMesh.log"),
            stage("OpenFOAM 求解", run["kind"] == "l1_full" and "\nEnd\n" in solver and (directory / "result.json").is_file(), "solver.log", run["kind"] == "l1_mesh"),
            stage("ParaView 后处理", (directory / "U.png").is_file() and (directory / "p.png").is_file() and (directory / "paraview.log").is_file(), "paraview.log", run["kind"] == "l1_mesh"),
            stage("报告", (directory / "report.md").is_file() and (directory / "result.json").is_file(), "report.md")]


@app.get("/api/runs/{rid}/artifacts/{name}")
def artifact(rid: str, name: str):
    if not rows("SELECT id FROM runs WHERE id=?", (rid,)) or Path(name).name != name:
        raise HTTPException(404, "Artifact not found")
    path = DATA / "runs" / rid / name
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, filename=name)


@app.get("/api/runs/{rid}/report")
def view_report(rid: str):
    if not rows("SELECT id FROM runs WHERE id=? AND status='success'", (rid,)):
        raise HTTPException(409, "完整流程未成功，暂不能展示成功报告")
    path = DATA / "runs" / rid / "report.html"
    if not path.is_file():
        raise HTTPException(404, "此历史运行没有生成 HTML 报告，请下载原报告")
    return FileResponse(path, media_type="text/html", headers={"Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})


@app.get("/api/runs/{rid}/preview/{name}")
def preview(rid: str, name: str):
    if name not in {"U.png", "p.png", "residuals.png"} or not rows("SELECT id FROM runs WHERE id=?", (rid,)):
        raise HTTPException(404, "Preview not found")
    path = DATA / "runs" / rid / name
    if not path.is_file():
        raise HTTPException(404, "Preview not found")
    return FileResponse(path, media_type="image/png")


from backend.workflow import register as register_workflow

register_workflow(app, DATA, ROOT, CONFIG)

dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
