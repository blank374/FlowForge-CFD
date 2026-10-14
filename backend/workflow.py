"""Incremental, versioned human handoff for the ANSA geometry gate."""
import hashlib
import json
import os
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
        return {**job, "versions": versions, "reviews": reviews,
                "stages": [{"name": "文件输入", "status": "PASSED"},
                           {"name": "ANSA 几何检查", "status": job["status"]},
                           {"name": "ANSA 表面网格", "status": "BLOCKED"},
                           {"name": "Pointwise 体网格", "status": "BLOCKED"},
                           {"name": "OpenFOAM 网格检查", "status": "BLOCKED"},
                           {"name": "OpenFOAM 求解", "status": "BLOCKED"},
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
            if result.returncode or report.get("status") not in {"passed", "needs_manual_repair"}:
                status, error = "NEEDS_MANUAL_REPAIR", report.get("error", "ANSA inspection failed; see ansa.log")
            elif report["status"] == "passed":
                status, error = "WAITING_FOR_REVIEW", None
            else:
                status, error = "NEEDS_MANUAL_REPAIR", "Geometry gate found free CONS, intersections, or missing CAD surfaces"
        except Exception as exc:
            status, error = "NEEDS_MANUAL_REPAIR", str(exc)
            report = {"status": "error", "error": error}
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with lock, db() as connection:
            current = connection.execute("SELECT version FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            connection.execute("UPDATE workflow_versions SET status=?,report=? WHERE job_id=? AND version=?",
                               (status, json.dumps(report), job_id, version))
            if current and current["version"] == version:
                connection.execute("UPDATE workflow_jobs SET status=?,updated=?,error=? WHERE id=?",
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
        if job["status"] not in {"WAITING_FOR_REVIEW", "PASSED", "PAUSED", "NEEDS_MANUAL_REPAIR"}:
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
        if status not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED", "PASSED"}:
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
        if effective_status not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED"}:
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
            if current["version"] != job["version"] or current["status"] not in {"NEEDS_MANUAL_REPAIR", "WAITING_FOR_REVIEW", "PAUSED"}:
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
        if current["report"] is None or current["report"].get("status") != "passed" or sha256(source) != current["sha256"]:
            raise HTTPException(409, "Verified geometry source has changed or gate report is missing")
        with db() as connection:
            connection.execute("INSERT INTO workflow_reviews VALUES(?,?,?,?,?,?)",
                               (job_id, job["version"], "APPROVED", reviewer.strip(), note.strip(), stamp()))
            connection.execute("UPDATE workflow_jobs SET status='PASSED',updated=? WHERE id=? AND status='WAITING_FOR_REVIEW'",
                               (stamp(), job_id))
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
