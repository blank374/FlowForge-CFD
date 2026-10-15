"""Immutable solver restart: reuse only a fingerprinted mesh, restart from time zero."""
import hashlib
import json
import re
import os
import shlex
import shutil
import subprocess
import threading
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel, Field

class SolverSettings(BaseModel):
    delta_t: float = Field(default=0.000001, gt=0, le=0.0001, allow_inf_nan=False)
    end_time: float = Field(default=0.002, gt=0, le=10, allow_inf_nan=False)
    max_co: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)

def fingerprint(directory, sha):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}

def register_recovery(router, data, config, job_row, details, db, lock, stamp, sha):
    def execute(job_id, version, directory):
        status, error = 'FAILED', None
        try:
            case=directory/'openfoam_case'
            windows=case.resolve().as_posix()
            if not re.match(r'^[A-Za-z]:/', windows):
                raise RuntimeError('Unsupported WSL case path')
            linux='/mnt/'+windows[0].lower()+windows[2:]
            for command, name in [('checkMesh','checkMesh.log'),('foamRun','solver.log')]:
                with (directory/name).open('w',encoding='utf-8') as out:
                    result=subprocess.run(['wsl.exe','-d',os.getenv('FLOWFORGE_WSL_DISTRO',config.get('wsl_distro','Ubuntu-F2')),'--','bash','-lc',
                        f'source /opt/openfoam13/etc/bashrc && exec {command} -case {shlex.quote(linux)}'],stdout=out,stderr=subprocess.STDOUT,timeout=1800)
                text=(directory/name).read_text(encoding='utf-8',errors='replace')
                if result.returncode or (command=='checkMesh' and 'Mesh OK.' not in text):
                    raise RuntimeError(f'{command} 未通过，请查看 {name}；原检查点已保留')
            courant=[float(v) for v in re.findall(r'Courant Number mean: [0-9.eE+-]+ max: ([0-9.eE+-]+)',text)]
            if '\nEnd\n' not in text or not courant or max(courant)>1 or re.search(r'FOAM FATAL|^\s*Floating point exception\s*$|\bnan\b|\binf\b',text,re.I|re.M):
                raise RuntimeError('求解数值检查未通过，本次流场不可用；网格和原始日志已保留')
            # A finished process alone does not establish trustworthy flow results.
            metadata=json.loads((directory/'checkpoint.json').read_text(encoding='utf-8'))
            end=metadata['parameters']['end_time']
            times=[float(v) for v in re.findall(r'(?m)^Time = ([0-9.eE+-]+)',text)]
            if not times or abs(times[-1]-end)>max(1e-8,end*1e-5):
                raise RuntimeError('未完成设定时间段，不能生成成功报告')
            if (directory/'external_setup.json').is_file():
                root=Path(__file__).resolve().parents[1]
                def wsl_path(path):
                    value=path.resolve().as_posix()
                    return '/mnt/'+value[0].lower()+value[2:]
                scripts=[['python3',wsl_path(root/'backend/plot_residuals.py'),wsl_path(directory/'solver.log'),wsl_path(directory)],
                         ['pvbatch',wsl_path(root/'backend/render_external.py'),linux,wsl_path(directory),str(end)],
                         ['python3',wsl_path(root/'backend/plot_fields.py'),wsl_path(directory/'slice_centers.csv'),wsl_path(directory),'External flow transient result']]
                for index,args in enumerate(scripts):
                    with (directory/f'postprocess_{index}.log').open('w',encoding='utf-8') as out:
                        proc=subprocess.run(['wsl.exe','-d',os.getenv('FLOWFORGE_WSL_DISTRO','Ubuntu-F2'),'--','bash','-lc','source /opt/openfoam13/etc/bashrc && '+shlex.join(args)],stdout=out,stderr=subprocess.STDOUT,timeout=180)
                    if proc.returncode:raise RuntimeError('后处理未通过，请查看 postprocess 日志；不会生成成功报告')
                from backend.reporting import write_report
                setup=json.loads((directory/'external_setup.json').read_text(encoding='utf-8'))
                manifest=json.loads((directory/'paraview_manifest.json').read_text())
                result={'title':'低速不可压外流场计算报告','scope':'当前模型的瞬态层流计算记录；物理适用性尚待人工审核，不代表稳态收敛或气动验证。','input_model':job_id,'cells':manifest['volume_cells'],'physics':setup['settings'],'numerical_criteria':'完成指定时间段；Courant 数未超过 1；需进一步审核残差与物理适用性','final_time_s':end,'steps':len(times),'velocity_outlier_warning':'未配置物理范围验收阈值，须人工审核'}
                write_report(directory,result)
                (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
                shutil.make_archive(str(directory/'openfoam_case'),'zip',root_dir=directory,base_dir='openfoam_case')
            status='WAITING_FOR_REVIEW' 
            error='求解进程结束；需审核残差、质量与物理适用性。若有报告，报告仅记录瞬态测试结果。'
        except Exception as exc:
            error=str(exc)
        if not (directory/'report.docx').is_file():
            try:
                from backend.word_report import write_word_report, read
                setup=read(directory,'external_setup.json')
                write_word_report(directory,{'input_model':job_id,'physics':setup.get('settings',{}),
                    'scope':error or '求解执行记录，标准验收未完成'},status=status)
            except Exception as report_error:
                (directory/'word_report_error.log').write_text(str(report_error),encoding='utf-8')
                error=(error or '')+'；Word 报告生成失败：'+str(report_error)
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
            selected_version=job['version']
            failed_checkpoint=old/'checkpoint.json'
            current_check=old/'checkMesh.log'
            if failed_checkpoint.is_file() and (not current_check.is_file() or 'Mesh OK.' not in current_check.read_text(errors='replace')):
                metadata=json.loads(failed_checkpoint.read_text(encoding='utf-8'))
                current_inputs=list(old.glob('input.*'))
                if not current_inputs or sha(current_inputs[0])!=metadata['input_sha256']:
                    raise HTTPException(409,'当前几何已修改，不能回退复用网格')
                candidate=old.parent/f"v{metadata['parent_version']}"
                if fingerprint(old/'openfoam_case/constant',sha)!=metadata['mesh'] or fingerprint(candidate/'openfoam_case/constant',sha)!=metadata['mesh']:
                    raise HTTPException(409,'上游网格已改变，不能恢复旧检查点')
                selected_version=metadata['parent_version']
                old=candidate
            case=old/'openfoam_case'
            required=[case/'0',case/'constant',case/'system',old/'checkMesh.log']
            if not all(p.exists() for p in required) or 'Mesh OK.' not in required[-1].read_text(errors='replace'):
                raise HTTPException(409,'缺少完整求解配置或通过的网格检查，请先完成工程配置')
            inputs=list(old.glob('input.*'))
            with db() as c:
                row=c.execute('SELECT sha256 FROM workflow_versions WHERE job_id=? AND version=?',(job_id,selected_version)).fetchone()
            if not inputs or sha(inputs[0])!=row['sha256']:
                raise HTTPException(409,'输入文件已变化，必须重新检查几何与网格')
            required_files=['0/U','0/p','system/controlDict','system/fvSchemes','system/fvSolution',
                            'constant/polyMesh/points','constant/polyMesh/faces','constant/polyMesh/owner',
                            'constant/polyMesh/neighbour','constant/polyMesh/boundary']
            if not all((case/name).is_file() for name in required_files):
                raise HTTPException(409,'求解配置不完整：需初始场、数值字典及完整体网格')
            mesh_hash=fingerprint(case/'constant',sha)
            parent_manifest=old/'checkpoint.json'
            if parent_manifest.is_file() and json.loads(parent_manifest.read_text(encoding='utf-8'))['mesh']!=mesh_hash:
                raise HTTPException(409,'检查点网格已改变，必须重新生成并验证上游网格')
            params=settings.model_dump()
            if params['delta_t']>params['end_time'] or params['end_time']/params['delta_t']>100000:
                raise HTTPException(422,'时间步与结束时间组合超出快速验证范围')
            version=job['version']+1
            target=old.parent/f'v{version}'
            if target.exists():
                raise HTTPException(409,'下一版本目录已存在，请检查上次未完成的检查点；不会覆盖')
            target.mkdir()  # Never overwrite an old attempt.
            for path in old.iterdir():
                if path.name in {'openfoam_case','solver.log','checkpoint.json','checkMesh.log','manual_edit.json',
                                 'result.json','report.html','report.docx','report.md','U.png','p.png','residuals.png',
                                 'paraview_manifest.json','external_flow.pvsm','slice_centers.csv',
                                 'openfoam_case.zip','force_coefficients.csv'} or path.name.startswith('postprocess_'): continue
                if path.is_dir(): shutil.copytree(path,target/path.name)
                else: shutil.copy2(path,target/path.name)
            for name in ('0','constant','system'):
                shutil.copytree(case/name,target/'openfoam_case'/name)
            if fingerprint(case/'constant',sha)!=mesh_hash or fingerprint(target/'openfoam_case/constant',sha)!=mesh_hash:
                raise HTTPException(409,'复制期间网格发生变化，请重新检查')
            control=target/'openfoam_case/system/controlDict'
            text=control.read_text()
            for key,value in {'deltaT':params['delta_t'],'endTime':params['end_time'],'maxCo':params['max_co'],'adjustTimeStep':'yes','writeControl':'adjustableRunTime','writeInterval':params['end_time'],'startFrom':'startTime','startTime':0}.items():
                pattern=rf'(?m)^\s*{key}\s+[^;]+;'
                text=re.sub(pattern,f'{key} {value};',text) if re.search(pattern,text) else text+f'\n{key} {value};\n'
            control.write_text(text)
            numerics = None
            if (target/'external_setup.json').is_file():
                from backend.numerics import limit_nonorthogonal_correction
                numerics = limit_nonorthogonal_correction(target/'openfoam_case')
            manifest={'stage':'OPENFOAM_SOLVE','parent_version':selected_version,'created':stamp(),'input_sha256':row['sha256'],'mesh':mesh_hash,'parameters':params,'parameter_sha256':hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest(),'software':'OpenFOAM Foundation 13 (configured; see execution logs)','restart':'time zero; upstream mesh reused'}
            manifest['numerics'] = numerics
            (target/'checkpoint.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            with db() as c:
                c.execute('INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)',(job_id,version,inputs[0].name,row['sha256'],'solver_checkpoint','RUNNING',None,stamp()))
                c.execute("INSERT INTO workflow_reviews SELECT job_id,?,decision,reviewer,note,created FROM workflow_reviews WHERE job_id=? AND version=?",(version,job_id,selected_version))
                c.execute("UPDATE workflow_jobs SET version=?,stage='OPENFOAM_SOLVE',status='RUNNING',error=NULL,updated=? WHERE id=?",(version,stamp(),job_id))
        threading.Thread(target=execute,args=(job_id,version,target),daemon=True).start()
        return details(job_id)
