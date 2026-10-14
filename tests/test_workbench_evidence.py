"""Workbench evidence comes from files and stays attached to its version."""
import sqlite3
import tempfile
import gc
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import workflow


def test_versioned_artifact_and_failed_solver_status():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        data = root / "data"
        data.mkdir()
        source = root / "model.ansa"
        source.write_bytes(b"geometry")
        with sqlite3.connect(data / "flowforge.sqlite3") as connection:
            connection.execute("CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)")
            connection.execute("INSERT INTO files VALUES(?,?,?,?,?,?)",
                               ("f", "p", source.name, str(source), source.stat().st_size, "now"))
        connection.close()
        app = FastAPI()
        workflow.register(app, data, root, {"ansa_executable": str(source)})
        with TestClient(app) as client:
            job = client.post("/api/workflows/projects/p?file_id=f&manual=true").json()
            job_id = job["id"]
            version = data / "workflows" / job_id / "v1"
            (version / "solver.log").write_text("Courant Number mean: 0.1 max: 100\n", encoding="utf-8")
            details = client.get(f"/api/workflows/{job_id}").json()
            assert details["stages"][5]["status"] == "FAILED"
            assert details["metrics"]["maximum_courant"] == 100
            url = details["versions"][0]["artifacts"][0]["url"]
            assert client.get(url).status_code == 200
            assert client.get(f"/api/workflows/{job_id}/artifacts/unknown").status_code == 404
        del client, app
        gc.collect()
        time.sleep(0.1)
