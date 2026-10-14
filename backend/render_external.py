"""Extract an actual internal-mesh central slice at an explicitly requested time."""
import json,sys
from pathlib import Path
from paraview.simple import OpenFOAMReader,Slice,CellCenters,SaveData,SaveState,CreateView,Show,ColorBy
case,out=Path(sys.argv[1]),Path(sys.argv[2]);time=float(sys.argv[3]);marker=case/'case.foam';marker.touch()
reader=OpenFOAMReader(FileName=str(marker));reader.MeshRegions=['internalMesh'];reader.CellArrays=['U','p'];reader.SkipZeroTime=1;reader.UpdatePipeline(time=time)
info=reader.GetDataInformation();bounds=info.GetBounds()
if info.GetNumberOfCells()<1:raise RuntimeError('Empty volume field')
cut=Slice(Input=reader);cut.SliceType='Plane';cut.SliceType.Origin=[(bounds[i]+bounds[i+1])/2 for i in (0,2,4)];cut.SliceType.Normal=[0,0,1];cut.UpdatePipeline(time=time)
if cut.GetDataInformation().GetNumberOfCells()<1:raise RuntimeError('Empty slice')
centers=CellCenters(Input=cut);centers.UpdatePipeline(time=time);SaveData(str(out/'slice_centers.csv'),proxy=centers)
view=CreateView('RenderView');Show(cut,view);ColorBy(Show(cut,view),('CELLS','U','Magnitude'));view.ResetCamera();SaveState(str(out/'external_flow.pvsm'))
(out/'paraview_manifest.json').write_text(json.dumps({'time_s':time,'volume_cells':info.GetNumberOfCells(),'bounds_m':bounds,'source':str(marker),'slice':'domain central XY plane'}))
