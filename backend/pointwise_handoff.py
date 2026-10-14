"""Pointwise manual handoff with immutable imports and real export/checkMesh gates."""
import json,shutil,subprocess,threading
from pathlib import Path
from fastapi import HTTPException,Request,UploadFile,File

def register_handoff(router,data,config,job_row,details,db,lock,stamp,sha,mesh_volume):
    @router.post('/{job_id}/open-in-pointwise')
    def open_project(job_id:str,request:Request):
        if request.headers.get('origin') and request.headers['origin']!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'只允许从本机工作台启动')
        with lock:
            job=job_row(job_id)
            if job['profile']!='general' or job['status']=='RUNNING':raise HTTPException(409,'请等待自动化阶段完成')
            directory=data/'workflows'/job_id/f"v{job['version']}"
            original=directory/'pointwise/aircraft_volume.pw'
            if not original.is_file():raise HTTPException(409,'没有 Pointwise 工程，请先生成网格或上传修复工程')
            executable=Path(config.get('pointwise_executable',str(Path(config['pointwise_glyph_executable']).with_name('Pointwise.exe'))))
            if not executable.is_file():raise HTTPException(503,'Pointwise 启动路径未配置，请下载工程后修复并上传')
            working=directory/'manual_pointwise.pw';meta=directory/'pointwise_handoff.json'
            if not meta.is_file():
                shutil.copy2(original,working)
                meta.write_text(json.dumps({'initial_sha256':sha(working),'created':stamp()}),encoding='utf-8')
            try:subprocess.Popen([str(executable),str(working)],cwd=str(directory),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except OSError as exc:raise HTTPException(503,str(exc))
        return {'path':str(working),'message':'在 Pointwise 保存修复副本，再提交复检；旧网格和结果仍保留'}

    def import_project(job_id,source,filename):
        with lock:
            job=job_row(job_id)
            if job['profile']!='general' or job['status']=='RUNNING':raise HTTPException(409,'请等待当前阶段完成')
            if Path(filename).suffix.lower()!='.pw':raise HTTPException(422,'请提供 Pointwise .pw 工程')
            old=data/'workflows'/job_id/f"v{job['version']}";version=job['version']+1
            with db() as c:previous=c.execute('SELECT * FROM workflow_versions WHERE job_id=? AND version=?',(job_id,job['version'])).fetchone()
            original=next(old.glob('input.*'))
            if sha(original)!=previous['sha256']:raise HTTPException(409,'原几何已变化，必须先重新进行 ANSA 检查')
            target=old.parent/f'v{version}'
            if target.exists():raise HTTPException(409,'新版本目录已存在，不会覆盖')
            target.mkdir()
            for name in [original.name,'review.ansa','geometry_report.json','ansa.log','surface']:
                path=old/name
                if path.is_dir():shutil.copytree(path,target/name)
                elif path.is_file():shutil.copy2(path,target/name)
            output=target/'pointwise';output.mkdir()
            with (output/'aircraft_volume.pw').open('wb') as dest:shutil.copyfileobj(source,dest)
            if not (output/'aircraft_volume.pw').stat().st_size:raise HTTPException(422,'工程文件为空')
            (target/'manual_pointwise.json').write_text(json.dumps({'parent_version':job['version'],'project_sha256':sha(output/'aircraft_volume.pw'),'geometry_sha256':previous['sha256'],'created':stamp(),'validation':'Pointwise export and checkMesh required'}),encoding='utf-8')
            with db() as c:
                c.execute('INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)',(job_id,version,previous['filename'],previous['sha256'],'manual_pointwise','RUNNING',previous['report'],stamp()))
                c.execute('INSERT INTO workflow_reviews SELECT job_id,?,decision,reviewer,note,created FROM workflow_reviews WHERE job_id=? AND version=?',(version,job_id,job['version']))
                c.execute("UPDATE workflow_jobs SET version=?,status='RUNNING',stage='POINTWISE_VOLUME',error=NULL,updated=? WHERE id=?",(version,stamp(),job_id))
        threading.Thread(target=mesh_volume,args=(job_id,version),daemon=True).start()
        return details(job_id)

    @router.post('/{job_id}/pointwise-repair')
    def upload(job_id:str,file:UploadFile=File(...)):
        return import_project(job_id,file.file,file.filename or '')

    @router.post('/{job_id}/submit-pointwise-repair')
    def submit(job_id:str):
        job=job_row(job_id);directory=data/'workflows'/job_id/f"v{job['version']}"
        working=directory/'manual_pointwise.pw';meta=directory/'pointwise_handoff.json'
        if not meta.is_file() or not working.is_file():raise HTTPException(409,'请先打开 Pointwise 工作副本')
        if sha(working)==json.loads(meta.read_text(encoding='utf-8'))['initial_sha256']:raise HTTPException(409,'尚未检测到保存的修改')
        with working.open('rb') as source:return import_project(job_id,source,working.name)
