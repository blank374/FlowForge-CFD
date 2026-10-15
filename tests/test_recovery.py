import json
import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import workflow

def test_checkpoint_reuses_mesh_and_preserves_failure(tmp_path, monkeypatch):
    data=tmp_path/'data';data.mkdir()
    source=tmp_path/'model.ansa';source.write_bytes(b'geometry')
    with sqlite3.connect(data/'flowforge.sqlite3') as c:
        c.execute('CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)')
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',('f','p','model.ansa',str(source),8,'now'))
    app=FastAPI();workflow.register(app,data,tmp_path,{})
    with TestClient(app) as client:
        job=client.post('/api/workflows/projects/p?file_id=f&manual=true').json();jid=job['id']
        base=data/'workflows'/jid/'v1';case=base/'openfoam_case'
        for name in ['0','constant/polyMesh','system']:(case/name).mkdir(parents=True)
        for name in ['0/U','0/p','system/fvSchemes','system/fvSolution','constant/polyMesh/faces','constant/polyMesh/owner','constant/polyMesh/neighbour','constant/polyMesh/boundary']:(case/name).write_text('fixture')
        (case/'constant/polyMesh/points').write_bytes(b'real-mesh-fixture')
        (case/'system/controlDict').write_text('deltaT 0.0001;\nendTime 0.002;')
        (base/'checkMesh.log').write_text('Mesh OK.')
        (base/'solver.log').write_text('Courant Number mean: 1 max: 200001\n')
        old_results = ['result.json','report.html','report.docx','U.png','paraview_manifest.json','force_coefficients.csv','postprocess_0.log','openfoam_case.zip']
        for name in old_results:
            (base/name).write_text('old result')
        assert client.post(f'/api/workflows/{jid}/retry-solver',json={'delta_t':-1}).status_code==422
        monkeypatch.setattr('backend.recovery.threading.Thread.start',lambda self:None)
        response=client.post(f'/api/workflows/{jid}/retry-solver',json={'delta_t':0.000001})
        assert response.status_code==200,response.text
        assert response.json()['version']==2
        newer=base.parent/'v2'
        assert all((base/name).exists() and not (newer/name).exists() for name in old_results)
        assert (newer/'openfoam_case/constant/polyMesh/points').read_bytes()==b'real-mesh-fixture'
        assert (base/'solver.log').is_file() and not (newer/'solver.log').exists()
        manifest=json.loads((newer/'checkpoint.json').read_text())
        assert manifest['parent_version']==1 and manifest['mesh'] and manifest['parameter_sha256']
        assert response.json()['stages'][5]['status']=='RUNNING'
        assert client.post(f'/api/workflows/{jid}/retry-solver',json={}).status_code==409
