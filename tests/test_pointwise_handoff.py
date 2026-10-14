import io,sqlite3,time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import workflow

def test_pointwise_repair_creates_new_version_and_never_reuses_solution(tmp_path,monkeypatch):
    data=tmp_path/'data';data.mkdir();source=tmp_path/'source.ansa';source.write_bytes(b'original')
    with sqlite3.connect(data/'flowforge.sqlite3') as c:
        c.execute('CREATE TABLE files(id TEXT,project_id TEXT,name TEXT,path TEXT,size INTEGER,created TEXT)')
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',('f','p','source.ansa',str(source),8,'now'))
    app=FastAPI();workflow.register(app,data,tmp_path,{'pointwise_glyph_executable':'not-installed'})
    def fail_export(*args,**kwargs):raise OSError('Pointwise unavailable in unit test')
    monkeypatch.setattr(workflow.subprocess,'run',fail_export)
    with TestClient(app) as client:
        job=client.post('/api/workflows/projects/p?file_id=f&manual=true').json();jid=job['id'];old=data/'workflows'/jid/'v1'
        (old/'solver.log').write_text('old failed result')
        assert client.post(f'/api/workflows/{jid}/pointwise-repair',files={'file':('bad.exe',b'not a project')}).status_code==422
        result=client.post(f'/api/workflows/{jid}/pointwise-repair',files={'file':('repaired.pw',b'native project fixture')})
        assert result.status_code==200,result.text
        assert result.json()['version']==2
        new=old.parent/'v2'
        assert (new/'pointwise/aircraft_volume.pw').read_bytes()==b'native project fixture'
        assert (old/'solver.log').read_text()=='old failed result' and not (new/'solver.log').exists()
        for _ in range(50):
            current=client.get(f'/api/workflows/{jid}').json()
            if current['status']!='RUNNING':break
            time.sleep(.01)
        assert current['status']=='NEEDS_MANUAL_REPAIR'
        assert current['stages'][4]['status']!='PASSED'
