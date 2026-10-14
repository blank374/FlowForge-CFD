"""A saved ANSA working copy becomes a new version without a browser upload."""
import gc
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import workflow


class LocalHandoffTest(unittest.TestCase):
    def test_open_save_submit_creates_new_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            source = root / "source.ansa"
            source.write_bytes(b"original model")
            with sqlite3.connect(data / "flowforge.sqlite3") as connection:
                connection.execute("CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)")
                connection.execute("INSERT INTO files VALUES(?,?,?,?,?,?)",
                                   ("file1", "project1", source.name, str(source), source.stat().st_size, "now"))
            connection.close()
            app = FastAPI()
            workflow.register(app, data, root, {"ansa_executable": str(source)})
            with TestClient(app) as client:
                job = client.post("/api/workflows/projects/project1?file_id=file1&manual=true").json()
                with patch.object(workflow.subprocess, "Popen") as launch:
                    opened = client.post(f"/api/workflows/{job['id']}/open-in-ansa")
                self.assertEqual(opened.status_code, 200)
                launch.assert_called_once()
                edit = Path(opened.json()["path"])
                self.assertEqual(edit.read_bytes(), b"original model")
                self.assertEqual(client.post(f"/api/workflows/{job['id']}/submit-local-repair").status_code, 409)
                edit.write_bytes(b"repaired model")
                submitted = client.post(f"/api/workflows/{job['id']}/submit-local-repair")
                self.assertEqual(submitted.status_code, 200)
                self.assertEqual(submitted.json()["version"], 2)
                self.assertEqual((data / "workflows" / job["id"] / "v1" / "input.ansa").read_bytes(), b"original model")
                self.assertEqual((data / "workflows" / job["id"] / "v2" / "input.ansa").read_bytes(), b"repaired model")
                for _ in range(40):
                    if client.get(f"/api/workflows/{job['id']}").json()["status"] != "RUNNING":
                        break
                    time.sleep(0.05)
                time.sleep(0.5)
            gc.collect()


if __name__ == "__main__":
    unittest.main()
