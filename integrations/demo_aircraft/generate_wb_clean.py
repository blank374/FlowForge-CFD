"""Create a closed, swept wing-body demonstration CAD; not a CRM replica."""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_iges as writer


def shape(direction):
    x, y, z = direction
    body = 1/math.sqrt((x/750)**2 + (y/75)**2 + (z/75)**2)
    sweep = x - 0.52*abs(y)
    wing = 650*abs(y)**2 * math.exp(-(sweep/0.28)**4) * math.exp(-(z/0.075)**2)
    return np.asarray(direction)*(body+wing)


def main():
    out = ROOT/'deliverables/crm_like_wb_clean'
    out.mkdir(parents=True, exist_ok=False)
    writer.OUT = out/'crm_like_wb_clean.igs'
    writer.N = 9
    writer.point = shape
    def patch_parameters(patch):
        face, sub = divmod(patch,64)
        row,col=divmod(sub,8)
        n=9
        values=[128,n-1,n-1,1,1,0,0,1,0,0]+writer.knots(n)*2+[1]*(n*n)
        for j in range(n):
            for i in range(n):
                u=-1+2*(col*8+i)/64
                v=-1+2*(row*8+j)/64
                d=np.array(writer.direction(face,u,v),dtype=float)
                values.extend(shape(d/np.linalg.norm(d)).tolist())
        values += [0,n-1,0,n-1]
        return ','.join(f'{v:.12g}' if isinstance(v,float) else str(v) for v in values)+';'
    writer.parameters=patch_parameters
    writer.main(patch_count=384)
    writer.N = 65
    facets = []
    for face in range(6):
        points = []
        for j in range(writer.N):
            row = []
            for i in range(writer.N):
                d = np.array(writer.direction(face, -1+2*i/(writer.N-1), -1+2*j/(writer.N-1)), dtype=float)
                row.append(shape(d/np.linalg.norm(d)))
            points.append(row)
        for j in range(writer.N-1):
            for i in range(writer.N-1):
                a,b,c,d=points[j][i],points[j][i+1],points[j+1][i],points[j+1][i+1]
                for tri in ([a,b,d],[a,d,c]):
                    tri=np.array(tri)
                    normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
                    if np.dot(normal,tri.mean(axis=0))<0:
                        tri=tri[[0,2,1]];normal=-normal
                    normal/=np.linalg.norm(normal)
                    facets.append((normal,tri))
    with (out/'preview.stl').open('wb') as stream:
        stream.write(b'Simplified no-tail swept wing-body, millimetres, not CRM'.ljust(80,b' '))
        stream.write(struct.pack('<I',len(facets)))
        for normal,tri in facets:
            stream.write(struct.pack('<12fH',*(normal.tolist()+tri.flatten().tolist()),0))
    vertices=np.concatenate([tri for _,tri in facets])
    (out/'design.json').write_text(json.dumps({'kind':'simplified_swept_wing_body_not_CRM',
        'units':'mm','layout':'full symmetric wing-body; swept wings; no horizontal or vertical tail',
        'bbox_min_mm':vertices.min(axis=0).tolist(),'bbox_max_mm':vertices.max(axis=0).tolist(),
        'recommended_surface_length_mm':12,'IGES_patches':384,'CAD_type':'piecewise bilinear type128 surfaces',
        'not_for':'DPW validation or substitution for the original CRM outer mold line'},indent=2))


if __name__=='__main__':
    main()
