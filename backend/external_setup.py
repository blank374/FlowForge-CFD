"""Explicit low-speed external-flow setup; independent of model shape."""
import hashlib
import json
import re
import shutil
from fastapi import HTTPException
from pydantic import BaseModel, Field
from pathlib import Path

class ExternalSetup(BaseModel):
    speed_m_s: float = Field(gt=0,le=60,allow_inf_nan=False)
    nu_m2_s: float = Field(gt=0,le=1,allow_inf_nan=False)
    wall_patch: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    farfield_patch: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    laminar_confirmed: bool
    units_confirmed: bool

def configure_case(case, setup):
    if not setup.laminar_confirmed or not setup.units_confirmed:
        raise HTTPException(422,'请确认网格为米，并确认层流模型适用；湍流闭合模型尚未接入')
    boundary=(case/'constant/polyMesh/boundary').read_text(encoding='utf-8')
    patches=set(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\{[^{}]*?nFaces\s+\d+\s*;',boundary))
    if {setup.wall_patch,setup.farfield_patch}!=patches or setup.wall_patch==setup.farfield_patch:
        raise HTTPException(422,'边界映射须与实际网格完全一致；当前支持一个壁面组和一个远场组')
    for patch,kind in [(setup.wall_patch,'wall'),(setup.farfield_patch,'patch')]:
        match=re.search(rf'\b{patch}\s*\{{([^{{}}]*)\}}',boundary)
        if not match or not re.search(rf'\btype\s+{kind}\s*;',match.group(1)):
            raise HTTPException(422,'网格边界类型不符合壁面/远场设置，请在 Pointwise 中修正')
    zero=case/'0';zero.mkdir(exist_ok=True)
    velocity=f'({setup.speed_m_s} 0 0)'
    (zero/'U').write_text('FoamFile { format ascii; class volVectorField; object U; }\ndimensions [0 1 -1 0 0 0 0];\n'+f'internalField uniform {velocity};\nboundaryField {{ {setup.wall_patch} {{ type noSlip; }} {setup.farfield_patch} {{ type freestreamVelocity; freestreamValue uniform {velocity}; }} }}',encoding='utf-8')
    (zero/'p').write_text('FoamFile { format ascii; class volScalarField; object p; }\ndimensions [0 2 -2 0 0 0 0];\n'+f'internalField uniform 0;\nboundaryField {{ {setup.wall_patch} {{ type zeroGradient; }} {setup.farfield_patch} {{ type freestreamPressure; freestreamValue uniform 0; }} }}',encoding='utf-8')
    (case/'constant/physicalProperties').write_text('FoamFile { format ascii; class dictionary; object physicalProperties; }\nviscosityModel constant;\n'+f'nu {setup.nu_m2_s} [m^2/s];\n',encoding='utf-8')
    (case/'constant/momentumTransport').write_text('FoamFile { format ascii; class dictionary; object momentumTransport; }\nsimulationType laminar;\n',encoding='utf-8')
    return setup.model_dump()

def register_setup(router,data,root,job_row,details,db,lock,stamp,sha):
    @router.post('/{job_id}/external-setup')
    def setup(job_id:str,body:ExternalSetup):
        with lock:
            job=job_row(job_id)
            if job['profile']!='general' or job['status']=='RUNNING':raise HTTPException(409,'等待当前阶段完成')
            old=data/'workflows'/job_id/f"v{job['version']}"
            check=old/'checkMesh.log'
            if not check.is_file() or 'Mesh OK.' not in check.read_text(errors='replace'):raise HTTPException(409,'必须先通过体网格检查')
            # Validate on an isolated copy; never mutate an old run.
            version=job['version']+1;target=old.parent/f'v{version}'
            if target.exists():raise HTTPException(409,'目标版本已存在，不会覆盖')
            import tempfile
            with tempfile.TemporaryDirectory(dir=old.parent) as temp:
                candidate=Path(temp)
                shutil.copytree(old/'openfoam_case',candidate/'case',ignore=shutil.ignore_patterns('postProcessing','processor*'))
                params=configure_case(candidate/'case',body)
                system=candidate/'case/system';system.mkdir(exist_ok=True)
                for name in ('fvSchemes','fvSolution','controlDict'):
                    if not (system/name).is_file():shutil.copy2(root/'integrations/l1/foam_template/system'/name,system/name)
                # Retain time zero only; previous fields cannot become new results.
                for path in (candidate/'case').iterdir():
                    if path.is_dir() and re.fullmatch(r'[0-9.eE+-]+',path.name) and path.name!='0':shutil.rmtree(path)
                shutil.copytree(old,target,ignore=shutil.ignore_patterns('openfoam_case','solver.log','checkpoint.json','manual_edit.json','report.html','report.md','result.json','U.png','p.png','residuals.png','paraview_manifest.json','external_flow.pvsm','slice_centers.csv','openfoam_case.zip','force_coefficients.csv','postprocess_*'))
                shutil.copytree(candidate/'case',target/'openfoam_case')
            manifest={'scenario':'incompressible_external','model':'laminar','settings':params,'parent_version':job['version'],'created':stamp(),'parameter_sha256':hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()}
            (target/'external_setup.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            source=next(target.glob('input.*'))
            with db() as c:
                c.execute('INSERT INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)',(job_id,version,source.name,sha(source),'external_setup','WAITING_FOR_REVIEW',None,stamp()))
                c.execute('INSERT INTO workflow_reviews SELECT job_id,?,decision,reviewer,note,created FROM workflow_reviews WHERE job_id=? AND version=?',(version,job_id,job['version']))
                c.execute("UPDATE workflow_jobs SET version=?,stage='OPENFOAM_SOLVE',status='WAITING_FOR_REVIEW',error=NULL,updated=? WHERE id=?",(version,stamp(),job_id))
        return details(job_id)
