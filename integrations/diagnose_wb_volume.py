"""Independent volume-mesh trials; never relax the checkMesh threshold."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
ratio = float(sys.argv[1])
out = root/'data'/('wb_volume_trial_'+str(ratio))
out.mkdir(exist_ok=False)
scripts=root/'integrations/generic_external'
exe=json.loads((root/'config.json').read_text())['pointwise_glyph_executable']
for script,args,log in [
    ('pointwise_aircraft.glf',[str(root/'deliverables/crm_like_wb_clean/surface_validation/surface.stl'),str(out/'pointwise'),'4',str(ratio),'3'],'pointwise.log'),
    ('export_openfoam.glf',[str(out/'pointwise/aircraft_volume.pw'),str(out/'export')],'export.log')]:
    if script.startswith('pointwise'): (out/'pointwise').mkdir()
    with (out/log).open('w') as stream:
        subprocess.run([exe,str(scripts/script),*args],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=600)
case=out/'case'
shutil.copytree(out/'export',case/'constant/polyMesh')
(case/'system').mkdir()
shutil.copy2(root/'integrations/l1/foam_template/system/controlDict',case/'system/controlDict')
linux='/mnt/'+str(case)[0].lower()+case.as_posix()[2:]
with (out/'checkMesh_mm.log').open('w') as stream:
    proc=subprocess.run(['wsl.exe','-d','Ubuntu-F2','--','bash','-lc',f'source /opt/openfoam13/etc/bashrc && checkMesh -case {linux}'],stdout=stream,stderr=subprocess.STDOUT,timeout=300)
text=(out/'checkMesh_mm.log').read_text(errors='replace')
result={'wall_spacing_ratio':ratio,'passed':proc.returncode==0 and 'Mesh OK.' in text,'directory':str(out)}
(out/'assessment.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
