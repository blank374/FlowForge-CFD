"""Incremental, versioned human handoff for the ANSA geometry gate."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def register(app, data, root, config):
    router = APIRouter(prefix="/api/workflows")
    db_path = data / "flowforge.sqlite3"
    lock = threading.Lock()
    allowed_artifacts = {
        "geometry_report.json": "geometry_report.json", "ansa.log": "ansa.log",
        "surface.ansa": "surface/surface.ansa", "surface.stl": "surface/surface.stl",
        "surface_report.json": "surface/report.json", "stl_quality.json": "surface/stl_quality.json",
        "surface_ansa.log": "surface/ansa.log", "aircraft_volume.pw": "pointwise/aircraft_volume.pw",
        "aircraft_volume.cgns": "pointwise/aircraft_volume.cgns",
        "pointwise.log": "pointwise/pointwise.log", "export.log": "pointwise/export.log",
        "checkMesh.log": "checkMesh.log", "solver.log": "solver.log",
        "units.json": "openfoam_case/units.json",
    }

    def db():
        connection = sqlite3.connect(db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    with db() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_jobs(
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_file_id TEXT NOT NULL,
            status TEXT NOT NULL, stage TEXT NOT NULL, version INTEGER NOT NULL,
            created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT);
        CREATE TABLE IF NOT EXISTS workflow_versions(
            job_id TEXT NOT NULL, version INTEGER NOT NULL, filename TEXT NOT NULL,
            sha256 TEXT NOT NULL, origin TEXT NOT NULL, status TEXT NOT NULL,
            report TEXT, created TEXT NOT NULL, PRIMARY KEY(job_id,version));
        CREATE TABLE IF NOT EXISTS workflow_reviews(
            job_id TEXT NOT NULL, version INTEGER NOT NULL, decision TEXT NOT NULL,
            reviewer TEXT NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        """)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflow_jobs)")}
        if "profile" not in columns:
            connection.execute("ALTER TABLE workflow_jobs ADD COLUMN profile TEXT NOT NULL DEFAULT 'general'")
        if "linked_run_id" not in columns:
            connection.execute("ALTER TABLE workflow_jobs ADD COLUMN linked_run_id TEXT")
        connection.execute("UPDATE workflow_jobs SET status='PAUSED',error='Backend restarted during inspection' WHERE status='RUNNING'")

    def job_row(job_id):
        with db() as connection:
            row = connection.execute("SELECT * FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Workflow not found")
        return dict(row)

    def details(job_id):
        job = job_row(job_id)
        with db() as connection:
            versions = [dict(x) for x in connection.execute(
                "SELECT * FROM workflow_versions WHERE job_id=? ORDER BY version", (job_id,))]
            reviews = [dict(x) for x in connection.execute(
                "SELECT * FROM workflow_reviews WHERE job_id=? ORDER BY created", (job_id,))]
        for version in versions:
            version["report"] = json.loads(version["report"]) if version["report"] else None
            version["download_url"] = f"/api/workflows/{job_id}/versions/{version['version']}/file"
            version["review_project_url"] = f"/api/workflows/{job_id}/versions/{version['version']}/review-project"
            version["review_project_available"] = (data / "workflows" / job_id / f"v{version['version']}" / "review.ansa").is_file()
            version_dir = data / "workflows" / job_id / f"v{version['version']}"
            version["artifacts"] = [{"name": name, "size": (version_dir / relative).stat().st_size,
                                      "url": f"/api/workflows/{job_id}/versions/{version['version']}/artifacts/{name}"}
                                     for name, relative in allowed_artifacts.items() if (version_dir / relative).is_file()]
            manual_meta = data / "workflows" / job_id / f"v{version['version']}" / "manual_edit.json"
            if manual_meta.is_file():
                edit = json.loads(manual_meta.read_text(encoding="utf-8"))
                edit_path = Path(edit["path"])
                version["manual_edit"] = {"path": str(edit_path), "changed": edit_path.is_file() and sha256(edit_path) != edit["initial_sha256"]}
        if job["profile"] == "l1_full":
            from backend.app import get_run
            run = get_run(job["linked_run_id"])
            stages = [{"name": "文件输入", "status": "PASSED", "evidence": None}]
            stages.extend(run["stages"])
            job["status"] = "PASSED" if run["status"] == "success" else (
                "NEEDS_MANUAL_REPAIR" if run["status"] in {"failed", "cancelled", "interrupted"} else "RUNNING")
            if versions:
                versions[-1]["status"] = job["status"]
            job["stage"] = next((s["name"] for s in stages if s["status"] != "PASSED"), "报告")
            job["error"] = run["error"]
            return {**job, "versions": versions, "reviews": reviews, "stages": stages,
                    "run": run, "result": run["result"], "artifacts": run["artifacts"]}
        surface_dir = data / "workflows" / job_id / f"v{job['version']}" / "surface"
        surface_report = surface_dir / "report.json"
        try:
            surface = json.loads(surface_report.read_text(encoding="utf-8")) if surface_report.is_file() else {}
        except (OSError, ValueError):
            surface = {}
        surface_passed = (surface.get("status") == "meshed" and
                          (surface_dir / "surface.ansa").is_file() and
                          (surface_dir / "surface.stl").is_file() and
                          (surface_dir / "stl_quality.json").is_file())
        version_dir = surface_dir.parent
        pointwise_log = version_dir / "pointwise" / "pointwise.log"
        pointwise_passed = (pointwise_log.is_file() and "GENERIC_POINTWISE_STATUS=ok" in
                            pointwise_log.read_text(encoding="utf-8", errors="replace") and
                            (version_dir / "pointwise" / "aircraft_volume.pw").is_file())
        check_log = version_dir / "checkMesh.log"
        mesh_passed = check_log.is_file() and "Mesh OK." in check_log.read_text(encoding="utf-8", errors="replace")
        solver_log = version_dir / "solver.log"
        solver_text = solver_log.read_text(encoding="utf-8", errors="replace") if solver_log.is_file() else ""
        courant = [float(x) for x in re.findall(r"Courant Number mean: [0-9.eE+-]+ max: ([0-9.eE+-]+)", solver_text)]
        solver_passed = ("\nEnd\n" in solver_text and bool(courant) and max(courant) <= 1.0 and
                         (version_dir / "openfoam_case" / "0.002" / "U").is_file())
        artifacts = [{"name": name, "size": (version_dir / relative).stat().st_size,
                      "url": f"/api/workflows/{job_id}/artifacts/{name}"}
                     for name, relative in allowed_artifacts.items() if (version_dir / relative).is_file()]
        def evidence(name):
            return next((item["url"] for item in artifacts if item["name"] == name), None)
        pointwise_text = pointwise_log.read_text(encoding="utf-8", errors="replace") if pointwise_log.is_file() else ""
        cell_match = re.search(r"BLOCK_AFTER_CELLS=(\d+)", pointwise_text)
        metrics = {"surface_elements": surface.get("shell"), "target_length_mm": surface.get("target_length_mm"),
                   "volume_cells": int(cell_match.group(1)) if pointwise_passed and cell_match else None,
                   "maximum_courant": max(courant) if courant else None,
                   "execution_passed": "\nEnd\n" in solver_text,
                   "numerical_checks_passed": solver_passed,
                   "physics_validated": False}
        return {**job, "versions": versions, "reviews": reviews,
                "surface": surface, "metrics": metrics, "artifacts": artifacts,
                "stages": [{"name": "文件输入", "status": "PASSED"},
                           {"name": "ANSA 几何检查", "status": "PASSED" if any(r["version"] == job["version"] and r["decision"] == "APPROVED" for r in reviews) else job["status"], "evidence": evidence("geometry_report.json")},
                           {"name": "ANSA 表面网格", "status": "PASSED" if surface_passed else ("RUNNING" if job["stage"] == "ANSA_SURFACE" and job["status"] == "RUNNING" else "BLOCKED"), "evidence": evidence("surface_report.json")},
                           {"name": "Pointwise 体网格", "status": "PASSED" if pointwise_passed else "BLOCKED", "evidence": evidence("pointwise.log")},
                           {"name": "OpenFOAM 网格检查", "status": "PASSED" if mesh_passed else "BLOCKED", "evidence": evidence("checkMesh.log")},
                           {"name": "OpenFOAM 求解", "status": "PASSED" if solver_passed else ("FAILED" if solver_text else "BLOCKED"), "evidence": evidence("solver.log")},
                           {"name": "ParaView 后处理", "status": "BLOCKED"},
                           {"name": "报告", "status": "BLOCKED"}]}

    def inspect(job_id, version):
        directory = data / "workflows" / job_id / f"v{version}"
        source = next(directory.glob("input.*"))
        report_path = directory / "geometry_report.json"
        project = directory / "review.ansa"
        log = directory / "ansa.log"
        env = os.environ.copy()
        env.update(FLOWFORGE_GATE_SOURCE=str(source), FLOWFORGE_GATE_PROJECT=str(project),
                   FLOWFORGE_GATE_REPORT=str(report_path))
        script = (root / "backend" / "ansa_geometry_gate.py").as_posix()
        try:
            with log.open("w", encoding="utf-8") as output:
                result = subprocess.run([config["ansa_executable"], "-exec", f"load_script: '{script}'",
                                         "-exec", "main()", "-nogui"], env=env, stdout=output,
                                        stderr=subprocess.STDOUT, timeout=600)
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
            complete = (all(key in report for key in ("before_topo", "after_topo", "checks", "source_unchanged"))
                        and isinstance(report.get("checks"), list) and len(report["checks"]) >= 6
                        and report.get("source_unchanged") is True and project.is_file())
            if result.returncode or not complete or report.get("status") not in {"passed", "waiting_for_review", "needs_manual_repair"}:
                status, error = "ERROR", report.get("error", "ANSA inspection failed or report incomplete; see ansa.log")
            elif report["status"] in {"passed", "waiting_for_review"}:
                status, error = "WAITING_FOR_REVIEW", None
            else:
                status, error = "NEEDS_MANUAL_REPAIR", "Geometry checks failed; inspect geometry_report.json"
        except Exception as exc:
            status, error = "ERROR", str(exc)
            report = {"status": "error", "error": error}
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with lock, db() as connection:
            current = connection.execute("SELECT version FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            connection.execute("UPDATE workflow_versions SET status=?,report=? WHERE job_id=? AND version=?",
                               (status, json.dumps(report), job_id, version))
            if current and current["version"] == version:
                connection.execute("UPDATE workflow_jobs SET status=?,updated=?,error=? WHERE id=?",
                                   (status, stamp(), error, job_id))

    def mesh_surface(job_id, version, length_mm):
        directory = data / "workflows" / job_id / f"v{version}" / "surface"
        directory.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update(FLOWFORGE_SURFACE_SOURCE=str(directory.parent / "review.ansa"),
                   FLOWFORGE_SURFACE_OUTPUT=str(directory),
                   FLOWFORGE_SURFACE_REPORT=str(directory / "report.json"),
                   FLOWFORGE_SURFACE_LENGTH_MM=str(length_mm))
        script = (root / "integrations" / "generic_external" / "ansa_surface.py").as_posix()
        try:
            with (directory / "ansa.log").open("w", encoding="utf-8") as output:
                proc = subprocess.run([config["ansa_executable"], "-exec", f"load_script: '{script}'",
                                       "-exec", "main()", "-nogui"], env=env, stdout=output,
                                      stderr=subprocess.STDOUT, timeout=1800)
            report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
            if proc.returncode or report.get("status") != "meshed":
                raise RuntimeError(report.get("error", "ANSA surface meshing failed; inspect ansa.log"))
            if not all((directory / name).is_file() for name in ("surface.ansa", "surface.stl")):
                raise RuntimeError("ANSA reported success without both mesh artifacts")
            from backend.validate_surface_stl import inspect as inspect_stl
            quality = inspect_stl(directory / "surface.stl")
            (directory / "stl_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
            if not quality["passed"]:
                raise RuntimeError("Exported STL failed closure or degeneracy check")
            status, error = "PAUSED", "Surface mesh generated; Pointwise volume stage is not yet available"
        except Exception as exc:
            status, error = "NEEDS_MANUAL_REPAIR", str(exc)
        with lock, db() as connection:
            current = connection.execute("SELECT version FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            if current and current["version"] == version:
                connection.execute("UPDATE workflow_jobs SET status=?,stage='ANSA_SURFACE',updated=?,error=? WHERE id=?",
                                   (status, stamp(), error, job_id))

    def mesh_volume(job_id, version):
        directory = data / "workflows" / job_id / f"v{version}"
        output = directory / "pointwise"
        output.mkdir(exist_ok=True)
        executable = config["pointwise_glyph_executable"]
        try:
            for script_name, args, log_name, marker in (
                ("pointwise_aircraft.glf", [str(directory / "surface" / "surface.stl"), str(output)],
                 "pointwise.log", "GENERIC_POINTWISE_STATUS=ok"),
                ("export_openfoam.glf", [str(output / "aircraft_volume.pw"), str(output / "openfoam_export")],
                 "export.log", "OPENFOAM_EXPORT_STATUS=ok")):
                script = root / "integrations" / "generic_external" / script_name
                with (output / log_name).open("w", encoding="utf-8") as stream:
                    proc = subprocess.run([executable, str(script), *args], stdout=stream,
                                          stderr=subprocess.STDOUT, timeout=1800)
                log = (output / log_name).read_text(encoding="utf-8", errors="replace")
                if proc.returncode or marker not in log:
                    raise RuntimeError(f"Pointwise {script_name} failed; inspect {log_name}")
            export = output / "openfoam_export"
            boundary = (export / "boundary").read_text(encoding="utf-8")
            if not all(re.search(rf"\b{name}\s*\{{[^}}]*nFaces\s+[1-9]", boundary)
                       for name in ("AIRCRAFT_WALL", "FARFIELD")) or "Unspecified" in boundary:
                raise RuntimeError("Pointwise boundary patch gate failed")
            case = directory / "openfoam_case"
            mesh = case / "constant" / "polyMesh"
            mesh.mkdir(parents=True, exist_ok=True)
            shutil.copytree(export, mesh, dirs_exist_ok=True)
            template = root / "integrations" / "l1" / "foam_template" / "system"
            (case / "system").mkdir(exist_ok=True)
            shutil.copy2(template / "controlDict", case / "system" / "controlDict")
            drive = config.get("wsl_mount_drive", "f")
            windows_case = case.resolve().as_posix()
            if not windows_case.lower().startswith(drive.lower() + ":/"):
                raise RuntimeError("OpenFOAM case is outside the configured WSL drive")
            linux_case = f"/mnt/{drive}/{windows_case[3:]}"
            def foam(command, name):
                with (directory / name).open("w", encoding="utf-8") as stream:
                    proc = subprocess.run(["wsl.exe", "-d", "Ubuntu-F2", "--", "bash", "-lc",
                                           f"source /opt/openfoam13/etc/bashrc; {command} -case '{linux_case}'"],
                                          stdout=stream, stderr=subprocess.STDOUT, timeout=600)
                log = (directory / name).read_text(encoding="utf-8", errors="replace")
                if proc.returncode or (command == "checkMesh" and "Mesh OK." not in log):
                    raise RuntimeError(f"OpenFOAM {command} failed; inspect {name}")
                return log
            before = foam("checkMesh", "checkMesh_mm.log")
            if (case / "units.json").exists():
                raise RuntimeError("Mesh has already been scaled")
            foam("transformPoints 'scale=(0.001 0.001 0.001)'", "transformPoints.log")
            after = foam("checkMesh", "checkMesh.log")
            def bounds(log):
                match = re.search(r"Overall domain bounding box \(([^)]+)\) \(([^)]+)\)", log)
                if not match:
                    raise RuntimeError("checkMesh bounding box missing")
                return [float(x) for group in match.groups() for x in group.split()]
            before_box, after_box = bounds(before), bounds(after)
            if not all(abs(a - .001 * b) < 2e-5 for a, b in zip(after_box, before_box)):
                raise RuntimeError("Mesh unit conversion did not preserve scale")
            (case / "units.json").write_text(json.dumps({"source_unit": "mm", "target_unit": "m",
                "scale": .001, "before_bbox_mm": before_box, "after_bbox_m": after_box}, indent=2), encoding="utf-8")
            status, error = "PAUSED", "Volume mesh and checkMesh passed; solver configuration requires review"
        except Exception as exc:
            status, error = "NEEDS_MANUAL_REPAIR", str(exc)
        with lock, db() as connection:
            current = connection.execute("SELECT version FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            if current and current["version"] == version:
                connection.execute("UPDATE workflow_jobs SET status=?,stage='POINTWISE_VOLUME',updated=?,error=? WHERE id=?",
                                   (status, stamp(), error, job_id))

    @router.post("/projects/{project_id}")
    def create(project_id: str, file_id: str, manual: bool = False, profile: str = "general"):
        with db() as connection:
            source = connection.execute("SELECT * FROM files WHERE id=? AND project_id=?", (file_id, project_id)).fetchone()
        if not source:
            raise HTTPException(404, "Project file not found")
        suffix = Path(source["name"]).suffix.lower()
        if profile not in {"general", "l1_full"}:
            raise HTTPException(400, "Unsupported workflow profile")
        if profile == "l1_full" and manual:
            raise HTTPException(400, "Use the general profile for manual ANSA processing")
        if profile == "l1_full" and suffix not in {".igs", ".iges"}:
            raise HTTPException(400, "L1 full profile requires an IGES file")
        if suffix not in {".igs", ".iges", ".stp", ".step", ".ansa"}:
            raise HTTPException(400, "ANSA geometry gate accepts CAD or ANSA projects; mesh-only inputs need another path")
        job_id = uuid.uuid4().hex
        directory = data / "workflows" / job_id / "v1"
        directory.mkdir(parents=True)
        target = directory / ("input" + suffix)
        shutil.copy2(source["path"], target)
        digest = sha256(target)
        linked_run_id = None
        if profile == "l1_full":
            from backend.app import RunIn, create_run
            linked_run_id = create_run(project_id, RunIn(kind="l1_full", file_id=file_id))["id"]
        with db() as connection:
            status = "NEEDS_MANUAL_REPAIR" if manual else "RUNNING"
            if profile == "l1_full":
                status = "RUNNING"
            connection.execute("INSERT INTO workflow_jobs(id,project_id,source_file_id,status,stage,version,created,updated,error,profile,linked_run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (job_id, project_id, file_id, status, "文件输入" if profile == "l1_full" else "ANSA_GEOMETRY", 1, stamp(), stamp(),
                                "Operator selected manual ANSA processing" if manual and profile == "general" else None,
                                profile, linked_run_id))
            connection.execute("INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)",
                               (job_id, 1, source["name"], digest, "uploaded", status, None, stamp()))
        if not manual and profile == "general":
            threading.Thread(target=inspect, args=(job_id, 1), daemon=True).start()
        return details(job_id)

    @router.get("/projects/{project_id}")
    def list_jobs(project_id: str):
        with db() as connection:
            jobs = [dict(x) for x in connection.execute(
                "SELECT * FROM workflow_jobs WHERE project_id=? ORDER BY created DESC", (project_id,))]
            for job in jobs:
                if job["profile"] == "l1_full" and job["linked_run_id"]:
                    run = connection.execute("SELECT status,error FROM runs WHERE id=?", (job["linked_run_id"],)).fetchone()
                    if run:
                        job["status"] = "PASSED" if run["status"] == "success" else (
                            "NEEDS_MANUAL_REPAIR" if run["status"] in {"failed", "cancelled", "interrupted"} else "RUNNING")
                        job["error"] = run["error"]
            return jobs

    @router.get("/{job_id}")
    def get(job_id: str):
        return details(job_id)

    @router.post("/{job_id}/manual")
    def request_manual(job_id: str):
        job = job_row(job_id)
        if job["status"] not in {"WAITING_FOR_REVIEW", "PASSED", "PAUSED", "NEEDS_MANUAL_REPAIR", "ERROR"}:
            raise HTTPException(409, "Wait for the current ANSA inspection to finish")
        with lock, db() as connection:
            connection.execute("UPDATE workflow_jobs SET status='NEEDS_MANUAL_REPAIR',updated=?,error=? WHERE id=?",
                               (stamp(), "Operator selected manual ANSA processing", job_id))
            connection.execute("INSERT INTO workflow_reviews VALUES(?,?,?,?,?,?)",
                               (job_id, job["version"], "MANUAL_REQUESTED", "operator", "", stamp()))
        return details(job_id)

    @router.post("/{job_id}/open-in-ansa")
    def open_in_ansa(job_id: str, request: Request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "ANSA can only be launched from this local FlowForge page")
        job = job_row(job_id)
        status = details(job_id)["status"]
        if status not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED", "PASSED", "ERROR"}:
            raise HTTPException(409, "Wait for the current operation to finish")
        executable = Path(config["ansa_executable"])
        if not executable.is_file():
            raise HTTPException(503, "ANSA is not installed at the configured path")
        directory = data / "workflows" / job_id / f"v{job['version']}"
        source = directory / "review.ansa"
        if job["profile"] == "l1_full" or not source.is_file():
            source = next(directory.glob("input.*"), None)
        if source is None or not source.is_file():
            raise HTTPException(404, "Task input is missing")
        edit = directory / ("manual_edit" + source.suffix.lower())
        meta = directory / "manual_edit.json"
        if not meta.is_file():
            shutil.copy2(source, edit)
            meta.write_text(json.dumps({"path": str(edit), "initial_sha256": sha256(edit), "source": str(source)}, indent=2), encoding="utf-8")
        else:
            edit = Path(json.loads(meta.read_text(encoding="utf-8"))["path"])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen([str(executable), "-i", str(edit)],
                             cwd=str(directory), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        except OSError as exc:
            raise HTTPException(503, f"Could not start ANSA: {exc}") from exc
        if job["profile"] == "general" and status in {"WAITING_FOR_REVIEW", "PASSED", "PAUSED"}:
            with lock, db() as connection:
                connection.execute("UPDATE workflow_jobs SET status='NEEDS_MANUAL_REPAIR',updated=?,error=? WHERE id=?",
                                   (stamp(), "Operator opened ANSA for manual processing", job_id))
        return {"status": "launched", "path": str(edit), "job": details(job_id)}

    @router.post("/{job_id}/submit-local-repair")
    async def submit_local_repair(job_id: str, request: Request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Local repair can only be submitted from this FlowForge page")
        job = job_row(job_id)
        directory = data / "workflows" / job_id / f"v{job['version']}"
        meta = directory / "manual_edit.json"
        if not meta.is_file():
            raise HTTPException(404, "Open this task in ANSA first")
        edit = json.loads(meta.read_text(encoding="utf-8"))
        path = Path(edit["path"])
        if path.parent.resolve() != directory.resolve() or not path.is_file():
            raise HTTPException(404, "ANSA working copy is missing")
        if sha256(path) == edit["initial_sha256"]:
            raise HTTPException(409, "Working copy has not changed; save the repair in ANSA first")
        with path.open("rb") as source:
            return await repair(job_id, UploadFile(filename=path.name, file=source))

    @router.post("/{job_id}/repair")
    async def repair(job_id: str, file: UploadFile = File(...)):
        job = job_row(job_id)
        effective_status = details(job_id)["status"] if job["profile"] == "l1_full" else job["status"]
        if effective_status not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED", "ERROR"}:
            raise HTTPException(409, "Workflow is not awaiting a repair")
        name = Path(file.filename or "repair").name
        suffix = Path(name).suffix.lower()
        if job["profile"] == "l1_full" and suffix not in {".igs", ".iges"}:
            raise HTTPException(400, "L1 retry requires a repaired IGES file")
        if suffix not in {".ansa", ".igs", ".iges", ".stp", ".step"}:
            raise HTTPException(400, "Upload an ANSA project or CAD repair")
        version = job["version"] + 1
        directory = data / "workflows" / job_id / f"v{version}"
        directory.mkdir(parents=True)
        target = directory / ("input" + suffix)
        size = 0
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 1024 * 1024 * 1024:
                    target.unlink(missing_ok=True)
                    raise HTTPException(413, "Repair file exceeds 1 GB")
                output.write(chunk)
        if not size:
            target.unlink(missing_ok=True)
            raise HTTPException(400, "Empty repair file")
        digest = sha256(target)
        if job["profile"] == "l1_full":
            from backend.app import RunIn, create_run
            file_id = uuid.uuid4().hex
            with db() as connection:
                connection.execute("INSERT INTO files VALUES(?,?,?,?,?,?)",
                                   (file_id, job["project_id"], name, str(target), size, stamp()))
            linked_run_id = create_run(job["project_id"], RunIn(kind="l1_full", file_id=file_id))["id"]
            with lock, db() as connection:
                connection.execute("UPDATE workflow_versions SET status=? WHERE job_id=? AND version=?",
                                   (effective_status, job_id, job["version"]))
                connection.execute("UPDATE workflow_jobs SET version=?,status='RUNNING',stage='文件输入',updated=?,error=NULL,linked_run_id=? WHERE id=?",
                                   (version, stamp(), linked_run_id, job_id))
                connection.execute("INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)",
                                   (job_id, version, name, digest, "manual_repair", "RUNNING", None, stamp()))
            return details(job_id)
        with lock, db() as connection:
            current = connection.execute("SELECT version,status FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            if current["version"] != job["version"] or current["status"] not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED", "ERROR"}:
                target.unlink(missing_ok=True)
                raise HTTPException(409, "Workflow changed while uploading")
            connection.execute("UPDATE workflow_jobs SET version=?,status='RUNNING',updated=?,error=NULL WHERE id=?",
                               (version, stamp(), job_id))
            connection.execute("INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)",
                               (job_id, version, name, digest, "manual_repair", "RUNNING", None, stamp()))
        threading.Thread(target=inspect, args=(job_id, version), daemon=True).start()
        return details(job_id)

    @router.post("/{job_id}/approve")
    def approve(job_id: str, reviewer: str, note: str = ""):
        job = job_row(job_id)
        if job["status"] != "WAITING_FOR_REVIEW":
            raise HTTPException(409, "ANSA geometry verification has not passed")
        if not reviewer.strip():
            raise HTTPException(400, "Reviewer name is required")
        current = details(job_id)["versions"][-1]
        source = next((data / "workflows" / job_id / f"v{job['version']}").glob("input.*"))
        if current["report"] is None or current["report"].get("status") not in {"passed", "waiting_for_review"} or sha256(source) != current["sha256"]:
            raise HTTPException(409, "Verified geometry source has changed or gate report is missing")
        if current["report"].get("status") == "waiting_for_review" and not note.strip():
            raise HTTPException(400, "Review note must explain why open boundaries are intended")
        with db() as connection:
            connection.execute("INSERT INTO workflow_reviews VALUES(?,?,?,?,?,?)",
                               (job_id, job["version"], "APPROVED", reviewer.strip(), note.strip(), stamp()))
            connection.execute("UPDATE workflow_jobs SET status='PASSED',updated=? WHERE id=? AND status='WAITING_FOR_REVIEW'",
                               (stamp(), job_id))
        return details(job_id)

    @router.post("/{job_id}/surface-mesh")
    def start_surface(job_id: str, length_mm: float = 12.0):
        job = job_row(job_id)
        if job["profile"] != "general" or job["status"] not in {"PASSED", "PAUSED", "NEEDS_MANUAL_REPAIR"}:
            raise HTTPException(409, "An approved general geometry version is required")
        if not 0.1 <= length_mm <= 100:
            raise HTTPException(400, "Surface length must be in millimetres")
        with db() as connection:
            approved = connection.execute("SELECT 1 FROM workflow_reviews WHERE job_id=? AND version=? AND decision='APPROVED'",
                                          (job_id, job["version"])).fetchone()
        if not approved:
            raise HTTPException(409, "Current geometry version has no approval")
        directory = data / "workflows" / job_id / f"v{job['version']}" / "surface"
        if directory.exists() and any(directory.iterdir()):
            raise HTTPException(409, "Surface attempt already exists; preserve its evidence before retrying")
        with lock, db() as connection:
            connection.execute("UPDATE workflow_jobs SET status='RUNNING',stage='ANSA_SURFACE',updated=?,error=NULL WHERE id=?",
                               (stamp(), job_id))
        threading.Thread(target=mesh_surface, args=(job_id, job["version"], length_mm), daemon=True).start()
        return details(job_id)

    @router.get("/{job_id}/surface/{name}")
    def surface_artifact(job_id: str, name: str):
        if name not in {"surface.ansa", "surface.stl", "report.json", "stl_quality.json", "ansa.log"}:
            raise HTTPException(404, "Surface artifact not found")
        job = job_row(job_id)
        path = data / "workflows" / job_id / f"v{job['version']}" / "surface" / name
        if not path.is_file():
            raise HTTPException(404, "Surface artifact not found")
        return FileResponse(path, filename=name)

    @router.get("/{job_id}/artifacts/{name}")
    def generic_artifact(job_id: str, name: str):
        job = job_row(job_id)
        if job["profile"] != "general" or name not in allowed_artifacts:
            raise HTTPException(404, "Artifact not found")
        path = data / "workflows" / job_id / f"v{job['version']}" / allowed_artifacts[name]
        if not path.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(path, filename=name)

    @router.get("/{job_id}/versions/{version}/artifacts/{name}")
    def version_artifact(job_id: str, version: int, name: str):
        job_row(job_id)
        if name not in allowed_artifacts:
            raise HTTPException(404, "Artifact not found")
        with db() as connection:
            known = connection.execute("SELECT 1 FROM workflow_versions WHERE job_id=? AND version=?",
                                       (job_id, version)).fetchone()
        if not known:
            raise HTTPException(404, "Version not found")
        path = data / "workflows" / job_id / f"v{version}" / allowed_artifacts[name]
        if not path.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(path, filename=name)

    @router.post("/{job_id}/volume-mesh")
    def start_volume(job_id: str):
        job = job_row(job_id)
        current = details(job_id)
        if job["profile"] != "general" or job["status"] not in {"PASSED", "PAUSED"} or current["stages"][2]["status"] != "PASSED":
            raise HTTPException(409, "A passed general surface mesh is required")
        directory = data / "workflows" / job_id / f"v{job['version']}" / "pointwise"
        if directory.exists() and any(directory.iterdir()):
            raise HTTPException(409, "Pointwise attempt already exists; preserve its evidence before retrying")
        with lock, db() as connection:
            connection.execute("UPDATE workflow_jobs SET status='RUNNING',stage='POINTWISE_VOLUME',updated=?,error=NULL WHERE id=?",
                               (stamp(), job_id))
        threading.Thread(target=mesh_volume, args=(job_id, job["version"]), daemon=True).start()
        return details(job_id)

    @router.get("/{job_id}/versions/{version}/file")
    def input_file(job_id: str, version: int):
        row = next((x for x in details(job_id)["versions"] if x["version"] == version), None)
        if not row:
            raise HTTPException(404, "Version not found")
        directory = data / "workflows" / job_id / f"v{version}"
        source = next(directory.glob("input.*"), None)
        if not source:
            raise HTTPException(404, "Version file missing")
        return FileResponse(source, filename=row["filename"])

    @router.get("/{job_id}/versions/{version}/review-project")
    def review_project(job_id: str, version: int):
        if not any(x["version"] == version for x in details(job_id)["versions"]):
            raise HTTPException(404, "Version not found")
        path = data / "workflows" / job_id / f"v{version}" / "review.ansa"
        if not path.is_file():
            raise HTTPException(404, "ANSA review project was not generated")
        return FileResponse(path, filename=f"flowforge_{job_id}_v{version}.ansa")

    @router.get("/{job_id}/versions/{version}/log")
    def log(job_id: str, version: int):
        if not any(x["version"] == version for x in details(job_id)["versions"]):
            raise HTTPException(404, "Version not found")
        path = data / "workflows" / job_id / f"v{version}" / "ansa.log"
        return {"log": path.read_text(encoding="utf-8", errors="replace")[-50000:] if path.is_file() else ""}

    app.include_router(router)
