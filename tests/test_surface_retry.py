import json,sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import workflow

def test_coarse_surface_explained_and_retry_preserves_evidence(tmp_path,monkeypatch):
    data=tmp_path/'data';data.mkdir();source=tmp_path/'input.igs';source.write_bytes(b'cad')
    with sqlite3.connect(data/'flowforge.sqlite3') as c:
        c.execute('CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)')
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',('f','p','input.igs',str(source),3,'now'))
    app=FastAPI();workflow.register(app,data,tmp_path,{})
    with TestClient(app) as client:
        job=client.post('/api/workflows/projects/p?file_id=f&manual=true').json();jid=job['id'];old=data/'workflows'/jid/'v1'
        (old/'review.ansa').write_bytes(b'approved geometry')
        (old/'surface').mkdir();(old/'surface/report.json').write_text(json.dumps({'status':'error','shell':42,'target_length_mm':12}))
        with sqlite3.connect(data/'flowforge.sqlite3') as c:
            c.execute("UPDATE workflow_jobs SET stage='ANSA_SURFACE' WHERE id=?",(jid,))
            c.execute('INSERT INTO workflow_reviews VALUES(?,?,?,?,?,?)',(jid,1,'APPROVED','test','fixture','now'))
        details=client.get(f'/api/workflows/{jid}').json()
        assert '42' in details['error'] and 'Traceback' not in details['error']
        assert client.post(f'/api/workflows/{jid}/retry-surface?length_mm=0').status_code==422
        monkeypatch.setattr(workflow.threading.Thread,'start',lambda self:None)
        retry=client.post(f'/api/workflows/{jid}/retry-surface?length_mm=0.5')
        assert retry.status_code==200,retry.text
        assert retry.json()['version']==2
        assert retry.json()['metrics']['target_length_mm']==0.5
        new=old.parent/'v2'
        assert (old/'surface/report.json').is_file() and not (new/'surface').exists()
        assert (new/'review.ansa').read_bytes()==b'approved geometry'
        assert json.loads((new/'surface_settings.json').read_text())['length_mm']==0.5
        assert client.post(f'/api/workflows/{jid}/retry-surface?length_mm=1').status_code==409

def test_start_records_actual_length_before_report_exists(tmp_path, monkeypatch):
    data=tmp_path/'data';data.mkdir();source=tmp_path/'input.igs';source.write_bytes(b'cad')
    with sqlite3.connect(data/'flowforge.sqlite3') as c:
        c.execute('CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)')
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',('f','p','input.igs',str(source),3,'now'))
    app=FastAPI();workflow.register(app,data,tmp_path,{})
    with TestClient(app) as client:
        jid=client.post('/api/workflows/projects/p?file_id=f&manual=true').json()['id']
        monkeypatch.setattr(workflow.threading.Thread,'start',lambda self:None)
        version=data/'workflows'/jid/'v1'
        (version/'review.ansa').write_bytes(b'approved')
        with sqlite3.connect(data/'flowforge.sqlite3') as c:
            c.execute("UPDATE workflow_jobs SET status='PASSED' WHERE id=?",(jid,))
            c.execute('INSERT INTO workflow_reviews VALUES(?,?,?,?,?,?)',(jid,1,'APPROVED','test','','now'))
        response=client.post(f'/api/workflows/{jid}/surface-mesh?length_mm=0.25')
        assert response.status_code==200,response.text
        assert response.json()['metrics']['target_length_mm']==0.25
        assert json.loads((version/'surface_settings.json').read_text())['length_mm']==0.25
        assert client.get(f'/api/workflows/{jid}').json()['metrics']['target_length_mm']==0.25
