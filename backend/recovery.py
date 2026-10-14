"""Immutable solver restart: reuse only a fingerprinted mesh, restart from time zero."""
import hashlib
import json
import math
import re
import shutil
import subprocess
import threading
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel, Field

class SolverSettings(BaseModel):
    delta_t: float = Field(default=0.000001, gt=0, le=0.0001, allow_inf_nan=False)
    end_time: float = Field(default=0.002, gt=0, le=0.002, allow_inf_nan=False)
    max_co: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)

def fingerprint(directory, sha):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}

def register_recovery(router, data, config, job_row, details, db, lock, stamp, sha):
    def execute(job_id, version, directory):
        status, error = 'FAILED', None
        try:
            case=directory/'openfoam_case'
            windows=case.resolve().as_posix()
            if not re.match(r'^[A-Za-z]:/[^\'\n\r]+$', windows):
                raise RuntimeError('Unsupported WSL case path')
            linux='/mnt/'+windows[0].lower()+windows[2:]
            for command, name in [('checkMesh','checkMesh.log'),('foamRun','solver.log')]:
                with (directory/name).open('w',encoding='utf-8') as out:
                    result=subprocess.run(['wsl.exe','-d',config.get('wsl_distro','Ubuntu-F2'),'--','bash','-lc',
                        f"source /opt/openfoam13/etc/bashrc && {command} -case '{linux}'"],stdout=out,stderr=subprocess.STDOUT,timeout=1800)
                text=(directory/name).read_text(encoding='utf-8',errors='replace')
                if result.returncode or (command=='checkMesh' and 'Mesh OK.' not in text):
                    raise RuntimeError(f'{command} 未通过，请查看 {name}；原检查点已保留')
            # A finished process alone does not establish trustworthy flow results.
            status='WAITING_FOR_REVIEW'
            error='求解进程结束；需审核残差、质量与物理结果，尚未生成可信报告'
        except Exception as exc:
            error=str(exc)
        with lock, db() as c:
            c.execute('UPDATE workflow_jobs SET status=?,error=?,updated=? WHERE id=? AND version=?',(status,error,stamp(),job_id,version))
            c.execute('UPDATE workflow_versions SET status=? WHERE job_id=? AND version=?',(status,job_id,version))

    @router.post('/{job_id}/retry-solver')
    def retry(job_id: str, settings: SolverSettings):
        with lock:
            job=job_row(job_id)
            if job['profile']!='general' or job['status']=='RUNNING':
                raise HTTPException(409,'当前任务不能从求解检查点重试')
            old=data/'workflows'/job_id/f"v{job['version']}"
            case=old/'openfoam_case'
            required=[case/'0',case/'constant',case/'system',old/'checkMesh.log']
            if not all(p.exists() for p in required) or 'Mesh OK.' not in required[-1].read_text(errors='replace'):
                raise HTTPException(409,'缺少完整求解配置或通过的网格检查，请先完成工程配置')
            inputs=list(old.glob('input.*'))
            with db() as c:
                row=c.execute('SELECT sha256 FROM workflow_versions WHERE job_id=? AND version=?',(job_id,job['version'])).fetchone()
            if not inputs or sha(inputs[0])!=row['sha256']:
                raise HTTPException(409,'输入文件已变化，必须重新检查几何与网格')
            mesh_hash=fingerprint(case/'constant',sha)
            params=settings.model_dump()
            if params['delta_t']>params['end_time'] or params['end_time']/params['delta_t']>100000:
                raise HTTPException(422,'时间步与结束时间组合超出快速验证范围')
            version=job['version']+1
            target=old.parent/f'v{version}'
            target.mkdir()  # Never overwrite an old attempt.
            for path in old.iterdir():
                if path.name in {'openfoam_case','solver.log','checkpoint.json'}: continue
                if path.is_dir(): shutil.copytree(path,target/path.name)
                else: shutil.copy2(path,target/path.name)
            for name in ('0','constant','system'):
                shutil.copytree(case/name,target/'openfoam_case'/name)
            if fingerprint(case/'constant',sha)!=mesh_hash:
                raise HTTPException(409,'复制期间网格发生变化，请重新检查')
            control=target/'openfoam_case/system/controlDict'
            text=control.read_text()
            for key,value in {'deltaT':params['delta_t'],'endTime':params['end_time'],'maxCo':params['max_co'],'adjustTimeStep':'yes','startFrom':'startTime','startTime':0}.items():
                pattern=rf'(?m)^\s*{key}\s+[^;]+;'
                text=re.sub(pattern,f'{key} {value};',text) if re.search(pattern,text) else text+f'\n{key} {value};\n'
            control.write_text(text)
            manifest={'stage':'OPENFOAM_SOLVE','parent_version':job['version'],'created':stamp(),'input_sha256':row['sha256'],'mesh':mesh_hash,'parameters':params,'parameter_sha256':hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest(),'software':'OpenFOAM Foundation 13 (configured; see execution logs)','restart':'time zero; upstream mesh reused'}
            (target/'checkpoint.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            with db() as c:
                c.execute('INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)',(job_id,version,inputs[0].name,row['sha256'],'solver_checkpoint','RUNNING',None,stamp()))
                c.execute("INSERT INTO workflow_reviews SELECT job_id,?,decision,reviewer,note,created FROM workflow_reviews WHERE job_id=? AND version=?",(version,job_id,job['version']))
                c.execute("UPDATE workflow_jobs SET version=?,stage='OPENFOAM_SOLVE',status='RUNNING',error=NULL,updated=? WHERE id=?",(version,stamp(),job_id))
        threading.Thread(target=execute,args=(job_id,version,target),daemon=True).start()
        return details(job_id)
