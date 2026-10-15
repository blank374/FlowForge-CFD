"""Real failure/recovery rehearsal using a validated non-sphere upstream checkpoint.
The human step is simulated by native Pointwise load/rename/save, not a geometry repair.
"""
import argparse,hashlib,json,subprocess,time,urllib.request,urllib.error,uuid
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8134');parser.add_argument('--job',required=True)
    args=parser.parse_args();base=args.base+'/api/workflows/'+args.job
    directory=ROOT/'data/rehearsals'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    events=[]
    def record(kind,**values):
        event={'time':datetime.now(timezone.utc).isoformat(),'event':kind,**values};events.append(event)
        (directory/'trace.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(event,ensure_ascii=True),flush=True)
    def api(suffix='',body=None,file=None):
        headers={};payload=None
        if file:
            boundary=uuid.uuid4().hex
            payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+file.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        elif body is not None:payload=json.dumps(body).encode();headers['Content-Type']='application/json'
        with urllib.request.urlopen(urllib.request.Request(base+suffix,data=payload,headers=headers),timeout=120) as response:return json.load(response)
    def wait(label):
        deadline=time.monotonic()+1200;previous=None
        while time.monotonic()<deadline:
            value=api();state=(value['version'],value['stage'],value['status'])
            if state!=previous:record(label,version=state[0],stage=state[1],status=state[2],error=value.get('error'));previous=state
            if value['status']!='RUNNING':return value
            time.sleep(3)
        raise RuntimeError('Stage timed out; original evidence retained')
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        original=api()
        if original['profile']!='general' or original['status']=='RUNNING':raise RuntimeError('An idle general checkpoint is required')
        start=ROOT/'data/workflows'/args.job/f"v{original['version']}"
        native=start/'pointwise/aircraft_volume.pw'
        if not native.is_file():raise RuntimeError('A real validated Pointwise source project is required')
        upstream={name:digest(start/name) for name in ['input.igs','surface/surface.stl','surface/surface.ansa']}
        record('start',job=args.job,source_version=original['version'],upstream_sha256=upstream,scope='Checkpoint rehearsal; ANSA evidence reused, not re-executed; human save simulated; no aerodynamic validation')
        invalid=directory/'deliberately_corrupt.pw';invalid.write_bytes(b'FLOWFORGE CONTROLLED FAILURE INJECTION - NOT A POINTWISE PROJECT')
        created=api('/pointwise-repair',file=invalid);failed=wait('injected_failure')
        if failed['status']!='NEEDS_MANUAL_REPAIR':raise RuntimeError('Corrupt project was not blocked')
        failed_dir=ROOT/'data/workflows'/args.job/f"v{failed['version']}"
        if (failed_dir/'solver.log').exists() or (failed_dir/'report.html').exists():raise RuntimeError('Invalid project incorrectly released downstream results')
        record('downstream_blocked',version=failed['version'],failure_log=str(failed_dir/'pointwise/export.log'))
        repaired=directory/'simulated_manual_save.pw'
        glyph=directory/'simulate_manual_save.glf'
        glyph.write_text('package require PWI_Glyph\npw::Application reset\npw::Application load [lindex $argv 0]\nset blocks [pw::Grid getAll -type pw::Block]\nif {[llength $blocks] != 1} {error "Expected one real volume block"}\n[lindex $blocks 0] setName FLOWFORGE_REHEARSAL_MANUAL_SAVE\npw::Application save [lindex $argv 1]\nputs "SIMULATED_MANUAL_SAVE_OK"\nexit 0\n',encoding='utf-8')
        config=json.loads((ROOT/'config.json').read_text())
        with (directory/'native_save.log').open('w',encoding='utf-8') as out:
            result=subprocess.run([config['pointwise_glyph_executable'],str(glyph),str(native),str(repaired)],stdout=out,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode or not repaired.is_file() or digest(repaired)==digest(native):raise RuntimeError('Native Pointwise save failed or unchanged')
        record('simulated_manual_handoff',native_software='Pointwise',changed_block_name_only=True,project_sha256=digest(repaired),geometry_repair_claimed=False)
        api('/pointwise-repair',file=repaired);checked=wait('mesh_revalidation')
        if checked['status']!='PAUSED' or checked['stages'][4]['status']!='PASSED':raise RuntimeError('Repaired project did not pass real export/checkMesh')
        checked_dir=ROOT/'data/workflows'/args.job/f"v{checked['version']}"
        for name,sha in upstream.items():
            if digest(checked_dir/name)!=sha:raise RuntimeError('Unchanged upstream checkpoint was modified')
        record('upstream_reused',ansa_rerun=False,hashes_verified=True)
        api('/external-setup',body={'speed_m_s':1,'nu_m2_s':0.001,'wall_patch':'AIRCRAFT_WALL','farfield_patch':'FARFIELD','laminar_confirmed':True,'units_confirmed':True})
        api('/retry-solver',body={'delta_t':0.000001,'end_time':0.000002,'max_co':0.5})
        final=wait('solver_and_report')
        output=ROOT/'data/workflows'/args.job/f"v{final['version']}"
        required=['solver.log','checkMesh.log','U.png','p.png','residuals.png','slice_centers.csv','external_flow.pvsm','report.html','openfoam_case.zip']
        if final['status']!='WAITING_FOR_REVIEW' or not all((output/name).is_file() for name in required):raise RuntimeError('Incomplete terminal result')
        summary={'job':args.job,'version':final['version'],'status':'REHEARSAL_PASSED','physical_validation':False,'manual_step':'Simulated using native Pointwise load/rename/save; no actual mesh defect repaired','upstream':'Existing ANSA checkpoint reused with hashes verified','solver':'Two-step high-viscosity laminar connectivity test only','report_url':base+'/report','artifacts':{name:{'bytes':(output/name).stat().st_size,'sha256':digest(output/name)} for name in required}}
        (directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        record('complete',**summary)
    except Exception as exc:
        record('rehearsal_failed',error=str(exc));raise

if __name__=='__main__':main()
